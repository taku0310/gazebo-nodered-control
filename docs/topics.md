# Topic Catalog

Combined MQTT + ROS 2 topic list for the whole demo.

## MQTT (control plane)

| Topic | Direction | QoS | Retain | Producer | Consumer |
|---|---|---|---|---|---|
| `robot/cmd_vel` | C → B | 1 | no | Node-RED (or SoftPLC) | `mqtt_ros2_bridge` |
| `robot/status`  | B → C | 1 | yes | `mqtt_ros2_bridge` | Node-RED, ops dashboards |
| `robot/odom`    | B → C | 0 | no | `mqtt_ros2_bridge` | Node-RED, observability |
| `robot/alarm`   | B → C | 1 | no | `mqtt_ros2_bridge` | Node-RED, ops |

Legend: C = client (Node-RED / SoftPLC), B = bridge.

## ROS 2 (simulation plane)

| Topic | Type | Direction | Producer | Consumer |
|---|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | bridge → sim | `mqtt_ros2_bridge` | Gazebo `libgazebo_ros_diff_drive` |
| `/odom`    | `nav_msgs/msg/Odometry`   | sim → bridge | Gazebo `libgazebo_ros_diff_drive` | `mqtt_ros2_bridge` |
| `/tf`      | `tf2_msgs/msg/TFMessage`  | sim → *      | Gazebo diff_drive | rviz, navigation (optional) |
| `/clock`   | `rosgraph_msgs/msg/Clock` | sim → *      | Gazebo            | any sim-time consumer |

`ROS_DOMAIN_ID=42` is shared by the bridge and Gazebo containers.

## Topic → Payload mapping (translation rules)

| MQTT | ROS 2 | Translation |
|---|---|---|
| `robot/cmd_vel` JSON | `/cmd_vel` `Twist` | `linear_x` → `linear.x`; `angular_z` → `angular.z`; others zero. |
| `/odom` `Odometry` | `robot/odom` JSON | `pose.position.{x,y}` and `twist.twist.linear.x` / `angular.z` are kept; throttled to `ODOM_THROTTLE_HZ`. |
| (synthetic) | `robot/status` | retained, written on MQTT connect / LWT. |
| (synthetic) | `robot/alarm` | watchdog state changes. |

## Future extensions

| Topic | Use |
|---|---|
| `robot/mode` (C → B) | `manual` / `auto` switch when a SoftPLC and the dashboard coexist. |
| `robot/cmd_pose` (C → B) | go-to-pose intent for a higher-level planner. |
| `robot/{id}/...` | multi-robot fleet — same payloads, scoped by ID. |
| `robot/diag` (B → C) | structured diagnostics (CPU, latencies). |
