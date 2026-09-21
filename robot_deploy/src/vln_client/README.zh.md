<!--
  Auto-translated from robot_deploy/src/vln_client/README.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](README.md)

# vln_client

VLN 客户端节点。

## 接口

| 名称 | 类型 | 方向 | 描述 |
| --- | --- | --- | --- |
| `camera/color/image_raw` | `sensor_msgs/Image` | 订阅 | 默认为 `rgb8` 相机图像；可通过参数切换为 `sensor_msgs/CompressedImage` |
| `vln/instruction` | `std_msgs/String` | 订阅 | 非空字符串启动或替换任务；空字符串停止任务 |
| `vln/response` | `std_msgs/String` | 发布 | JSON 推理结果，包含 episode、seq、图像时间戳、路点、stop、visible，以及 apos/opos 状态和像素坐标 |
| `vln/path_body` | `nav_msgs/Path` | 发布 | 仅用于可视化；`base_link` 坐标系下的路点，Best Effort |
| `vln/status` | `std_msgs/String` | 发布 | `IDLE`（指令为空）、`RUNNING`（任务进行中）或 `ERROR`（通信或推理失败）；状态变化时立即发布，并以 1 Hz 重新发送 |
| `vln/server_url` | `std_msgs/String` | 订阅 | 切换 VLN WebSocket URL；省略协议时自动添加 `ws://`，活动任务会自动重连 |
| `vln/server_url_status` | `std_msgs/String` | 发布 | 当前生效的 VLN WebSocket URL，Transient Local |

## 布局

- `vln_node.py`：ROS 接口与消息转换。
- `vln_client.py`：图像编码、WebSocket 与请求生命周期；同一时间只有一个请求在途——推理完成后，下一帧相机图像会触发新请求。

`apos_state` 和 `opos_state` 是服务器提供的语义字符串；客户端不解释其取值。对应的 `apos_px` 和 `opos_px` 为 `[x, y]` 或 `null`。

VLN 服务器 URL 默认为空，必须在启动任务前在网页上配置。

相机通过 `image_topic` 和 `image_transport` 参数配置；`image_transport` 接受 `raw` 或 `compressed`。
