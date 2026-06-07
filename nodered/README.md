# nodered コンテナ

Node-RED 3.x + `node-red-dashboard` で構築した**手動オペレータ UI**。
方向ボタンとスライダーから JSON 速度指令を作って `robot/cmd_vel` に
発行し、`robot/status` / `robot/odom` / `robot/alarm` を購読して
リアルタイム表示する。

> 将来この UI は SoftPLC に置き換える。MQTT 契約は同じなので、
> 置換時に ROS 2 / Gazebo 側に手を入れる必要は無い。

## 役割

| 担当 | 説明 |
|---|---|
| オペレータ UI | DRIVE / SPEED / TELEMETRY の 3 パネルをブラウザに配信 |
| 指令生成 | ボタン押下 + 速度スライダー → JSON ペイロードを組み立て |
| MQTT 発行 | `robot/cmd_vel` を QoS 1 で発行 |
| テレメトリ表示 | `robot/status` のバッジ脈動、`robot/odom` の数値表、`robot/alarm` のカード |

## ファイル構成

| ファイル | 役割 |
|---|---|
| `Dockerfile` | 公式 `nodered/node-red:3.1` に `node-red-dashboard@3.6.5` を追加 |
| `flows.json` | インポート可能なフロー定義。`docker-compose.yml` でコンテナの `/data` に bind mount |

## コンポーネント図

```mermaid
flowchart LR
    Browser[ブラウザ<br/>:1880/ui]

    subgraph container["nodered コンテナ"]
      direction TB
      subgraph ui[Dashboard UI]
        SL[ui_slider speed]
        BTN[ui_button × 5<br/>FWD/BWD/L/R/STOP]
        ST[ui_template status pill]
        OD[ui_template odom card]
        AL[ui_template alarm card]
        GA[ui_gauge speed]
        CSS[ui_template global CSS]
      end
      subgraph logic[Flow ロジック]
        SET[change<br/>flow.speed = payload]
        FN[function<br/>direction → JSON]
      end
      subgraph mqtt[MQTT クライアント]
        OUT[mqtt out<br/>robot/cmd_vel]
        IN_S[mqtt in<br/>robot/status]
        IN_O[mqtt in<br/>robot/odom]
        IN_A[mqtt in<br/>robot/alarm]
      end
    end

    MB[(mosquitto)]

    Browser <--> ui
    SL --> SET
    SL --> GA
    BTN --> FN
    FN --> OUT
    OUT --> MB
    MB --> IN_S --> ST
    MB --> IN_O --> OD
    MB --> IN_A --> AL
```

## シーケンス図 — ボタン押下から MQTT 発行まで

```mermaid
sequenceDiagram
    autonumber
    participant U as 操作者
    participant UI as Dashboard (ブラウザ)
    participant FN as function ノード
    participant CTX as flow context
    participant OUT as mqtt out
    participant MB as mosquitto

    U->>UI: SPEED スライダー = 1.2
    UI->>CTX: flow.speed ← 1.2 (change ノード経由)
    U->>UI: FORWARD クリック
    UI->>FN: msg.payload = "forward"
    FN->>CTX: const v = flow.get('speed')
    FN-->>FN: cmd = { linear_x: +1.2, angular_z: 0 }
    FN->>OUT: msg.topic = robot/cmd_vel<br/>msg.payload = cmd
    OUT->>MB: PUBLISH robot/cmd_vel QoS=1
```

## シーケンス図 — テレメトリ受信から表示更新

```mermaid
sequenceDiagram
    autonumber
    participant MB as mosquitto
    participant IN as mqtt in
    participant FMT as function (整形)
    participant TPL as ui_template
    participant UI as Dashboard

    MB->>IN: PUBLISH robot/odom<br/>{"x":1.2,"y":0,"linear_x":0.5,"angular_z":0}
    IN->>FMT: msg.payload (JSON parsed)
    FMT->>TPL: 整形済 msg
    TPL->>UI: AngularJS 双方向バインドで DOM 更新
    Note over UI: POSE X = 1.20 m などの行が動く
```

## アクティビティ図 — 方向決定ロジック

```mermaid
flowchart TD
    A([ボタン押下イベント]) --> B[msg.payload に方向文字列]
    B --> C[v ← flow.get speed]
    C --> D{v が有限値?}
    D -- "no" --> E[v = 1.0 fallback]
    D -- "yes" --> F
    E --> F{方向}
    F -- "forward" --> G1["{lx:+v, az:0}"]
    F -- "backward" --> G2["{lx:-v, az:0}"]
    F -- "left" --> G3["{lx:0, az:+v}"]
    F -- "right" --> G4["{lx:0, az:-v}"]
    F -- "stop" --> G5["{lx:0, az:0}"]
    F -- "その他" --> Z[node.warn して null]
    G1 --> H[topic=robot/cmd_vel で出力]
    G2 --> H
    G3 --> H
    G4 --> H
    G5 --> H
    H --> END([終了])
    Z --> END
```

## 状態遷移図 — BRIDGE バッジ表示

```mermaid
stateDiagram-v2
    [*] --> Unknown: 初回ロード
    Unknown --> Online: robot/status<br/>{state:"online"} 受信
    Unknown --> Offline: robot/status<br/>{state:"offline"} 受信 (retained)
    Online --> Offline: robot/status<br/>{state:"offline"}
    Offline --> Online: robot/status<br/>{state:"online"}
    Online --> Online: LWT 自動再配信
    Offline --> [*]: タブを閉じる
    Online --> [*]
```

## ユースケース図

```mermaid
flowchart LR
    Op([操作者]):::actor
    Mon([監視者]):::actor
    Dev([開発者]):::actor

    subgraph nr["nodered コンテナ"]
      UC1((ロボットを<br/>手動操縦))
      UC2((テレメトリを<br/>監視))
      UC3((ブリッジ生存を<br/>確認))
      UC4((フローを<br/>編集 / デプロイ))
      UC5((アラームを<br/>確認))
    end

    Op --> UC1
    Op --> UC2
    Mon --> UC2
    Mon --> UC3
    Mon --> UC5
    Dev --> UC4

    classDef actor stroke:#1E88E5,stroke-width:2px,fill:#0e1117,color:#fff;
```

## 公開インターフェース

| インターフェース | 方向 | 内容 |
|---|---|---|
| ホスト `:1880` | in | Node-RED エディタ（フロー編集） |
| ホスト `:1880/ui` | in | Dashboard（操作 UI） |
| MQTT `robot/cmd_vel` (Pub QoS=1) | out | 指令 |
| MQTT `robot/status` (Sub QoS=1, retained) | in | ブリッジ生存 |
| MQTT `robot/odom` (Sub QoS=0) | in | テレメトリ |
| MQTT `robot/alarm` (Sub QoS=1) | in | アラーム |

## ノード一覧（flows.json）

| ID | タイプ | 役割 |
|---|---|---|
| `uiBase` | `ui_base` | ダークテーマ + サイト名 |
| `cssInject` | `ui_template (global)` | グローバル CSS（バッジ脈動、カード装飾、ボタン陰影） |
| `btnForward`〜`btnBackward` | `ui_button` × 5 | 方向ボタン。topic=`dir`, payload=方向文字列 |
| `fnCmd` | `function` | 方向 + flow.speed → cmd_vel JSON |
| `mqttOutCmd` | `mqtt out` | `robot/cmd_vel` 発行 |
| `sliderSpeed` | `ui_slider` | 0〜2 のスピード設定 |
| `setSpeed` | `change` | `flow.speed = msg.payload` |
| `gaugeSpeed` | `ui_gauge (wave)` | スライダー値のライブ表示 |
| `mqttInStatus` / `tplStatus` | `mqtt in` + `ui_template` | BRIDGE 脈動バッジ |
| `mqttInOdom` / `tplOdom` | 同上 | POSE X/Y, LIN.X, ANG.Z の 4 行表 |
| `mqttInAlarm` / `tplAlarm` | 同上 | LATEST ALARM カード（CLEAR 時は緑） |

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| アイコンが `mi-arrow_upward` などの文字列で表示される | `node-red-dashboard` が未インストール。`docker compose build --no-cache nodered` |
| ボタンを押しても何も起きない | BRIDGE バッジが `OFFLINE`：`docker compose logs ros2_bridge`。`ONLINE`：MQTT トレースで PUBLISH の有無を確認 |
| ライブで編集した変更が保存されない | `docker-compose.yml` で `flows.json` を read-only でマウントしているため。`compose cp` で書き戻すか、bind mount を ro 解除する |
| スライダーを動かしても波形ゲージが反応しない | `sliderSpeed.passthru` が `false` だと出力されない。`true` のままにする |
