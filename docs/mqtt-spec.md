# MQTT 仕様書

制御クライアント（Node-RED、将来の SoftPLC）と `ros2_bridge` ノードの
間で公開する契約です。

## 1. ブローカー

| 項目 | 値 |
|---|---|
| 実装 | Eclipse Mosquitto 2.x |
| ホスト名（Compose 内部） | `mosquitto` |
| 平文 MQTT ポート | `1883` (TCP) |
| WebSocket ポート | `9001` |
| 認証 | デモのため匿名。本番では `password_file` + ACL を有効化すること |
| TLS | デモのため無効。本番では TLS リスナーを追加すること |
| 永続化 | 有効。ボリュームにバックアップ |

## 2. バージョニング方針

* PoC 段階ではトピックにバージョン名を付与しません。互換性のない変更が
  必要になった場合は `v2/` プレフィックス（例: `robot/v2/cmd_vel`）を
  導入し、1 リリース分は新旧を並走させます。
* ペイロードのキーは**追加**のみであればバージョンを上げません。既存
  クライアントは未知のキーを無視する必要があります。キーの削除や改名は
  互換性のない変更です。

## 3. トピック一覧

| トピック | 方向 | QoS | Retain | ペイロード |
|---|---|---|---|---|
| `robot/cmd_vel` | クライアント → ブリッジ | 1 | × | Twist JSON、§4 参照 |
| `robot/status`  | ブリッジ → クライアント | 1 | **○** | `{"state":"online"\|"offline"}`（LWT） |
| `robot/odom`    | ブリッジ → クライアント | 0 | × | Odom JSON、§4 参照 |
| `robot/alarm`   | ブリッジ → クライアント | 1 | × | Alarm JSON、§4 参照 |

将来予約: `robot/v2/*`、複数台運用時の `robot/{id}/...`。

## 4. ペイロード定義

すべてのペイロードは UTF-8 JSON オブジェクトです。数値は倍精度浮動小数点。

### 4.1 `robot/cmd_vel`

```json
{
  "linear_x": 1.0,
  "angular_z": 0.0
}
```

* `linear_x` — 並進速度 [m/s]。正値が前進。必須。
* `angular_z` — ヨー角速度 [rad/s]。正値が反時計回り。必須。
* ブリッジ側で `±MAX_LINEAR` / `±MAX_ANGULAR` にクランプします。
* 非有限値 (`NaN`, `Infinity`) は拒否してログ出力します。
* 互換性確保のため `linear_y`, `angular_x`, `angular_y`, `seq`, `ts`
  は予約済みキーとします。

タスク仕様に合わせた代表的なペイロード:

| 動作 | ペイロード |
|---|---|
| 前進  | `{"linear_x":  1.0, "angular_z":  0.0}` |
| 後退  | `{"linear_x": -1.0, "angular_z":  0.0}` |
| 左旋回 | `{"linear_x":  0.0, "angular_z":  1.0}` |
| 右旋回 | `{"linear_x":  0.0, "angular_z": -1.0}` |
| 停止   | `{"linear_x":  0.0, "angular_z":  0.0}` |

### 4.2 `robot/status`

```json
{ "state": "online" }
```

* `state ∈ {"online", "offline"}`。retained。
* ブローカー接続成功時に毎回 `online` を発行します。
* 非正常終了時は Last Will により `offline` が自動発行されます。

### 4.3 `robot/odom`

```json
{
  "x": 1.23,
  "y": -0.45,
  "linear_x": 0.50,
  "angular_z": 0.10
}
```

* `x`, `y` — `odom` フレームでの位置 [m]。
* `linear_x`, `angular_z` — 実測速度。
* `ODOM_THROTTLE_HZ`（既定 5 Hz）で送信頻度を制限します。

### 4.4 `robot/alarm`

```json
{
  "code": "WATCHDOG_TIMEOUT",
  "detail": "no cmd_vel within 1.0s"
}
```

| `code` | 意味 |
|---|---|
| `WATCHDOG_TIMEOUT` | `WATCHDOG_SEC` 内に有効な指令なし。ゼロ速度に強制 |
| `WATCHDOG_CLEAR`   | タイムアウト後に指令が再開した |

将来予約のコード: `BRIDGE_OVERLOAD`, `INVALID_PAYLOAD`,
`GAZEBO_UNREACHABLE`。

## 5. QoS 方針

| 用途 | QoS | 理由 |
|---|---|---|
| 指令 (`robot/cmd_vel`) | 1 | 少なくとも一度の配送が必要。ブリッジが固定周期で再送するため重複は問題にならない |
| ステータス (`robot/status`) | 1 + retained | 後発の購読者が現在状態を即取得できる必要がある |
| アラーム (`robot/alarm`) | 1 | 無音で落とすのは不可 |
| テレメトリ (`robot/odom`) | 0 | 高頻度のため欠落許容 |

QoS 2 はブローカー負荷の割に得が無いため意図的に採用していません。

## 6. セキュリティ方針

PoC ではループバック (`MQTT_BIND=127.0.0.1`) で匿名運用しています。
ブローカーを外部公開する前に下記を実施してください。

1. `mosquitto.conf` で `password_file` を有効化しクライアント毎の
   認証情報を付与する。
2. ACL を導入し、`robot/cmd_vel` への書き込みは制御主体（Node-RED、
   SoftPLC）に限定、`robot/odom/status/alarm` への書き込みはブリッジ
   のみに制限する。
3. TLS リスナー (`listener 8883`) とサーバー証明書を追加する。
