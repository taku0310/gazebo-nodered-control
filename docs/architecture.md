# System Architecture

## 1. Goal

Replace the original `keyboard_input → control_logic → gazebo` PoC with a
demonstrator that drives the same Gazebo robot from a **Node-RED
Dashboard** through **MQTT**. The MQTT topic surface is the single,
stable control interface, so the dashboard can later be swapped for a
SoftPLC without touching the ROS 2 side.

## 2. Container topology

```mermaid
flowchart LR
    subgraph Browser
      UI[Node-RED Dashboard UI]
    end

    subgraph control_net["Docker network: control_net"]
      NR[nodered<br/>Node-RED 3.x]
      MB[mosquitto<br/>MQTT broker]
      BR[ros2_bridge<br/>mqtt_ros2_bridge node]
      GZ[gazebo<br/>gzserver + diff_drive plugin]
    end

    UI -- HTTP/WebSocket --> NR
    NR -- "publish robot/cmd_vel" --> MB
    MB -- "subscribe robot/cmd_vel" --> BR
    BR -- "publish /cmd_vel<br/>(geometry_msgs/Twist)" --> GZ
    GZ -- "publish /odom<br/>(nav_msgs/Odometry)" --> BR
    BR -- "publish robot/odom<br/>robot/status<br/>robot/alarm" --> MB
    MB -- subscribe --> NR
```

* **Single control interface** — every actor in the chain only speaks
  MQTT or ROS 2. The MQTT topic surface is the contract.
* **No `control_logic` container** — clamping, watchdog, and command
  shaping live inside the bridge node so there is one less moving part.
* **DDS stays inside Docker** — `gazebo` and `ros2_bridge` share the
  `ROS_DOMAIN_ID` and the `control_net` bridge network; the rest of the
  world only sees MQTT.

## 3. Data flow

```mermaid
sequenceDiagram
    participant UI as Dashboard button
    participant NR as Node-RED flow
    participant M  as Mosquitto
    participant BR as mqtt_ros2_bridge
    participant GZ as Gazebo (diff_drive)

    UI->>NR: click "Forward"
    NR->>NR: function: dir+speed → JSON
    NR->>M: PUBLISH robot/cmd_vel<br/>{"linear_x":1.0,"angular_z":0.0}
    M->>BR: deliver (QoS 1)
    BR->>BR: clamp + cache cmd
    loop 20 Hz
        BR->>GZ: /cmd_vel Twist
    end
    GZ->>BR: /odom Odometry
    BR->>M: PUBLISH robot/odom (≤5 Hz)
    M->>NR: deliver
    NR->>UI: update telemetry
```

Two safety features live in the bridge:

* **Watchdog.** If no command arrives within `WATCHDOG_SEC` (default
  `1.0`), the bridge republishes `(0, 0)` on `/cmd_vel` and emits a
  `WATCHDOG_TIMEOUT` alarm. A `WATCHDOG_CLEAR` alarm is emitted once
  commands resume.
* **Status LWT.** `robot/status` is a retained MQTT topic. On healthy
  connect the bridge publishes `{"state":"online"}`; the broker
  publishes `{"state":"offline"}` as the Last Will if the bridge
  crashes. Dashboards (and future SoftPLCs) can rely on this signal.

## 4. Configuration surface

All tunables are environment variables on the `ros2_bridge` service
(see `docker-compose.yml`):

| Var | Default | Meaning |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `mosquitto` / `1883` | broker address |
| `MQTT_CMD_TOPIC` | `robot/cmd_vel` | inbound command topic |
| `MQTT_STATUS_TOPIC` | `robot/status` | retained online/offline |
| `MQTT_ODOM_TOPIC` | `robot/odom` | outbound telemetry |
| `MQTT_ALARM_TOPIC` | `robot/alarm` | outbound alarms |
| `ROS_CMD_VEL_TOPIC` | `/cmd_vel` | ROS publisher |
| `ROS_ODOM_TOPIC` | `/odom` | ROS subscriber |
| `WATCHDOG_SEC` | `1.0` | zero out cmd after this many seconds idle |
| `MAX_LINEAR` / `MAX_ANGULAR` | `2.0` / `2.0` | clamp limits (m/s, rad/s) |
| `PUBLISH_HZ` | `20.0` | /cmd_vel republish rate |
| `ODOM_THROTTLE_HZ` | `5.0` | MQTT odom rate cap |

## 5. Future-proofing for SoftPLC

The dashboard is one MQTT client; nothing on the ROS 2 side knows or
cares about Node-RED. A SoftPLC (Codesys, OpenPLC, Beckhoff TwinCAT
with an MQTT runtime, Siemens with `IoTSink`, …) drops in by:

1. Connecting to the same broker on the same network.
2. Publishing `robot/cmd_vel` with the same JSON payload.
3. Subscribing to `robot/status`, `robot/odom`, `robot/alarm`.

See `docs/softplc-migration.md` for the staged plan.
