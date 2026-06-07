# gazebo コンテナ

ROS 2 Humble + **Gazebo Fortress (Gazebo Sim 6.x)** + `ros_gz_bridge` を
1 コンテナで起動し、3D ビューを **noVNC でブラウザ配信**する。
MQTT は一切扱わず、外部とは ROS 2 の `/cmd_vel` と `/odom` のみで会話する。

## 役割

| 担当 | 説明 |
|---|---|
| ロボットシミュレーション | SDF で定義した差動駆動ロボットを DART 物理エンジンで実行 |
| gz transport ↔ ROS 2 翻訳 | `ros_gz_bridge` が `/cmd_vel` と `/odom` を双方向にマップ |
| 3D ビューのブラウザ配信 | Xvfb 仮想ディスプレイ + x11vnc + noVNC websockify |

## ファイル構成

| ファイル | 役割 |
|---|---|
| `Dockerfile` | OSRF apt から `ignition-fortress` / `ros-humble-ros-gz` と Xvfb / x11vnc / noVNC を導入 |
| `entrypoint.sh` | Xvfb (:1) → x11vnc (:5900) → websockify (:8080) を順に起動して CMD を `exec` |
| `launch/gazebo.launch.py` | `ign gazebo -r ...` と `ros_gz_bridge parameter_bridge` を起動 |
| `worlds/diff_drive.sdf` | SDF 1.9 — 地面 / 光源 / 差動駆動ロボット + `ignition::gazebo::systems::DiffDrive` |
| `config/ros_gz_bridge.yaml` | `/cmd_vel`（Twist）と `/odom`（Odometry）を双方向にマップ |

## コンポーネント図

```mermaid
flowchart LR
    Browser[ブラウザ]

    subgraph container["gazebo コンテナ"]
      direction LR
      W[websockify :8080]
      V[x11vnc :5900]
      X[Xvfb :1]
      G[ign gazebo<br/>Fortress 6.17]
      P[ros_gz_bridge<br/>parameter_bridge]
    end

    Other[ros2_bridge コンテナ]

    Browser -- "WebSocket" --> W
    W --> V
    V --> X
    X -- "DISPLAY=:1" --> G
    G <-- "gz transport<br/>/cmd_vel /odom" --> P
    P <-- "ROS 2 DDS<br/>/cmd_vel /odom" --> Other
```

## シーケンス図 — 起動

```mermaid
sequenceDiagram
    autonumber
    participant CMP as docker compose
    participant EP as entrypoint.sh
    participant XV as Xvfb
    participant VN as x11vnc
    participant WS as websockify
    participant LCH as ros2 launch
    participant GZ as ign gazebo
    participant RGB as ros_gz_bridge

    CMP->>EP: ENTRYPOINT /entrypoint.sh CMD=ros2 launch ...
    EP->>XV: Xvfb :1 -screen 0 1280x800x24
    EP->>XV: xdpyinfo で疎通確認 (≤3s)
    EP->>VN: x11vnc -display :1 -rfbport 5900
    EP->>WS: websockify --web=/usr/share/novnc 8080
    EP->>LCH: source ROS && exec ros2 launch ...
    LCH->>GZ: ExecuteProcess(ign gazebo -r diff_drive.sdf)
    LCH->>RGB: Node parameter_bridge --config-file
    RGB-->>GZ: gz transport subscribe /odom
    RGB-->>GZ: gz transport advertise /cmd_vel
    Note over GZ: GUI が DISPLAY=:1 に描画開始
```

## シーケンス図 — ランタイム（指令と odom）

```mermaid
sequenceDiagram
    autonumber
    participant RB as ros2_bridge
    participant RGB as ros_gz_bridge
    participant DD as DiffDrive system
    participant PH as 物理シミュ
    participant BR as ブラウザ

    RB->>RGB: ROS /cmd_vel (geometry_msgs/Twist) @ 20Hz
    RGB->>DD: gz /cmd_vel (ignition.msgs.Twist)
    DD->>PH: 左右車輪に角速度を印加
    PH-->>DD: ステップ計算で位置を更新
    DD->>RGB: gz /odom (ignition.msgs.Odometry) @ 30Hz
    RGB->>RB: ROS /odom (nav_msgs/Odometry)
    PH-->>BR: シーンを Xvfb に描画 → noVNC → ブラウザに反映
```

## アクティビティ図 — `entrypoint.sh`

```mermaid
flowchart TD
    A([開始]) --> B[Xvfb :1 をバックグラウンド起動]
    B --> C{xdpyinfo で<br/>X 疎通 OK?}
    C -- "成功" --> D
    C -- "3 秒経過<br/>でも続行" --> D[x11vnc を起動]
    D --> E[websockify 起動]
    E --> F[/opt/ros/humble/setup.bash を source]
    F --> G["exec ""$@"" で CMD を前景化"]
    G --> H([CMD の終了で終了])
```

## 状態遷移図 — 差動駆動ロボットの動作状態

```mermaid
stateDiagram-v2
    [*] --> Idle: world ロード完了
    Idle --> Driving: /cmd_vel に非ゼロ指令
    Driving --> Driving: 指令を継続受信
    Driving --> Decelerating: /cmd_vel = (0, 0)
    Decelerating --> Idle: 静止判定
    Idle --> [*]: コンテナ停止
    Driving --> [*]: コンテナ停止
```

## ユースケース図

```mermaid
flowchart LR
    Op([操作者]):::actor
    Mon([監視者]):::actor
    Br([ros2_bridge]):::actor

    subgraph gazebo["gazebo コンテナ"]
      UC1((指令を受けて<br/>ロボットを動かす))
      UC2((3D ビューを<br/>ブラウザに配信))
      UC3((odom を<br/>発行する))
    end

    Op --> UC1
    Mon --> UC2
    Br --> UC1
    Br --> UC3

    classDef actor stroke:#1E88E5,stroke-width:2px,fill:#0e1117,color:#fff;
```

## 公開インターフェース

| インターフェース | 方向 | 内容 |
|---|---|---|
| ホスト `:8080` (HTTP/WebSocket) | in  | noVNC ビューアー (`/vnc.html`) |
| ROS 2 `/cmd_vel` (`geometry_msgs/Twist`) | in  | 速度指令 |
| ROS 2 `/odom` (`nav_msgs/Odometry`) | out | 走行オドメトリ |

## 環境変数

| 変数 | 既定値 | 用途 |
|---|---|---|
| `ROS_DOMAIN_ID` | `42` | ros2_bridge と同一にする |
| `RMW_IMPLEMENTATION` | `rmw_cyclonedds_cpp` | DDS 実装 |
| `DISPLAY` | `:1` | Xvfb の表示先 |
| `LIBGL_ALWAYS_SOFTWARE` | `1` | ソフトウェア OpenGL (llvmpipe) |
| `OGRE_RTT_MODE` | `Copy` | Xvfb 環境向けの OGRE2 設定 |
| `XVFB_RESOLUTION` | `1280x800x24` | 仮想ディスプレイ解像度 |

## トラブルシューティング

| 症状 | 原因 / 対処 |
|---|---|
| 3D ビューが真っ黒 | OGRE2 + llvmpipe の初期化に 10〜20 秒かかる。マウスをドラッグして強制再描画 |
| Anti-aliasing warning | 無害。FSAA=0 にフォールバック |
| `Loading world file [/sim/worlds/diff_drive.world]` | 古いイメージ。`docker compose build --no-cache gazebo` |
| `platform (linux/amd64) does not match host (linux/arm64)` | 古い amd64 イメージが残存。同上 |
