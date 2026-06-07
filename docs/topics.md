# トピック一覧

本デモで利用する MQTT と ROS 2 のトピックを横断的に整理します。

## MQTT（制御プレーン）

| トピック | 方向 | QoS | Retain | 発行元 | 受信先 |
|---|---|---|---|---|---|
| `robot/cmd_vel` | C → B | 1 | × | Node-RED（または SoftPLC） | `mqtt_ros2_bridge` |
| `robot/status`  | B → C | 1 | ○ | `mqtt_ros2_bridge` | Node-RED、運用監視 |
| `robot/odom`    | B → C | 0 | × | `mqtt_ros2_bridge` | Node-RED、可視化基盤 |
| `robot/alarm`   | B → C | 1 | × | `mqtt_ros2_bridge` | Node-RED、運用 |

凡例: C = クライアント (Node-RED / SoftPLC)、B = ブリッジ。

## ROS 2（シミュレーションプレーン）

| トピック | 型 | 方向 | 発行元 | 受信先 |
|---|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | ブリッジ → シミュ | `mqtt_ros2_bridge` | Gazebo `libgazebo_ros_diff_drive` |
| `/odom`    | `nav_msgs/msg/Odometry`   | シミュ → ブリッジ | Gazebo `libgazebo_ros_diff_drive` | `mqtt_ros2_bridge` |
| `/tf`      | `tf2_msgs/msg/TFMessage`  | シミュ → *        | Gazebo diff_drive | RViz、ナビゲーション（任意） |
| `/clock`   | `rosgraph_msgs/msg/Clock` | シミュ → *        | Gazebo            | 任意のシム時刻利用ノード |

`ROS_DOMAIN_ID=42` をブリッジと Gazebo コンテナで共有します。

## トピック ↔ ペイロード変換規則

| MQTT | ROS 2 | 変換内容 |
|---|---|---|
| `robot/cmd_vel` JSON | `/cmd_vel` `Twist` | `linear_x` → `linear.x`、`angular_z` → `angular.z`。他の項は 0 |
| `/odom` `Odometry` | `robot/odom` JSON | `pose.position.{x,y}` と `twist.twist.linear.x` / `angular.z` を抽出。`ODOM_THROTTLE_HZ` で間引き |
| （内部生成） | `robot/status` | MQTT 接続成立時 / LWT 発火時に retained で発行 |
| （内部生成） | `robot/alarm` | ウォッチドッグ状態遷移時に発行 |

## 将来拡張トピック

| トピック | 用途 |
|---|---|
| `robot/mode`（C → B） | Node-RED と SoftPLC を同居させた時の `manual` / `auto` 権限切替 |
| `robot/cmd_pose`（C → B） | 高位プランナ向けの目標姿勢指示 |
| `robot/{id}/...` | 複数台運用時のロボット ID 名前空間 |
| `robot/diag`（B → C） | 構造化された診断情報（CPU、レイテンシなど） |
