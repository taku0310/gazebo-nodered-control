# SoftPLC 移行計画

PoC のダッシュボードは MQTT クライアントの 1 つにすぎず、後段は Node-RED
の存在を知りません。本書はシミュレーション側に手を入れずダッシュボードを
SoftPLC に置き換える段階的な計画です。

## なぜ MQTT が境界として適切か

| 特性 | PLC 引き渡しでの利点 |
|---|---|
| トピックとペイロードの契約 | PLC と ROS 2 は JSON キーの合意だけで済み、rclpy や DDS を PLC に持ち込む必要がない |
| QoS 1 + retained ステータス | PLC は接続が間欠的でも `robot/status` の retained により現在状態を即把握できる |
| ブローカーによるファンアウト | ダッシュボード、PLC、観測ツールが同じトピックに同居でき、ホットテイクオーバーが容易 |
| オープンソースブローカーの選択肢 | Mosquitto、HiveMQ、EMQX、AWS IoT 等で相互運用できる |

## フェーズ 0 — 現状（Node-RED のみ）

```
[Node-RED Dashboard]  ──►  Mosquitto  ──►  ros2_bridge  ──►  Gazebo
```

## フェーズ 1 — シャドー SoftPLC

SoftPLC を並走させ、まずは MQTT を**読むだけ**の状態にします。

* `robot/odom` / `robot/status` / `robot/alarm` を PLC 入力として購読。
* PLC ロジックで候補となる `cmd_vel` を計算するが**発行はしない**。
* 実際のロボット制御は引き続き Node-RED が担当。
* PLC が計算した指令と Node-RED の指令をログや HMI で比較し、PLC
  ロジックの信頼性を高める。

合格基準: `docs/test-plan.md` の全テストケースで PLC と Node-RED の
出力が許容誤差内で一致すること。

## フェーズ 2 — 監視付き切替

ROS 2 側に変更を加えずに権限を実行時で切り替えるためのモードトピックを
導入します。

```
robot/mode  (retained, QoS 1)   値:  "manual" | "auto"
```

* `manual`: Node-RED のみが `robot/cmd_vel` を発行。PLC はシャドー継続。
* `auto`: PLC のみが `robot/cmd_vel` を発行。Node-RED は監視専用に降格。
* ブリッジは仲裁しない。違反者には運用アラートで対応する社会的契約とする。

将来的にハード仲裁が必要になった場合、ブリッジにモード認識フィルタを
追加できますが、本デモの範囲では不要です。

## フェーズ 3 — Node-RED 廃止

`docker-compose.yml` から `nodered` サービスを削除します。差分は次の
ようになります。

```yaml
services:
  mosquitto: ...
  softplc:   ...   # 新規サービスまたは外部ホスト
  ros2_bridge: ... # 変更なし
  gazebo:    ...   # 変更なし
```

`robot/*` の MQTT 契約は変わらないため、設定ファイル 1 つの編集で完了
します。

## SoftPLC 側が満たすべき要件

候補となる SoftPLC ランタイムの適合チェックリスト:

* MQTT 3.1.1 クライアント機能を備えていること（Mosquitto は 3.1.1 +
  5.0 対応）。
* JSON のエンコード / デコード（Codesys IIoT Library、OpenPLC の
  `pymqtt` など）。
* `robot/status` を購読する際の **retain handling = 既存 retained を
  即時受信**を有効にし、`state == "online"` でのみ指令発行を許可する。
* ウォッチドッグを尊重: 非ゼロ指令中は `WATCHDOG_SEC` の逆数以上の
  頻度で `robot/cmd_vel` を再送する。停止時は明示的にゼロ指令を送る。
* 自前のクランプを実装する。ブリッジ側でも防御的に再クランプは行う。

## フェーズ間で変化しないもの

* `gazebo/worlds/diff_drive.world` と diff_drive プラグイン設定
* `ros2_bridge` パッケージ・イメージ・既定環境変数
* MQTT のトピック名・QoS・ペイロード定義

この不変性が低リスクな移行を支える要です。

## リスクと緩和策

| リスク | 緩和策 |
|---|---|
| フェーズ 2 で `robot/cmd_vel` に複数の書込みが発生 | 運用ルールで担保し、認証導入後に `robot/mode` の ACL を追加 |
| PLC ベンダーの MQTT クライアントが publish 時に QoS 0 しか出せない | 許容範囲。ブリッジのクランプとウォッチドッグが補正吸収する |
| PLC のクロックと `/clock` のずれ | PLC は壁時計で制御ループを回し、ブリッジが `PUBLISH_HZ` で固定再送するためジッタを吸収 |
| 互換性のないスキーマ変更が必要になった | 1 リリース分は `robot/v2/cmd_vel` を並走させる |
