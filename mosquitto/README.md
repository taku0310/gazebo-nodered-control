# mosquitto コンテナ

Eclipse Mosquitto 2.x を使った **MQTT 3.1.1 / 5.0 ブローカー**。
本デモにおける唯一の「公開された制御インターフェース境界」で、ここに
集まる `robot/*` トピックが Node-RED と ROS 2 ブリッジ（および将来の
SoftPLC）の契約点となる。

## 役割

| 担当 | 説明 |
|---|---|
| メッセージ仲介 | パブリッシュ → 同じトピックを購読中の全クライアントへ配送 |
| QoS 保証 | QoS 0 / 1 / 2 を扱う。本デモは指令とアラームに QoS 1 を採用 |
| Retained メッセージ保持 | `robot/status` を retained で保存し後発の購読者へ即配送 |
| Last Will (LWT) | ros2_bridge の異常終了時に `robot/status: offline` を自動発行 |
| WebSocket 配信 | `:9001` で MQTT-over-WebSocket。ブラウザ MQTT クライアントから接続可能 |

## ファイル構成

| ファイル | 役割 |
|---|---|
| `config/mosquitto.conf` | リスナー 2 系統 (1883/TCP, 9001/WS)、永続化、ログ設定 |

本コンテナは公式イメージ `eclipse-mosquitto:2` をそのまま利用するので
`Dockerfile` を持たない（`docker-compose.yml` で直接指定）。

## コンポーネント図

```mermaid
flowchart LR
    NR[nodered<br/>クライアント]
    RB[ros2_bridge<br/>クライアント]
    SP[将来の SoftPLC<br/>クライアント]
    OBS[監視ツール<br/>mosquitto_sub]

    subgraph container["mosquitto コンテナ"]
      direction TB
      L1[Listener :1883<br/>MQTT 3.1.1/5.0]
      L2[Listener :9001<br/>WebSocket]
      CORE[Core<br/>Persistence + Retain + LWT + ACL]
      LOG[(/mosquitto/log)]
      DAT[(/mosquitto/data)]
      L1 --- CORE
      L2 --- CORE
      CORE --- LOG
      CORE --- DAT
    end

    NR <-- "TCP :1883" --> L1
    RB <-- "TCP :1883" --> L1
    SP <-- "TCP :1883" --> L1
    OBS <-- "TCP :1883" --> L1
```

## シーケンス図 — パブリッシュ → ファンアウト

```mermaid
sequenceDiagram
    autonumber
    participant NR as nodered
    participant MB as mosquitto
    participant RB as ros2_bridge
    participant OBS as 監視ツール

    Note over NR,OBS: 起動時に各自 SUBSCRIBE 済み
    NR->>MB: PUBLISH robot/cmd_vel<br/>QoS=1 retain=false<br/>{"linear_x":1.0,"angular_z":0.0}
    MB-->>NR: PUBACK
    par ファンアウト
        MB->>RB: PUBLISH robot/cmd_vel<br/>QoS=1
        RB-->>MB: PUBACK
    and
        MB->>OBS: PUBLISH robot/cmd_vel<br/>QoS=1
        OBS-->>MB: PUBACK
    end
```

## シーケンス図 — Last Will（ブリッジ異常終了）

```mermaid
sequenceDiagram
    autonumber
    participant RB as ros2_bridge
    participant MB as mosquitto
    participant NR as nodered

    RB->>MB: CONNECT (Will: robot/status={"state":"offline"}, retain=true)
    MB-->>RB: CONNACK
    RB->>MB: PUBLISH robot/status {"state":"online"} retain=true
    Note over RB: 異常終了 (SIGKILL / OOM)
    MB->>NR: PUBLISH robot/status {"state":"offline"} retain=true
    Note over MB: retain 済みなので、後から接続したクライアントも<br/>最初の SUBACK 直後に offline を受信する
```

## アクティビティ図 — メッセージ受信処理

```mermaid
flowchart TD
    A([PUBLISH を受信]) --> B{QoS}
    B -- "0" --> F
    B -- "1" --> C[PUBACK を返す]
    B -- "2" --> D[PUBREC → PUBREL → PUBCOMP]
    C --> F
    D --> F
    F{retain<br/>フラグ?}
    F -- "true" --> G[retained ストアを<br/>上書き]
    F -- "false" --> H
    G --> H{ACL を通過?}
    H -- "no" --> Z([ドロップ])
    H -- "yes" --> I[購読中の全クライアントへ<br/>ファンアウト]
    I --> J([終了])
```

## 状態遷移図 — クライアント 1 接続のライフサイクル

```mermaid
stateDiagram-v2
    [*] --> Disconnected
    Disconnected --> Connecting: TCP/WebSocket open
    Connecting --> Connected: CONNACK rc=0
    Connecting --> Disconnected: CONNACK rc≠0 / TCP fail
    Connected --> Subscribed: SUBSCRIBE / SUBACK
    Subscribed --> Subscribed: PUBLISH 配送
    Subscribed --> WillFired: keepalive timeout / TCP RST
    Subscribed --> Disconnected: DISCONNECT (clean)
    WillFired --> Disconnected: LWT 発行後
    Disconnected --> [*]
```

## ユースケース図

```mermaid
flowchart LR
    Pub([パブリッシャ<br/>nodered / SoftPLC]):::actor
    Sub([サブスクライバ<br/>ros2_bridge / nodered]):::actor
    Obs([監視者<br/>mosquitto_sub]):::actor

    subgraph mosq["mosquitto コンテナ"]
      UC1((メッセージを<br/>仲介する))
      UC2((retained を<br/>保持する))
      UC3((Last Will を<br/>発火する))
      UC4((QoS 配送を<br/>保証する))
    end

    Pub --> UC1
    Pub --> UC2
    Sub --> UC1
    Sub --> UC2
    Sub --> UC3
    Obs --> UC1
    Pub --> UC4
    Sub --> UC4

    classDef actor stroke:#1E88E5,stroke-width:2px,fill:#0e1117,color:#fff;
```

## 公開インターフェース

| インターフェース | プロトコル | 用途 |
|---|---|---|
| ホスト `:1883` | MQTT 3.1.1 / 5.0 over TCP | 通常のクライアント接続 |
| ホスト `:9001` | MQTT over WebSocket | ブラウザクライアント |

## トピック契約

詳細は [`docs/mqtt-spec.md`](../docs/mqtt-spec.md) と
[`docs/topics.md`](../docs/topics.md) を参照。
本コンテナはトピック名を意識しない（任意の `robot/*` を扱う）。

## 設定の主要項目（`config/mosquitto.conf`）

| 設定 | 値 | 意味 |
|---|---|---|
| `listener` | `1883` / `9001 protocol websockets` | 2 リスナー |
| `allow_anonymous` | `true` | デモのため匿名許可。本番では `password_file` + ACL |
| `persistence` | `true` | retained と QoS 1+ の永続化 |
| `persistence_location` | `/mosquitto/data/` | 永続化先（Docker volume） |
| `log_dest` | `stdout` + `file` | `docker compose logs mosquitto` で確認可能 |

## 永続化ボリューム

| ボリューム名 | マウント先 | 内容 |
|---|---|---|
| `mosquitto_data` | `/mosquitto/data` | retained, QoS 1+ の queued messages |
| `mosquitto_log` | `/mosquitto/log` | サーバーログ |

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `docker compose logs mosquitto` で `Connection from .. refused` | 認証や ACL を有効化した直後に多い。設定ファイルを確認 |
| Node-RED から接続できない | broker ホスト名は **`mosquitto`**（Compose のサービス名）。`localhost` ではない |
| `robot/status` が `offline` のまま戻らない | ros2_bridge 側の問題。`docker compose logs ros2_bridge` を確認 |
| retained が消えない | ボリュームに残るのが仕様。空 retained を送ると消える: `mosquitto_pub -t robot/status -m '' -r` |
