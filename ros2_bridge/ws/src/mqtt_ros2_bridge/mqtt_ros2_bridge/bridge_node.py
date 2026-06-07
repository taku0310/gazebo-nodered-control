"""MQTT ↔ ROS 2 bridge node.

Subscribes JSON velocity commands on the MQTT broker and republishes them
as geometry_msgs/Twist on /cmd_vel. Listens to /odom and forwards a small
JSON summary back over MQTT, and publishes a retained online/offline
status under a Last Will and Testament.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time

import paho.mqtt.client as mqtt
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _envi(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class MqttRos2Bridge(Node):
    def __init__(self) -> None:
        super().__init__('mqtt_ros2_bridge')

        self.mqtt_host = _env('MQTT_HOST', 'mosquitto')
        self.mqtt_port = _envi('MQTT_PORT', 1883)
        self.cmd_topic = _env('MQTT_CMD_TOPIC', 'robot/cmd_vel')
        self.status_topic = _env('MQTT_STATUS_TOPIC', 'robot/status')
        self.odom_topic = _env('MQTT_ODOM_TOPIC', 'robot/odom')
        self.alarm_topic = _env('MQTT_ALARM_TOPIC', 'robot/alarm')
        self.ros_cmd_topic = _env('ROS_CMD_VEL_TOPIC', '/cmd_vel')
        self.ros_odom_topic = _env('ROS_ODOM_TOPIC', '/odom')
        self.watchdog_sec = _envf('WATCHDOG_SEC', 1.0)
        self.max_linear = _envf('MAX_LINEAR', 2.0)
        self.max_angular = _envf('MAX_ANGULAR', 2.0)
        self.publish_hz = _envf('PUBLISH_HZ', 20.0)
        self.odom_throttle_hz = _envf('ODOM_THROTTLE_HZ', 5.0)

        self._cmd_pub = self.create_publisher(Twist, self.ros_cmd_topic, 10)
        self.create_subscription(Odometry, self.ros_odom_topic, self._on_odom, 10)

        self._lock = threading.Lock()
        self._last_cmd = (0.0, 0.0)
        # Start "stale" so we publish zero until a real command arrives.
        self._last_cmd_time = 0.0
        # Whether a WATCHDOG_TIMEOUT alarm is currently active. Stays False
        # until at least one valid command has been seen and then lost —
        # avoids a spurious CLEAR on the first command after startup.
        self._alarm_active = False
        self._last_odom_pub = 0.0

        self._mqtt = mqtt.Client(client_id='ros2_bridge', clean_session=True)
        self._mqtt.will_set(
            self.status_topic,
            payload=json.dumps({'state': 'offline'}),
            qos=1,
            retain=True,
        )
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_disconnect = self._on_disconnect
        self._mqtt.on_message = self._on_message
        self._mqtt.reconnect_delay_set(min_delay=1, max_delay=30)
        self._mqtt.connect_async(self.mqtt_host, self.mqtt_port, keepalive=30)
        self._mqtt.loop_start()

        period = 1.0 / max(self.publish_hz, 1.0)
        self.create_timer(period, self._tick)

        self.get_logger().info(
            f'bridge ready: mqtt={self.mqtt_host}:{self.mqtt_port} '
            f'cmd_topic={self.cmd_topic} ros_cmd={self.ros_cmd_topic}'
        )

    # ---------- MQTT callbacks ----------

    def _on_connect(self, client: mqtt.Client, userdata, flags, rc) -> None:
        if rc != 0:
            self.get_logger().error(f'MQTT connect failed rc={rc}')
            return
        self.get_logger().info('MQTT connected')
        client.subscribe(self.cmd_topic, qos=1)
        client.publish(
            self.status_topic,
            json.dumps({'state': 'online'}),
            qos=1,
            retain=True,
        )

    def _on_disconnect(self, client: mqtt.Client, userdata, rc) -> None:
        self.get_logger().warning(f'MQTT disconnected rc={rc}')

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            data = json.loads(msg.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f'bad JSON on {msg.topic}: {exc}')
            return

        try:
            lx = float(data.get('linear_x', 0.0))
            az = float(data.get('angular_z', 0.0))
        except (TypeError, ValueError) as exc:
            self.get_logger().warning(f'bad numeric fields: {exc}')
            return

        if not (math.isfinite(lx) and math.isfinite(az)):
            self.get_logger().warning('non-finite command rejected')
            return

        lx = max(min(lx, self.max_linear), -self.max_linear)
        az = max(min(az, self.max_angular), -self.max_angular)

        with self._lock:
            self._last_cmd = (lx, az)
            self._last_cmd_time = time.monotonic()

    # ---------- ROS callbacks ----------

    def _on_odom(self, msg: Odometry) -> None:
        now = time.monotonic()
        period = 1.0 / max(self.odom_throttle_hz, 0.1)
        if (now - self._last_odom_pub) < period:
            return
        self._last_odom_pub = now
        payload = {
            'x': msg.pose.pose.position.x,
            'y': msg.pose.pose.position.y,
            'linear_x': msg.twist.twist.linear.x,
            'angular_z': msg.twist.twist.angular.z,
        }
        self._mqtt.publish(self.odom_topic, json.dumps(payload), qos=0)

    # ---------- Periodic loop ----------

    def _tick(self) -> None:
        now = time.monotonic()
        with self._lock:
            cmd = self._last_cmd
            last_cmd_time = self._last_cmd_time
            stale = (now - last_cmd_time) > self.watchdog_sec

        ever_received = last_cmd_time > 0.0

        if stale:
            cmd = (0.0, 0.0)
            # Only fire TIMEOUT after we've actually seen at least one
            # command — startup with no traffic is not an alarm.
            if ever_received and not self._alarm_active:
                self._mqtt.publish(
                    self.alarm_topic,
                    json.dumps({'code': 'WATCHDOG_TIMEOUT',
                                'detail': f'no cmd_vel within {self.watchdog_sec}s'}),
                    qos=1,
                )
                self.get_logger().warning('watchdog: publishing zero velocity')
                self._alarm_active = True
        else:
            if self._alarm_active:
                self._mqtt.publish(
                    self.alarm_topic,
                    json.dumps({'code': 'WATCHDOG_CLEAR', 'detail': 'cmd_vel resumed'}),
                    qos=1,
                )
                self._alarm_active = False

        twist = Twist()
        twist.linear.x = float(cmd[0])
        twist.angular.z = float(cmd[1])
        self._cmd_pub.publish(twist)

    # ---------- Lifecycle ----------

    def shutdown(self) -> None:
        try:
            self._mqtt.publish(
                self.status_topic,
                json.dumps({'state': 'offline'}),
                qos=1,
                retain=True,
            )
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
        except Exception:
            pass


def main() -> None:
    rclpy.init()
    node = MqttRos2Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
