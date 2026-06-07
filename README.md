# gazebo-nodered-control

A Node-RED → MQTT → ROS 2 → Gazebo control demonstrator.

```
Node-RED Dashboard  ──►  Mosquitto  ──►  mqtt_ros2_bridge (ROS 2)  ──►  Gazebo
                              ▲                  │
                              └──── robot/status, robot/odom, robot/alarm
```

The MQTT topic surface is the **single control interface**. Node-RED
plays the role of a manual operator UI today; tomorrow a SoftPLC can
publish the same JSON commands and the ROS 2 side won't notice. See
[`docs/softplc-migration.md`](docs/softplc-migration.md).

## Layout

```
.
├── docker-compose.yml          # one-command stack
├── .env.example                # copy to .env to override
├── docs/
│   ├── architecture.md         # system + data-flow diagrams
│   ├── mqtt-spec.md            # the MQTT contract
│   ├── topics.md               # combined MQTT + ROS 2 topic list
│   ├── test-plan.md            # QA scenarios
│   └── softplc-migration.md    # staged plan to replace Node-RED
├── mosquitto/config/           # broker config
├── nodered/
│   ├── Dockerfile              # Node-RED + node-red-dashboard
│   └── flows.json              # importable Dashboard flow
├── ros2_bridge/
│   ├── Dockerfile              # ros:humble + paho-mqtt + workspace
│   └── ws/src/mqtt_ros2_bridge # the bridge node package
└── gazebo/
    ├── Dockerfile              # ros:humble-desktop + gazebo_ros_pkgs
    └── worlds/diff_drive.world # diff-drive robot + libgazebo_ros_diff_drive
```

## Requirements

* Docker Engine 24+ with Compose v2.
* ~4 GB free disk for first-time image builds.
* (Optional) X11 server on the host if you want to see Gazebo with
  `gzclient`.

## Start

```bash
cp .env.example .env             # optional — defaults are fine
docker compose up --build -d
```

Wait for the four containers to settle (first run pulls and builds; ~5
minutes depending on network):

```bash
docker compose ps
```

Open the dashboard at **http://127.0.0.1:1880/ui**.

Click the direction buttons. Watch the "Bridge" pill flip to `online`
and the "Odom" line update as the robot moves.

## Stop

```bash
docker compose down              # keep volumes
docker compose down -v           # also wipe broker/Node-RED state
```

## Operating the demo

| Action | UI control | MQTT payload |
|---|---|---|
| Forward  | ▲ | `{"linear_x": +speed, "angular_z": 0}` |
| Backward | ▼ | `{"linear_x": -speed, "angular_z": 0}` |
| Left     | ◀ | `{"linear_x": 0, "angular_z": +speed}` |
| Right    | ▶ | `{"linear_x": 0, "angular_z": -speed}` |
| Stop     | ■ | `{"linear_x": 0, "angular_z": 0}` |

`speed` is set by the Speed slider (default 1.0, range 0–2).

Drive headlessly with `mosquitto_pub` to prove the MQTT contract:

```bash
docker compose exec mosquitto mosquitto_pub \
    -t robot/cmd_vel -m '{"linear_x":0.5,"angular_z":0.0}'
docker compose exec mosquitto mosquitto_sub -v -t 'robot/#'
```

Tail the ROS 2 side from inside the bridge container:

```bash
docker compose exec ros2_bridge bash -lc \
    'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
     && ros2 topic echo /cmd_vel --once'
```

## Seeing Gazebo (optional)

By default Gazebo runs headless (`GAZEBO_HEADLESS=1`). To see the
robot move on a Linux host:

```bash
xhost +local:docker
GAZEBO_HEADLESS=0 docker compose up -d gazebo
```

Then a `gzclient` window will attach to the in-container `gzserver`
on the next start. On macOS / Windows, use XQuartz / VcXsrv or run
`gzclient` natively against the same `GAZEBO_MASTER_URI`.

## Tests

Manual scenarios live in [`docs/test-plan.md`](docs/test-plan.md).
They cover the happy path, payload validation, the watchdog, and
isolated failures of the broker, the bridge, and Gazebo.

## Configuration

Everything tunable is an env var on the `ros2_bridge` service. See the
table in [`docs/architecture.md`](docs/architecture.md#4-configuration-surface).

## How it differs from `gazebo-keyboard-control`

| Original | This repo |
|---|---|
| `keyboard_input` over TCP | Node-RED Dashboard over MQTT |
| Dedicated `control_logic` container with clamping + smoothing | Clamping + watchdog live in the bridge; no extra container |
| ROS 2 Jazzy + Gazebo Harmonic | ROS 2 Humble + Gazebo Classic 11 (gazebo_ros_pkgs) |
| TCP boundary | MQTT boundary — same broker can serve a SoftPLC later |

## License

Apache-2.0 (matches the upstream reference repo).
