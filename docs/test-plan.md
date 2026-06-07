# テスト仕様書

QA 担当が本書を保守します。各シナリオに手順・期待結果・検証コマンドを
記載します。

前提: スタックが起動済み (`docker compose up -d`) で、`docker compose ps`
の出力で 4 コンテナがすべて `running` / `healthy` 状態であること。

人が観測する場合の汎用サブスクライバ:

```bash
docker compose exec mosquitto mosquitto_sub -v -t 'robot/#'
```

## T1 — 正常系走行（ゴールデンパス）

| 手順 | 操作 | 期待結果 |
|---|---|---|
| 1 | `http://127.0.0.1:1880/ui` を開く | Drive / Speed / Telemetry の各グループが表示される |
| 2 | Speed スライダーを 1.0 に設定 | まだ動かない（ボタンが必要） |
| 3 | 「前進」をクリック | `robot/cmd_vel` に `{"linear_x":1,"angular_z":0}` が流れる |
| 4 | Telemetry を確認 | `Bridge: online` / `Odom: x=… y=… v=…` が増加 |
| 5 | 「停止」をクリック | 減速して停止。odom の `v` → 0 |
| 6 | 「左旋回」→「右旋回」をクリック | `angular_z` の符号が反転、`linear_x` = 0 |
| 7 | 「後退」をクリック | `linear_x` = -1、ロボットが後退 |

指令変換は次のコマンドで検証します:

```bash
docker compose exec ros2_bridge bash -lc \
  'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
   && ros2 topic echo /cmd_vel --once'
```

## T2 — MQTT 入力検証

| # | `robot/cmd_vel` への入力 | `/cmd_vel` 上の期待値 |
|---|---|---|
| 2.1 | `{"linear_x":0.5,"angular_z":0.5}` | `linear.x=0.5, angular.z=0.5` |
| 2.2 | `{"linear_x":99,"angular_z":0}` | クランプ: `linear.x=2.0` (MAX_LINEAR) |
| 2.3 | `{"linear_x":"oops"}` | 反映されず、ブリッジが `bad numeric fields` をログ出力 |
| 2.4 | JSON 以外のバイト列 | 反映されず、`bad JSON on robot/cmd_vel` をログ出力 |
| 2.5 | `{"linear_x":NaN,"angular_z":0}`（生バイト） | 反映されず、`non-finite command rejected` をログ出力 |

送信コマンド:

```bash
docker compose exec mosquitto mosquitto_pub -t robot/cmd_vel \
    -m '{"linear_x":99,"angular_z":0}'
```

## T3 — ウォッチドッグ（指令タイムアウト）

| 手順 | 操作 | 期待結果 |
|---|---|---|
| 1 | 動作指令を 1 回送信し、`WATCHDOG_SEC`（既定 1.0 秒）以上待機 | `/cmd_vel` がゼロに戻り、odom 速度も 0 に収束 |
| 2 | `robot/alarm` を確認 | `WATCHDOG_TIMEOUT` イベントが 1 件 |
| 3 | 新規指令を送信 | `WATCHDOG_CLEAR` イベントが 1 件 |

```bash
docker compose exec mosquitto mosquitto_sub -t 'robot/alarm' -v &
docker compose exec mosquitto mosquitto_pub -t robot/cmd_vel -m '{"linear_x":0.5}'
sleep 2  # ウォッチドッグ時間を超過
```

## T4 — ブローカー停止試験

| 手順 | 操作 | 期待結果 |
|---|---|---|
| 1 | `docker compose stop mosquitto` | ブリッジが `MQTT disconnected` をログ出力。`WATCHDOG_SEC` 以内に `/cmd_vel` がゼロに強制される |
| 2 | `docker compose start mosquitto` | ブリッジが再接続（バックオフ最大 30 秒）。再接続時に `robot/status` に `online` が再発行される |
| 3 | ダッシュボードで `/ui` を再読込 | ボタン操作が復活する |

ブローカー停止中は LWT が retained 済み。新たな購読者は最初に
`robot/status = {"state":"offline"}` を受信し、その後ブリッジ復帰で
`online` が届きます。

## T5 — ブリッジ停止試験

| 手順 | 操作 | 期待結果 |
|---|---|---|
| 1 | `docker compose stop ros2_bridge` | Mosquitto が LWT を発行: `robot/status = {"state":"offline"}`（retained）。ダッシュボードの "Bridge" が offline に切り替わる |
| 2 | ダッシュボードから指令を送り続ける | Gazebo は無反応（ロボットは静止）、`gazebo` コンテナにエラーは出ない |
| 3 | `docker compose start ros2_bridge` | `robot/status` が `online` に戻り、ロボットが再び応答する |

## T6 — Gazebo 停止試験

| 手順 | 操作 | 期待結果 |
|---|---|---|
| 1 | `docker compose stop gazebo` | ブリッジは `/cmd_vel` を発行し続けるが消費されない。v1 では意図的にアラーム化していない（バックログ参照） |
| 2 | `docker compose start gazebo` | 数秒以内に `/cmd_vel` への応答が復帰する |

バックログ: `/odom` 未受信を検出して `GAZEBO_UNREACHABLE` アラームを
発行するロジックは今後の拡張候補。

## T7 — シェルだけで実施する E2E スモークテスト

ダッシュボードを経由せず MQTT 契約のみで動作することを確認します。

```bash
docker compose exec mosquitto mosquitto_pub -t robot/cmd_vel \
    -m '{"linear_x":1.0,"angular_z":0.0}'

docker compose exec ros2_bridge bash -lc \
  'source /opt/ros/humble/setup.bash && source /ws/install/setup.bash \
   && ros2 topic echo /odom --once' | grep -E 'linear|x:'
```

期待結果: `linear.x` > 0、`pose.position.x` が増加。

## 合格判定

* T1、T2、T3、T4、T5 が `docker compose up` のみで再現できる。
* T6 で停止 → 復旧の流れがクラッシュなく成立する。
* T7 がダッシュボード非経由で成功し、MQTT が唯一の契約であることが
  実証される。
