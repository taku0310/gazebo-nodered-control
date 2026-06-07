# ros2_bridge コンテナ

`mqtt_ros2_bridge` ROS 2 ノードを 1 個だけ動かすコンテナ。
MQTT 側（クライアントの世界）と ROS 2 側（シミュレータの世界）を翻訳し、
ウォッチドッグ・クランプ・retained ステータス・アラーム発行を担う。

**設計上の重要な性質:**
- MQTT 契約は不変（Node-RED でも SoftPLC でも同じ JSON で動く）
- ROS 2 契約も不変（Gazebo Classic でも Fortress でも `/cmd_vel` と `/odom`）
- このノードが「2 つの世界の唯一の境界」

## 役割

| 担当 | 説明 |
|---|---|
| MQTT → ROS 翻訳 | `robot/cmd_vel` JSON → `geometry_msgs/Twist` を `PUBLISH_HZ` で再送 |
| ROS → MQTT 翻訳 | `/odom` `nav_msgs/Odometry` → `robot/odom` JSON を `ODOM_THROTTLE_HZ` で間引いて発行 |
| クランプ | `±MAX_LINEAR` / `±MAX_ANGULAR` で速度を制限 |
| ウォッチドッグ | `WATCHDOG_SEC` 無入力でゼロ速度に強制 + `WATCHDOG_TIMEOUT` 発行 |
| ステータス通知 | 接続成功時に `robot/status: online` を retained、異常終了時は LWT が `offline` |
| ペイロード検証 | 非 JSON / 数値以外 / NaN・Inf をログとともに拒否 |

## ファイル構成

| ファイル | 役割 |
|---|---|
| `Dockerfile` | `ros:humble-ros-base` に `python3-paho-mqtt` と CycloneDDS を追加、ワークスペースをビルド |
| `entrypoint.sh` | `/opt/ros/humble/setup.bash` と `/ws/install/setup.bash` を source して CMD を `exec` |
| `ws/src/mqtt_ros2_bridge/` | ament_python の ROS 2 パッケージ |
| └ `mqtt_ros2_bridge/bridge_node.py` | 本体（200 行弱、依存は標準ライブラリ + rclpy + paho-mqtt） |
| └ `launch/bridge.launch.py` | `Node(bridge_node)` を起動するだけのランチャ |
| └ `package.xml`, `setup.py`, `setup.cfg` | パッケージメタ |

## コンポーネント図

```mermaid
flowchart LR
    MB[(mosquitto)]
    DDS[(ROS 2 DDS<br/>CycloneDDS)]

    subgraph container["ros2_bridge コンテナ"]
      direction TB
      subgraph node["mqtt_ros2_bridge ノード"]
        direction TB
        MC[paho-mqtt Client<br/>ネットワークスレッド]
        OC[/odom コールバック<br/>rclpy 実行スレッド/]
        TM["20Hz タイマー (_tick)<br/>rclpy 実行スレッド"]
        LK[/threading.Lock<br/>_last_cmd, _last_cmd_time/]
        PUB[Twist Publisher<br/>/cmd_vel]
      end
    end

    MB -- "robot/cmd_vel" --> MC
    MC -- "store cmd" --> LK
    TM -- "read" --> LK
    TM -- "publish" --> PUB
    PUB -- "Twist" --> DDS
    DDS -- "Odometry" --> OC
    OC -- "publish" --> MC
    MC -- "robot/odom robot/status robot/alarm" --> MB
```

## シーケンス図 — 通常時の指令往復

```mermaid
sequenceDiagram
    autonumber
    participant NR as nodered
    participant MB as mosquitto
    participant MC as paho-mqtt
    participant LK as Lock
    participant TM as 20Hz Timer
    participant DDS as DDS
    participant GZ as gazebo

    NR->>MB: PUBLISH robot/cmd_vel<br/>{"linear_x":1.0,"angular_z":0}
    MB->>MC: on_message
    MC->>MC: parse + clamp + isfinite チェック
    MC->>LK: acquire → _last_cmd=(1.0,0.0)<br/>_last_cmd_time=now → release
    loop @20Hz
        TM->>LK: acquire → cmd,t = state → release
        TM->>TM: stale = (now-t) > 1.0s?
        TM->>DDS: publish Twist(linear.x=1.0)
    end
    DDS->>GZ: /cmd_vel 配送
```

## シーケンス図 — ウォッチドッグ発火と解除

```mermaid
sequenceDiagram
    autonumber
    participant TM as 20Hz Timer
    participant LK as Lock
    participant MC as paho-mqtt
    participant MB as mosquitto

    Note over TM: _alarm_active = false
    TM->>LK: 直近の cmd は 0.6s 前
    Note over TM: stale = false
    TM->>TM: Twist 公開 (last_cmd 維持)

    Note over TM: 入力が途絶え、1 秒経過...

    TM->>LK: 直近の cmd は 1.2s 前
    Note over TM: stale = true & ever_received = true
    TM->>MC: PUBLISH robot/alarm<br/>{code:"WATCHDOG_TIMEOUT"}
    MC->>MB: PUBLISH (QoS=1)
    Note over TM: _alarm_active = true
    TM->>TM: Twist 公開 (0, 0)

    Note over TM: 新たな指令が到着

    TM->>LK: stale = false
    Note over TM: _alarm_active なので CLEAR を発行
    TM->>MC: PUBLISH robot/alarm<br/>{code:"WATCHDOG_CLEAR"}
    Note over TM: _alarm_active = false
```

## アクティビティ図 — `_tick()`（20Hz 周期処理）

```mermaid
flowchart TD
    A([タイマー発火]) --> B[Lock 取得して<br/>cmd, last_t をコピー]
    B --> C[ever_received = last_t > 0]
    C --> D{stale = now-last_t > watchdog?}
    D -- "yes" --> E[cmd = 0, 0]
    E --> F{ever_received<br/>かつ NOT alarm_active?}
    F -- "yes" --> G[robot/alarm に<br/>WATCHDOG_TIMEOUT 発行]
    G --> H[alarm_active = true]
    F -- "no" --> H
    D -- "no" --> I{alarm_active?}
    I -- "yes" --> J[robot/alarm に<br/>WATCHDOG_CLEAR 発行]
    J --> K[alarm_active = false]
    I -- "no" --> K
    H --> L[Twist を組み立てて<br/>/cmd_vel に publish]
    K --> L
    L --> END([次の発火を待機])
```

## 状態遷移図 — ウォッチドッグ

```mermaid
stateDiagram-v2
    [*] --> WaitingFirst: 起動直後 _last_cmd_time=0
    WaitingFirst --> Active: 有効な robot/cmd_vel
    Active --> Active: WATCHDOG_SEC 以内に再受信
    Active --> Alarmed: WATCHDOG_SEC 経過<br/>WATCHDOG_TIMEOUT 発行
    Alarmed --> Alarmed: stale 継続中 Twist=0 を送り続ける
    Alarmed --> Active: 新たな指令<br/>WATCHDOG_CLEAR 発行
    WaitingFirst --> WaitingFirst: stale でも<br/>TIMEOUT は発火しない
    WaitingFirst --> [*]
    Active --> [*]
    Alarmed --> [*]
```

## 状態遷移図 — MQTT 接続

```mermaid
stateDiagram-v2
    [*] --> Disconnected: ノード起動
    Disconnected --> Connecting: connect_async
    Connecting --> Connected: CONNACK rc=0
    Connecting --> Disconnected: rc≠0<br/>1〜30s バックオフ
    Connected --> Connected: keepalive 30s
    Connected --> Disconnected: 切断検知<br/>自動再接続
    Connected --> [*]: ノード停止
    Disconnected --> [*]
```

## ユースケース図

```mermaid
flowchart LR
    Cli([制御クライアント<br/>nodered / SoftPLC]):::actor
    Sim([シミュレータ<br/>gazebo]):::actor
    Mon([監視者]):::actor

    subgraph rb["ros2_bridge コンテナ"]
      UC1((指令を<br/>変換 & 再送))
      UC2((odom を<br/>橋渡し))
      UC3((ウォッチドッグで<br/>安全停止))
      UC4((ステータスを<br/>retained 通知))
      UC5((異常入力を<br/>拒否 & ログ))
    end

    Cli --> UC1
    Cli --> UC4
    Sim --> UC2
    Mon --> UC4
    Cli --> UC3
    Mon --> UC3
    Cli --> UC5

    classDef actor stroke:#1E88E5,stroke-width:2px,fill:#0e1117,color:#fff;
```

## 公開インターフェース

| インターフェース | 方向 | 内容 |
|---|---|---|
| MQTT `robot/cmd_vel` (Sub QoS=1) | in  | 指令 JSON |
| ROS 2 `/cmd_vel` (Pub) | out | `geometry_msgs/Twist` を 20Hz で再送 |
| ROS 2 `/odom` (Sub) | in  | `nav_msgs/Odometry` |
| MQTT `robot/status` (Pub QoS=1, retained, LWT) | out | `online`/`offline` |
| MQTT `robot/odom` (Pub QoS=0) | out | テレメトリ JSON |
| MQTT `robot/alarm` (Pub QoS=1) | out | `WATCHDOG_TIMEOUT` / `WATCHDOG_CLEAR` |

## 環境変数

| 変数 | 既定値 | 意味 |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `mosquitto` / `1883` | ブローカー |
| `MQTT_CMD_TOPIC` | `robot/cmd_vel` | 指令受信トピック |
| `MQTT_STATUS_TOPIC` | `robot/status` | retained ステータス |
| `MQTT_ODOM_TOPIC` | `robot/odom` | テレメトリ送信 |
| `MQTT_ALARM_TOPIC` | `robot/alarm` | アラーム送信 |
| `ROS_CMD_VEL_TOPIC` | `/cmd_vel` | ROS パブリッシャ |
| `ROS_ODOM_TOPIC` | `/odom` | ROS サブスクライバ |
| `WATCHDOG_SEC` | `1.0` | 指令タイムアウト |
| `MAX_LINEAR` / `MAX_ANGULAR` | `2.0` / `2.0` | クランプ上限 |
| `PUBLISH_HZ` | `20.0` | `/cmd_vel` 再送頻度 |
| `ODOM_THROTTLE_HZ` | `5.0` | MQTT odom の上限頻度 |
| `ROS_DOMAIN_ID` | `42` | gazebo と同一にする |
| `RMW_IMPLEMENTATION` | `rmw_cyclonedds_cpp` | DDS 実装 |

## スレッドモデルと安全性

| スレッド | 所有データ | 共有データ |
|---|---|---|
| paho-mqtt loop_start | — | `_last_cmd`, `_last_cmd_time`（Lock 越し書込） |
| rclpy executor (timer) | `_alarm_active` | `_last_cmd`, `_last_cmd_time`（Lock 越し読出） |
| rclpy executor (sub) | `_last_odom_pub` | — |

- `Twist` の publish と `_alarm_active` の遷移は同じ rclpy スレッドで行うので
  ロック不要。
- `paho-mqtt.publish` は内部でキューイング + スレッドセーフ。複数スレッドから
  呼び出して安全。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `MQTT connect failed rc=…` | ブローカー未起動 / DNS で `mosquitto` 引けない。`docker compose logs mosquitto` |
| `non-finite command rejected` | クライアントが `NaN` / `Infinity` を送ってきている |
| `bad JSON on robot/cmd_vel` | JSON でないバイト列。ペイロード送信元を確認 |
| Twist は流れているのに Gazebo で動かない | `ROS_DOMAIN_ID` 不一致、または gazebo の `ros_gz_bridge` 未起動 |
| odom が MQTT に流れない | `/odom` が ROS 側に出ていない。`ros2 topic echo /odom` で確認 |
