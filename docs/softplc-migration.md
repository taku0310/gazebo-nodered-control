# SoftPLC Migration Plan

The PoC dashboard is one MQTT client; nothing downstream knows about
Node-RED. This document describes the staged plan to swap it for a
SoftPLC without breaking the simulator side.

## Why MQTT is the right boundary

| Property | Why it matters for PLC handoff |
|---|---|
| Topic-and-payload contract | PLC and ROS 2 only need to agree on JSON keys, not on a transport (no rclpy/DDS in the PLC). |
| QoS 1 + retained status | PLCs come and go; retained `robot/status` gives them current health on connect. |
| Broker-side fan-out | Dashboard, PLC, observers can all coexist on the same topic for hot-takeover. |
| Open-source brokers | Mosquitto, HiveMQ, EMQX, AWS IoT, etc. are all interoperable. |

## Phase 0 — current (Node-RED only)

```
[Node-RED Dashboard]  ──►  Mosquitto  ──►  ros2_bridge  ──►  Gazebo
```

## Phase 1 — shadow SoftPLC

Run the SoftPLC in parallel and have it **read** from MQTT only:

* `robot/odom`, `robot/status`, `robot/alarm` → PLC inputs.
* PLC logic computes a candidate `cmd_vel` but does **not** publish.
* Node-RED still drives the robot.
* Compare PLC-computed command vs. Node-RED command in a log/HMI to
  build confidence in the PLC logic.

Acceptance: PLC and Node-RED outputs match within tolerance for the
test suite in `docs/test-plan.md`.

## Phase 2 — supervised switchover

Introduce a mode topic so a human can switch authority at runtime
**without** changing the ROS 2 side.

```
robot/mode  (retained, QoS 1)   values:  "manual" | "auto"
```

* `manual`: only Node-RED writes `robot/cmd_vel`. PLC stays in shadow.
* `auto`: only the PLC writes `robot/cmd_vel`. Node-RED reverts to
  monitor-only.
* The bridge does **not** arbitrate. Whichever client violates the
  rule loses by social contract (and operator alerting).

If hard arbitration becomes necessary later, the bridge can grow a
mode-aware filter, but it isn't required for the demo.

## Phase 3 — Node-RED retired

Remove the `nodered` service from `docker-compose.yml`. The diff
collapses to:

```yaml
services:
  mosquitto: ...
  softplc:   ...   # new service or external host
  ros2_bridge: ... # unchanged
  gazebo:    ...   # unchanged
```

The `robot/*` MQTT contract is unchanged, so this is a one-file edit.

## Things the SoftPLC must implement

Conformance checklist for any candidate SoftPLC runtime:

* MQTT 3.1.1 client (Mosquitto is 3.1.1 + 5.0 capable).
* JSON encode/decode (Codesys IIoT Library, OpenPLC `pymqtt`, etc.).
* Subscribe `robot/status` with **retain handling = send retained at
  subscribe**; gate command publishes on `state == "online"`.
* Honor watchdog: publish `robot/cmd_vel` at ≥ 1 / `WATCHDOG_SEC`
  while a non-zero command is active. Idle = explicit zero command.
* Apply own clamps, but the bridge will re-clamp defensively.

## What does NOT change between phases

* `gazebo/worlds/diff_drive.world` and its diff_drive plugin.
* `ros2_bridge` package, image, or environment defaults.
* MQTT topic names, QoS, payload schemas.

This is the invariant that makes the migration low-risk.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Two writers on `robot/cmd_vel` during Phase 2. | Operational discipline + add `robot/mode` ACLs once auth is enabled. |
| PLC vendor MQTT client is QoS-1 only on subscribe but QoS-0 on publish. | Acceptable — bridge clamps and watchdog absorb drops. |
| PLC clock skew with `/clock`. | PLC uses wall-clock for control loop; bridge republishes at fixed `PUBLISH_HZ` so jitter is absorbed. |
| Need to introduce a breaking schema change. | Use `robot/v2/cmd_vel` in parallel for one release. |
