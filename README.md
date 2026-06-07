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
* モダンなブラウザ（Gazebo 3D ビューは noVNC でブラウザに直接配信。
  XQuartz や VcXsrv などホスト側 X11 サーバーは不要）

## 起動手順

### 初回起動

```bash
git clone <repository-url>
cd gazebo-nodered-control

cp .env.example .env             # 任意。デフォルトのままで動作します
docker compose up --build -d     # 4 サービスをビルド + 起動
```

初回はイメージのプルとビルドにネットワーク次第 5〜10 分かかります
（Apple Silicon Mac でもネイティブ arm64 でビルドされます）。

起動完了の確認:

```bash
docker compose ps
# 4 サービス (mosquitto / nodered / ros2_bridge / gazebo) が
# 全て STATUS=Up になっていれば OK

docker compose logs --tail=20 gazebo
# 末尾に Ignition Gazebo の plugin ロード成功ログが出ていれば OK

docker compose logs --tail=10 ros2_bridge
# `MQTT connected` と `bridge ready` の 2 行が出ていれば OK
```

開く URL:

| 用途 | URL | 備考 |
|---|---|---|
| ダッシュボード | http://127.0.0.1:1880/ui | 操作 UI |
| 3D ビュー（Gazebo） | http://127.0.0.1:8080/vnc.html | 「Connect」クリック、パスワードなし |
| Node-RED エディタ | http://127.0.0.1:1880 | フロー編集（任意） |

方向ボタンをクリックすると BRIDGE バッジが緑の `ONLINE` で脈動し、
TELEMETRY の `POSE` / `LIN.X` / `ANG.Z` が更新され、3D ビュー内で
ロボットが移動します。

### 2 回目以降の起動

```bash
docker compose up -d             # ビルド済みイメージを使うので数秒で起動
```

> ⚠ `Dockerfile` / `entrypoint.sh` / `gazebo/worlds/*.sdf` などを変更した
> 場合は `docker compose up -d --build` を使ってください。`up -d` のみだと
> キャッシュされた古いイメージで起動してしまいます。詳細は[運用方法 §
> ビルド・更新ワークフロー](#ビルド更新ワークフロー)を参照。

## 停止手順

```bash
docker compose stop              # コンテナだけ停止、状態は保持。再起動は `start`
docker compose down              # コンテナとネットワークを削除、ボリュームは残す
docker compose down -v           # ブローカー / Node-RED の永続化データも削除
```

## 操作方法

| 動作 | UI ボタン | 送信される MQTT ペイロード |
|---|---|---|
| 前進  | ▲ FORWARD  | `{"linear_x": +speed, "angular_z": 0}` |
| 後退  | ▼ BACKWARD | `{"linear_x": -speed, "angular_z": 0}` |
| 左旋回 | ◀ LEFT     | `{"linear_x": 0, "angular_z": +speed}` |
| 右旋回 | ▶ RIGHT    | `{"linear_x": 0, "angular_z": -speed}` |
| 停止   | ■ STOP     | `{"linear_x": 0, "angular_z": 0}` |

`speed` は SPEED スライダーで設定します（既定 1.0、範囲 0〜2、0.1 刻み）。
波形ゲージにライブで反映されます。
STOP 後 1 秒指令が無いとウォッチドッグが作動し、TELEMETRY の
`LATEST ALARM` カードに `WATCHDOG_TIMEOUT` が表示されます（次の
操作で `WATCHDOG_CLEAR` に切替）。

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

## 運用方法

### サービス構成と役割

| サービス | 役割 | 公開ポート (host) | 永続化ボリューム |
|---|---|---|---|
| `mosquitto` | MQTT ブローカー (1883) + WebSocket (9001) | 1883, 9001 | `mosquitto_data`, `mosquitto_log` |
| `nodered` | ダッシュボード UI + フローエンジン | 1880 | `nodered_data` |
| `ros2_bridge` | MQTT ↔ ROS 2 ブリッジ + ウォッチドッグ | — | なし |
| `gazebo` | Gazebo Fortress + ros_gz_bridge + noVNC | 8080 | なし |

### ログ確認

```bash
docker compose logs -f                       # 全サービスを追従
docker compose logs -f ros2_bridge gazebo    # 2 サービスだけ
docker compose logs --tail=100 nodered       # 直近 100 行
```

ブリッジが出力する代表的なログ:

| メッセージ | 意味 |
|---|---|
| `MQTT connected` | ブローカー接続成功 |
| `bridge ready: mqtt=... ros_cmd=/cmd_vel` | 起動完了 |
| `MQTT disconnected rc=...` | ブローカー切断（自動再接続） |
| `watchdog: publishing zero velocity` | 指令が来ない → 強制ゼロ化 |
| `bad JSON on robot/cmd_vel` | ペイロード破損 |
| `non-finite command rejected` | `NaN` / `Inf` を含む指令を拒否 |

### 健全性チェック

```bash
# MQTT が生きているか
docker compose exec mosquitto mosquitto_pub -t healthcheck -m ping

# 全 robot/* トピックを観測
docker compose exec mosquitto mosquitto_sub -v -t 'robot/#'
# 出力例:
#   robot/status {"state":"online"}
#   robot/odom {"x":0.0,"y":0.0,"linear_x":0.0,"angular_z":0.0}

# ROS 2 側
docker compose exec ros2_bridge bash -lc \
  'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
   && ros2 topic list'
# /cmd_vel, /odom, /parameter_events, /rosout が見えれば OK
```

### 個別サービスの再起動

```bash
docker compose restart nodered          # フロー再読込
docker compose restart ros2_bridge      # ウォッチドッグ / ブリッジ再起動
docker compose restart gazebo           # 3D ビュー含めて再起動（〜5 秒）
```

`mosquitto` を再起動するとブリッジは数秒でバックオフ付き再接続し、
`robot/status` を `online` に戻します。Last Will により再接続まで
`offline` が retained で配信されるので、ダッシュボードの BRIDGE バッジで
切替を観測できます。

### Node-RED フローの更新

`nodered/flows.json` を編集して即時反映する場合:

```bash
docker compose restart nodered
```

ブラウザ上のエディタ (http://127.0.0.1:1880) で編集 → 「Deploy」した
変更は `nodered_data` ボリュームに保存され、`docker compose down` でも
残ります。リポジトリの `flows.json` に書き戻したい場合:

```bash
docker compose cp nodered:/data/flows.json nodered/flows.json
git diff nodered/flows.json
```

<a id="ビルド更新ワークフロー"></a>
### ビルド・更新ワークフロー

| 変更内容 | 必要な操作 |
|---|---|
| `flows.json` のみ | `docker compose restart nodered` |
| `mqtt_ros2_bridge/**.py` | `docker compose up -d --build ros2_bridge` |
| `gazebo/worlds/*.sdf` または launch / config | `docker compose up -d --build gazebo` |
| `Dockerfile`、`entrypoint.sh` | `docker compose build --no-cache <service>` → `up -d` |
| `docker-compose.yml`、`.env` | `docker compose up -d`（コンテナ再作成） |

`up -d` 単体ではイメージが再ビルドされないため、Dockerfile を編集した
ときは必ず `--build` または `build` を明示してください。

### MQTT 経由でロボットを直接動かす（ダッシュボード不要）

```bash
docker compose exec mosquitto mosquitto_pub \
    -t robot/cmd_vel -m '{"linear_x":0.5,"angular_z":0.3}'

docker compose exec mosquitto mosquitto_sub -v -t 'robot/#'
```

これだけで Gazebo 内のロボットが旋回しながら前進します。
**MQTT が唯一の制御契約**であることを実証できます。

### トラブルシューティング

| 症状 | 原因の可能性 | 対処 |
|---|---|---|
| `gazebo` のログが古い (`gzserver`, Classic 11 など) | `up -d` でキャッシュされた旧イメージを使用 | `docker compose down && docker compose build --no-cache gazebo && docker compose up -d` |
| `platform (linux/amd64) does not match host (linux/arm64/v8)` | 古い amd64 イメージが残存 | 上記と同じ |
| ダッシュボードのアイコンが文字 (`mi-arrow_upward`) になる | `node-red-dashboard` 未導入 | `docker compose build --no-cache nodered` |
| 3D ビューが真っ黒 | OGRE2 描画の起動遅延 | 10〜20 秒待ち、ビュー内をマウスドラッグ |
| BRIDGE バッジが `OFFLINE` のまま | `ros2_bridge` 停止または MQTT 接続不能 | `docker compose logs ros2_bridge` を確認 |
| ロボットが動かない（odom も止まったまま） | `ros_gz_bridge` 未接続 | `docker compose logs gazebo \| grep 'Bridge'` で起動確認 |

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
