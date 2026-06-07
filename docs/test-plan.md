# Test Plan

QA owns this document. Each scenario lists the steps, the expected
result, and the commands a human can run to verify.

Prereqs: stack is up (`docker compose up -d`), all four containers in
`docker compose ps` show `running`/`healthy`.

A handy one-liner subscriber for any human watcher:

```bash
docker compose exec mosquitto mosquitto_sub -v -t 'robot/#'
```

## T1 — Happy-path drive (golden path)

| Step | Action | Expected |
|---|---|---|
| 1 | Open `http://127.0.0.1:1880/ui` | Dashboard renders Drive, Speed, Telemetry groups. |
| 2 | Set Speed slider = 1.0 | No movement yet (button required). |
| 3 | Click "Forward" | `robot/cmd_vel` carries `{"linear_x":1,"angular_z":0}`. |
| 4 | Watch Telemetry | `Bridge: online`, `Odom: x=… y=… v=…` increasing. |
| 5 | Click "Stop" | Robot decelerates to rest; odom `v` → 0. |
| 6 | Click "Left" then "Right" | `angular_z` flips sign, `linear_x` = 0. |
| 7 | Click "Backward" | `linear_x` = -1, robot reverses. |

Verify command translation with:

```bash
docker compose exec ros2_bridge bash -lc \
  'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
   && ros2 topic echo /cmd_vel --once'
```

## T2 — MQTT command validation

| # | Input on `robot/cmd_vel` | Expected on `/cmd_vel` |
|---|---|---|
| 2.1 | `{"linear_x":0.5,"angular_z":0.5}` | `linear.x=0.5, angular.z=0.5` |
| 2.2 | `{"linear_x":99,"angular_z":0}` | clamped: `linear.x=2.0` (MAX_LINEAR) |
| 2.3 | `{"linear_x":"oops"}` | nothing; bridge logs `bad numeric fields`. |
| 2.4 | non-JSON bytes | nothing; bridge logs `bad JSON on robot/cmd_vel`. |
| 2.5 | `{"linear_x":NaN,"angular_z":0}` (raw) | nothing; bridge logs `non-finite command rejected`. |

Send with:

```bash
docker compose exec mosquitto mosquitto_pub -t robot/cmd_vel \
    -m '{"linear_x":99,"angular_z":0}'
```

## T3 — Watchdog (command timeout)

| Step | Action | Expected |
|---|---|---|
| 1 | Publish a moving command, wait > `WATCHDOG_SEC` (default 1.0 s). | `/cmd_vel` returns to zero; odom velocities decay to 0. |
| 2 | Inspect `robot/alarm`. | Single `WATCHDOG_TIMEOUT` event. |
| 3 | Publish a new command. | Single `WATCHDOG_CLEAR` event. |

```bash
docker compose exec mosquitto mosquitto_sub -t 'robot/alarm' -v &
docker compose exec mosquitto mosquitto_pub -t robot/cmd_vel -m '{"linear_x":0.5}'
sleep 2  # exceeds watchdog
```

## T4 — Broker outage

| Step | Action | Expected |
|---|---|---|
| 1 | `docker compose stop mosquitto` | Bridge logs `MQTT disconnected`. Within `WATCHDOG_SEC`, `/cmd_vel` is forced to zero. |
| 2 | `docker compose start mosquitto` | Bridge reconnects (backoff up to 30 s). On reconnect, `robot/status` is re-published as `online`. |
| 3 | Dashboard reloads `/ui` | Buttons resume working. |

While the broker is down, the Last Will retains: on next subscriber
connect, the first delivered `robot/status` is `{"state":"offline"}`,
then `online` arrives after the bridge republishes.

## T5 — Bridge outage

| Step | Action | Expected |
|---|---|---|
| 1 | `docker compose stop ros2_bridge` | Mosquitto publishes the LWT: `robot/status = {"state":"offline"}` (retained). Dashboard "Bridge" pill flips to offline. |
| 2 | Commands keep being published from the dashboard. | No effect on Gazebo (robot stays still). No errors in `gazebo` container. |
| 3 | `docker compose start ros2_bridge` | `robot/status` flips back to `online`. Robot responds again. |

## T6 — Gazebo outage

| Step | Action | Expected |
|---|---|---|
| 1 | `docker compose stop gazebo` | `/cmd_vel` is still published by the bridge but goes unconsumed. No alarms (this is intentional for v1; see backlog). |
| 2 | `docker compose start gazebo` | Robot resumes responding within a few seconds of `/cmd_vel`. |

Backlog: a future `GAZEBO_UNREACHABLE` alarm could be added by having
the bridge time-out on missing `/odom`.

## T7 — Smoke test from the shell

End-to-end without the dashboard:

```bash
docker compose exec mosquitto mosquitto_pub -t robot/cmd_vel \
    -m '{"linear_x":1.0,"angular_z":0.0}'

docker compose exec ros2_bridge bash -lc \
  'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
   && ros2 topic echo /odom --once' | grep -E 'linear|x:'
```

Expected: `linear.x` > 0 and `pose.position.x` advancing.

## Pass criteria

* T1, T2, T3, T4, T5 pass on a clean checkout via `docker compose up`.
* T6 demonstrates graceful degradation (no crashes).
* T7 succeeds without the dashboard, proving MQTT is the only contract.
