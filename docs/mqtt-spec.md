# MQTT Specification

This is the public contract between control clients (Node-RED, future
SoftPLC) and the `ros2_bridge` node.

## 1. Broker

| Item | Value |
|---|---|
| Implementation | Eclipse Mosquitto 2.x |
| Host (inside compose) | `mosquitto` |
| Plain MQTT port | `1883` (TCP) |
| WebSocket port | `9001` |
| Auth | Anonymous (demo). Replace with `password_file` + ACL for production. |
| TLS | Off (demo). Add a TLS listener for production. |
| Persistence | Enabled, volume-backed |

## 2. Versioning rule

* Topics are versionless during PoC. When a breaking change is needed,
  introduce a `v2/` prefix (e.g. `robot/v2/cmd_vel`) and run both for
  one release.
* Payload keys may be **added** without bumping; existing clients must
  ignore unknown fields. Removing or renaming a key is breaking.

## 3. Topic summary

| Topic | Direction | QoS | Retain | Payload |
|---|---|---|---|---|
| `robot/cmd_vel` | client → bridge | 1 | no | Twist JSON, see §4 |
| `robot/status`  | bridge → client | 1 | **yes** | `{"state":"online"\|"offline"}` (LWT) |
| `robot/odom`    | bridge → client | 0 | no | Odom JSON, see §4 |
| `robot/alarm`   | bridge → client | 1 | no | Alarm JSON, see §4 |

Reserved for later: `robot/v2/*`, `robot/{id}/...` for multi-robot fleets.

## 4. Payload schemas

All payloads are UTF-8 JSON objects. Numeric values are double precision.

### 4.1 `robot/cmd_vel`

```json
{
  "linear_x": 1.0,
  "angular_z": 0.0
}
```

* `linear_x` — forward velocity in m/s. Positive = forward. Required.
* `angular_z` — yaw rate in rad/s. Positive = counter-clockwise. Required.
* The bridge clamps to `±MAX_LINEAR` / `±MAX_ANGULAR`.
* Non-finite values (`NaN`, `Infinity`) are rejected and logged.
* Reserved keys for forward compatibility: `linear_y`, `angular_x`,
  `angular_y`, `seq`, `ts`.

Canonical examples (mirror the task spec):

| Action | Payload |
|---|---|
| Forward  | `{"linear_x":  1.0, "angular_z":  0.0}` |
| Backward | `{"linear_x": -1.0, "angular_z":  0.0}` |
| Left     | `{"linear_x":  0.0, "angular_z":  1.0}` |
| Right    | `{"linear_x":  0.0, "angular_z": -1.0}` |
| Stop     | `{"linear_x":  0.0, "angular_z":  0.0}` |

### 4.2 `robot/status`

```json
{ "state": "online" }
```

* `state ∈ {"online", "offline"}`. Retained.
* Published as `online` on every successful broker connect.
* Last Will publishes `offline` if the bridge dies without a clean
  disconnect.

### 4.3 `robot/odom`

```json
{
  "x": 1.23,
  "y": -0.45,
  "linear_x": 0.50,
  "angular_z": 0.10
}
```

* `x`, `y` — pose in meters in the `odom` frame.
* `linear_x`, `angular_z` — measured velocities.
* Throttled to `ODOM_THROTTLE_HZ` (default 5 Hz).

### 4.4 `robot/alarm`

```json
{
  "code": "WATCHDOG_TIMEOUT",
  "detail": "no cmd_vel within 1.0s"
}
```

| `code` | Meaning |
|---|---|
| `WATCHDOG_TIMEOUT` | No valid command for `WATCHDOG_SEC`; zero velocity forced. |
| `WATCHDOG_CLEAR`   | Commands resumed after a timeout. |

Future codes (reserved): `BRIDGE_OVERLOAD`, `INVALID_PAYLOAD`,
`GAZEBO_UNREACHABLE`.

## 5. QoS policy

| Class | QoS | Why |
|---|---|---|
| Command (`robot/cmd_vel`) | 1 | Exactly the deliver-at-least-once we want; duplicates are harmless because the bridge republishes at fixed rate. |
| Status (`robot/status`) | 1 + retained | Late-joining subscribers must see current state. |
| Alarm (`robot/alarm`) | 1 | Don't silently drop. |
| Telemetry (`robot/odom`) | 0 | High rate; loss is tolerable. |

QoS 2 is intentionally avoided — its broker overhead is not justified
for a control demo.

## 6. Security posture

The PoC runs anonymous on loopback only (`MQTT_BIND=127.0.0.1`).
Before exposing the broker:

1. Enable `password_file` + per-client credentials in `mosquitto.conf`.
2. Add an ACL restricting `robot/cmd_vel` writes to controller
   identities (Node-RED, SoftPLC) and `robot/odom/status/alarm`
   writes to the bridge identity only.
3. Add a TLS listener (`listener 8883`) with a server certificate.
