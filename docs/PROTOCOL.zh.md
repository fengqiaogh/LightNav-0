<!--
  Auto-translated from docs/PROTOCOL.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](PROTOCOL.md)

# WebSocket 线路协议

`lightnav-serve` 使用一种小型的基于 WebSocket 的 JSON 协议。每一帧都是一条
JSON 文本消息；每个请求恰好得到一个响应。参考客户端是 `lightnav-ws-client`
（`src/lightnav/cli/ws_client.py`）；`evt_bench/trackvla_client_agent.py` 中的
EVT-Bench 客户端使用相同的协议。

服务器接受最大 64 MiB 的请求帧（`max_size=64*1024*1024`），因此每条消息携带一张
全分辨率 JPEG 也没问题。响应很小（几 KiB），所以客户端自身的入站限制通常无关紧要；
如果你的库报错，就调高它。

## 会话模型

* 一个连接 = 一个会话：一个帧缓冲区（最近 `num_history_frames` 帧，对于
  slow-fast 检查点则是整个 episode）加上每个会话的 ViT 缓存。会话在任意类型的
  第一条消息到达时惰性创建。
* 连接之间不保留任何状态。`clientId` 是日志元数据，不是身份验证，也不会恢复状态。
* `reset` 会清空帧缓冲区、帧 id 和 ViT 缓存。在每个 episode 边界都要发送它。
* 并发连接的所有服务器端推理都会微批处理到一个共享引擎上；客户端除了通过
  `latency_ms` 之外感知不到这一点。

## 请求

```json
{"action": "login", "data": {"clientId": "<string, optional>"}}
{"action": "reset", "data": {}}
{"action": "next",  "data": {"seq": <int>, "image": "<base64 JPEG>", "instruction": "<string or null>"}}
```

* `clientId` 若存在，必须是字符串或 `null`。
* `seq` 必须是整数（布尔值会被拒绝；浮点数仅当有限且为整数时才被接受）。它会被
  回显，除此之外不使用。
* `image` 必须是非空的 base64 字符串，表示一张 JPEG（或 PNG）帧。服务器会将其
  解码为 RGB，并在内部缩放到检查点的 `video_size`；请以原生分辨率发送相机帧。
* `instruction` 可以是 `""` 或 `null`。**仅缓冲语义：** 帧总是先被追加到会话
  缓冲区；如果指令为空，服务器确认收到该帧且不运行模型。这让客户端可以在第一次
  预测之前预填充历史窗口。

## 响应

### login / reset

```json
{"action": "login", "data": {"rc": 0, "msg": "ok"}}
{"action": "reset", "data": {"rc": 0, "msg": "ok"}}
```

### next，仅缓冲（instruction 为空或 null）

```json
{"action": "next", "data": {"rc": 0, "seq": 17, "msg": "image received"}}
```

### next，预测

```json
{
  "action": "next",
  "data": {
    "rc": 0,
    "seq": 17,
    "actions": {
      "step": 12,
      "actions": [[0.31, 0.02, 0.05], [0.62, 0.04, 0.09], "... H rows"]
    },
    "latency_ms": 143.2,
    "stop": false,
    "visible": true,
    "timings_ms": {"batch_size": 1.0, "queue_wait_ms": 0.4, "vit_ms": 61.0, "llm_ms": 70.1, "...": 0.0},
    "raw_text": "<tpos_12><traj_57>",
    "pointing": {"...": "only for pointing checkpoints, see below"}
  }
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `actions.step` | int | 追加此帧后会话缓冲区中的帧数（`min(frames since reset, num_history_frames)`；对于 slow-fast 检查点是总帧数）。仅供参考。 |
| `actions.actions` | `[[float, float, float] x H]` | 预测的航点块，参见*航点约定*。值为 float32 转换为 JSON 数字（例如 `0.10000000149011612`）。 |
| `latency_ms` | float | 服务器上预测的墙钟时间，包括微批队列等待、ViT、LLM 解码和航点解码。 |
| `stop` | bool | 模型预测了停止动作（解码出的航点块全为零）。 |
| `visible` | bool 或 null | 目标是否可见，当检查点输出 grounding token 时：`<tpos_k>` 解码为一个可见性位；网格指向使用 `opos_id > 0`；`posxy` 指向使用 `<opos>` 存在（true）/ `<novis>`（false）。对于没有 grounding token 的检查点为 `null`。 |
| `timings_ms` | object | 服务器各阶段计时（`batch_size`、`queue_wait_ms`、`build_sample_ms`、`vit_ms`、`llm_ms`、`decode_waypoints_ms`、`batch_total_ms`，以及可用时的 ViT 缓存计数器）。对客户端可选；可能变化。 |
| `raw_text` | string | 此步骤模型的原始输出 token，若过长则截断为 256 个字符（带 `...`）。用于调试。 |
| `pointing` | object | 仅当输出携带 `<apos*>`/`<opos*>` 指向 token 时存在。 |

只需要驱动机器人的客户端读取 `actions.actions[0]`（第一个航点）、`stop`，以及
可选的 `visible`。

### pointing 载荷

Pointing 检查点会为动作目标（`apos`）和/或被跟踪对象（`opos`）输出一个像素位置。
服务器将 token id 转换为**客户端发送的**帧中的像素（`frame_size = [width, height]`
为解码后的请求图像的尺寸，在服务器内部缩放之前）。像素四舍五入到 2 位小数。

网格编码（`<apos_K>` / `<opos_K>`，在 48x27 单元格网格上用一个 id 表示）：

```json
{"mode": "grid", "frame_size": [640, 480],
 "apos_px": [412.5, 262.5], "opos_px": null,
 "apos_clamped": false, "opos_clamped": false,
 "apos_state": "point", "opos_state": "not_visible"}
```

轴编码（`<apos><pos_x><pos_y>`，每个通道两个 1000 分箱的轴 token）：

```json
{"mode": "posxy", "frame_size": [640, 480],
 "apos_px": [411.84, 261.6], "apos_clamped": false, "apos_state": "point",
 "opos_px": null, "opos_clamped": false, "opos_state": "none"}
```

| 字段 | 取值 |
|---|---|
| `*_px` | 客户端帧中的 `[u, v]` 像素，或当该通道不携带像素时为 `null` |
| `*_clamped` | 当编码值位于边界单元格/分箱上时为 `true`，即“在该边缘处或超出它” |
| `apos_state` | `none`（通道缺失）、`point`、`rot_left`、`rot_right`、`stop` |
| `opos_state` | `none`、`point`、`not_visible` |

`apos_state` 为 `stop` 是一种指向指令；顶层的 `stop` 报告解码出的动作，是应当
据以行动的字段。

## 错误

| rc | 何时 | 形状 |
|---|---|---|
| 400 | 请求格式错误 | `{"action": "<action or 'error'>", "data": {"rc": 400, "msg": "<reason>", "seq": N}}`（`seq` 仅在已解析时存在） |
| 500 | 模型输出无法解码，或任何其他服务器端错误（在预测时，或在 `login`/`reset` 时创建会话——此时没有 `seq`） | `{"action": "next", "data": {"rc": 500, "seq": N, "msg": "<str(exc)>"}}` |

400 消息：`bad json: ...`、`payload must be an object`、`data must be an
object`、`missing seq`、`seq must be an integer`、`missing image`、`instruction
must be a string`、`bad image: ...`、`clientId must be a string`、`unknown
action: '<x>'`。错误响应中回显的 `action` 是请求的 `action`（若它是非空字符串），
否则为 `"error"`。

400 或 500 之后连接保持打开；客户端决定是复用其上一个动作还是停止。响应绝不会
发送两次：如果服务器发送响应失败，连接会被关闭。模型警告（轨迹 id 超出词表范围、
缺少 RVQ 层级）会以 rc 500 及解析器的消息呈现，绝不会表现为静默错误的航点。

## 航点约定

`actions.actions` 的每一行是一个机器人局部位移

```
[forward_m, lateral_m, yaw_rad]      +lateral = left, +yaw = counter-clockwise
```

相对于当前帧的机器人位姿表示，每个未来步骤一行（`H` 行，`H = --horizon`）。
各行是沿预测块累积的位姿，因此 `actions.actions[0]` 是向前一步的位姿。停止是
全零块并带 `stop: true`。

要将第一个航点转换为 `[-1, 1]` 范围内的归一化 `[vx, vy, vyaw]` 命令，参考客户端
除以每步最大值并裁剪：`vx = clip(fwd / 0.375)`、`vy = clip(lat / 0.25)`、
`vyaw = clip(yaw / (pi/20))`。对于 Habitat 的 `velocity_control` 命令，使用
`lightnav.velocity.first_waypoint_to_velocity_cmd`。

## 最小客户端（Python）

```python
import base64, json
from websockets.sync.client import connect

with connect("ws://localhost:8050", max_size=64 * 1024 * 1024) as ws:
    ws.send(json.dumps({"action": "login", "data": {"clientId": "demo"}}))
    assert json.loads(ws.recv())["data"]["rc"] == 0
    ws.send(json.dumps({"action": "reset", "data": {}}))
    ws.recv()
    for seq, jpeg_bytes in enumerate(frames):
        ws.send(json.dumps({"action": "next", "data": {
            "seq": seq,
            "image": base64.b64encode(jpeg_bytes).decode(),
            "instruction": "follow the person in the red shirt",
        }}))
        data = json.loads(ws.recv())["data"]
        if data["rc"] == 0 and "actions" in data:
            fwd, lat, yaw = data["actions"]["actions"][0]
```
