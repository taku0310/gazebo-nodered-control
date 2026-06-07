# gazebo-nodered-control

Node-RED → MQTT → ROS 2 → Gazebo で動作する制御デモシステムです。

```
Node-RED ダッシュボード  ──►  Mosquitto  ──►  mqtt_ros2_bridge (ROS 2)  ──►  Gazebo
                                  ▲                  │
                                  └──── robot/status, robot/odom, robot/alarm
```

MQTT のトピック設計が**唯一の制御インターフェース**です。
現時点では Node-RED が手動操作 UI を担っていますが、将来 SoftPLC が同じ
JSON を送信するだけで ROS 2 側に一切の変更なく置換できます。
詳細は [`docs/softplc-migration.md`](docs/softplc-migration.md) を参照してください。

## ディレクトリ構成

```
.
├── docker-compose.yml          # ワンコマンド起動用
├── .env.example                # コピーして .env で上書き
├── docs/
│   ├── architecture.md         # システム構成図・データフロー図
│   ├── mqtt-spec.md            # MQTT 仕様書
│   ├── topics.md               # MQTT + ROS 2 トピック一覧
│   ├── test-plan.md            # QA テスト手順
│   └── softplc-migration.md    # SoftPLC 移行計画
├── mosquitto/config/           # ブローカー設定
├── nodered/
│   ├── Dockerfile              # Node-RED + node-red-dashboard
│   └── flows.json              # インポート可能な Dashboard フロー
├── ros2_bridge/
│   ├── Dockerfile              # ros:humble + paho-mqtt + ワークスペース
│   └── ws/src/mqtt_ros2_bridge # ブリッジノードパッケージ
└── gazebo/
    ├── Dockerfile              # ros:humble + Gazebo Fortress + Xvfb/x11vnc/noVNC
    ├── entrypoint.sh           # Xvfb / x11vnc / websockify を起動
    ├── launch/gazebo.launch.py # ign gazebo + ros_gz_bridge
    ├── config/ros_gz_bridge.yaml # /cmd_vel と /odom のブリッジ定義
    └── worlds/diff_drive.sdf   # SDF 1.9 + ignition-gazebo-diff-drive-system
```

> Gazebo は **Fortress (Gazebo Sim 6.x)** を採用しています。ROS 2 Humble
> でバイナリインストール可能な「新 Gazebo」は Fortress までで、Harmonic
> を Humble と組み合わせる場合は ros_gz をソースビルドする必要があります。
> Fortress は Harmonic と同じ gz transport / OGRE2 / `gz sim` アーキ
> テクチャを採用しており、見た目・操作感はほぼ同一です。

## 動作要件

* Docker Engine 24 以上 + Compose v2
* 初回ビルド用に約 4 GB のディスク空き容量
* （任意）Gazebo の GUI (`gzclient`) を表示する場合はホスト側に X11 サーバー

## 起動手順

```bash
cp .env.example .env             # 任意。デフォルトのままでも動作します
docker compose up --build -d
```

4 つのコンテナが立ち上がるまで待ちます（初回はイメージのプル + ビルドで
ネットワーク次第 5 分程度かかります）。

```bash
docker compose ps
```

ダッシュボードを **http://127.0.0.1:1880/ui** で開きます。
シミュレータの 3D ビューは **http://127.0.0.1:8080/vnc.html** で開きます
（パスワード未設定のまま「Connect」をクリック）。

方向ボタンをクリックすると "Bridge" が `online` になり、"Odom" の値が更新され、
3D ビュー内でロボットが移動します。

## 停止手順

```bash
docker compose down              # ボリュームは残す
docker compose down -v           # ブローカー / Node-RED の状態も削除
```

## 操作方法

| 動作 | UI ボタン | 送信される MQTT ペイロード |
|---|---|---|
| 前進  | ▲ | `{"linear_x": +speed, "angular_z": 0}` |
| 後退  | ▼ | `{"linear_x": -speed, "angular_z": 0}` |
| 左旋回 | ◀ | `{"linear_x": 0, "angular_z": +speed}` |
| 右旋回 | ▶ | `{"linear_x": 0, "angular_z": -speed}` |
| 停止   | ■ | `{"linear_x": 0, "angular_z": 0}` |

`speed` は Speed スライダーで設定します（既定 1.0、範囲 0〜2）。

ダッシュボードを経由せず `mosquitto_pub` で直接 MQTT 契約を検証できます。

```bash
docker compose exec mosquitto mosquitto_pub \
    -t robot/cmd_vel -m '{"linear_x":0.5,"angular_z":0.0}'
docker compose exec mosquitto mosquitto_sub -v -t 'robot/#'
```

ブリッジコンテナの内側から ROS 2 側を確認する場合は次のとおりです。

```bash
docker compose exec ros2_bridge bash -lc \
    'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
     && ros2 topic echo /cmd_vel --once'
```

## Gazebo の表示

Gazebo Fortress の GUI はコンテナ内の Xvfb（仮想ディスプレイ）に出力され、
`x11vnc` + `noVNC` 経由でブラウザに配信されます。

* ブラウザで **http://127.0.0.1:8080/vnc.html** を開いて「Connect」
  （パスワードなし）。
* 解像度を変えたい場合は `.env` の `XVFB_RESOLUTION` を変更
  （例: `1920x1080x24`）。
* GPU パススルー（Linux + NVIDIA Container Toolkit）が使える場合は
  `.env` で `LIBGL_ALWAYS_SOFTWARE=0` にしてハードウェアアクセラレーション
  に切替可能。

Mac / Windows でも追加ソフト不要。XQuartz や VcXsrv は不要です。

## テスト

手動テストの手順は [`docs/test-plan.md`](docs/test-plan.md) にあります。
正常系、ペイロード検証、ウォッチドッグ、ブローカー / ブリッジ / Gazebo
それぞれの停止試験を網羅しています。

## 設定項目

調整可能な項目はすべて `ros2_bridge` サービスの環境変数として公開しています。
一覧は [`docs/architecture.md`](docs/architecture.md#4-設定項目) を参照してください。

## 参考リポジトリ (`gazebo-keyboard-control`) との差分

| 元リポジトリ | 本リポジトリ |
|---|---|
| `keyboard_input` が TCP で送信 | Node-RED Dashboard が MQTT で送信 |
| `control_logic` コンテナがクランプ・スムージングを担当 | クランプとウォッチドッグはブリッジ内に統合し、専用コンテナを廃止 |
| ROS 2 Jazzy + Gazebo Harmonic | ROS 2 Humble + Gazebo Fortress（`ros_gz_bridge` 経由） |
| TCP 境界 | MQTT 境界。同じブローカーに将来 SoftPLC を接続可能 |

## ライセンス

Apache-2.0（参考リポジトリと同一）
