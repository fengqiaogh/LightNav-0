<!--
  Auto-translated from docs/DEPLOYMENT.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](DEPLOYMENT.md)

# 真机部署

部署采用双进程架构：**模型运行在 GPU 主机上，由 `lightnav-serve` 提供服务**，而**机器人运行一个轻量级 WebSocket 客户端**，负责流式传输相机帧并执行返回的航点。机器人端不需要 GPU，也不需要 torch —— 只需要一个 WebSocket 库和一个 JPEG 编码器。

本文档涵盖服务端和客户端协议。机器人端的完整 ROS 2 参考实现 —— 包括相机、客户端、MPC 航点跟踪、Web 控制面板以及机器人适配器（Unitree Go2、LimX TRON1）—— 位于 [`robot_deploy/`](../robot_deploy/README.md)，而 [`mujoco_demo/`](../mujoco_demo/README.md) 在模拟的 TurtleBot 上运行相同的协议和 MPC，无需真实机器人。

GPU 主机不必是远程的：[JETSON_THOR.md](JETSON_THOR.md) 记录了如何在机器人自带的 NVIDIA Jetson Thor 上**板载**提供模型服务（SM 11.0 内核陷阱、统一内存预算、ViT 缓存大小、实测 4+ Hz 闭环），并在 [`scripts/serve_thor.sh`](../scripts/serve_thor.sh) 中提供了配套的启动脚本。

```
 robot (any language)                                GPU host
 ┌──────────────────────────┐    ws://host:8050     ┌────────────────────────────┐
 │ camera ─▶ JPEG ─▶ base64 │ ───── next ─────────▶ │ lightnav-serve             │
 │ instruction text         │ ◀── waypoints/stop ── │  one engine per GPU        │
 │ waypoint[0] ─▶ velocity  │                       │  micro-batched sessions    │
 └──────────────────────────┘                       └────────────────────────────┘
```

## 在 GPU 主机上启动服务端

```bash
# tracking prompt (follow a person / object). A released checkpoint ships its own decoder,
# so --model_path is the only asset argument.
PORT=8050 CUDA_VISIBLE_DEVICES=0 lightnav-serve \
    --task tracking \
    --model_path checkpoints/LightNav-0 \
    --backend vllm_local --gpu_memory_utilization 0.85

# navigation prompt (instruction / object-goal navigation)
PORT=8051 CUDA_VISIBLE_DEVICES=0 lightnav-serve \
    --task vln \
    --model_path checkpoints/LightNav-0 \
    --backend vllm_local

# a checkpoint that ships NO decoder: pass the RVQ bundle explicitly
PORT=8052 CUDA_VISIBLE_DEVICES=0 lightnav-serve \
    --task vln \
    --model_path /path/to/hf_ckpt \
    --action_tokenizer_bundle /path/to/action_tokenizer --horizon 10 \
    --backend vllm_local
```

服务端在绑定端口之前会先运行一次合成预热推理，因此端口打开（或 `--ready_file` 出现）意味着引擎已真正就绪。多台机器人可以共享一个服务端：每个 WebSocket 连接都是独立会话（拥有自己的帧历史和 ViT 缓存），并发请求会在共享引擎上进行微批处理。若使用多块 GPU，请使用 `scripts/start_servers.sh`（每块 GPU 一个进程）或 Docker 镜像（见下文 *Docker 镜像*），并在前面放置一个普通的 TCP 负载均衡器 —— 会话以连接为作用域，因此任何能将连接保持在同一后端的负载均衡器都可以工作。

## 机器人客户端循环

每个回合（新指令 / 新目标）：

1. 每个连接执行一次 `login`，然后执行 `reset` —— 清除服务端的帧历史。
2. 每个控制周期：采集 RGB 帧，进行 JPEG 编码，发送 `next`，附带单调递增的 `seq`、帧以及**当前指令**（指令随每次 `next` 一起传输，因此可以在回合中途更改而无需 reset）。
3. 读取回复：`actions.actions` 是 `(H, 3)` 的航点块，`stop` 是到达标志，`visible` 是目标可见性标志（跟踪检查点），`pointing` 是目标像素（指向检查点）。
4. 将**第一个航点**作为速度命令执行一个控制周期，然后重复 —— 模型每帧都会重新规划，因此其余行只是前瞻。

帧率：以检查点的训练帧率（`eval_config.json` 中的 `video_fps`，通常为 4 Hz）或更快的速度发送帧；发送的每一帧都会追加到历史窗口中，因此只想预热历史（不做预测）的客户端可以发送带有空 `instruction` 的 `next`，并收到 `{"rc": 0, "msg": "image received"}`。以相机的原生分辨率发送帧；服务端会将其调整为检查点的 `video_size`。

航点 → 速度。每一行是一个*规划步*的机器人局部位移；轨迹词表将每步的平移限制在约 0.25 m、偏航限制在 30°。这些行**本身不携带时间基准**：选择 `dt` = 你的控制周期，并命令

```
v_forward = forward_m / dt          w_yaw = yaw_rad / dt          (lateral_m for holonomic bases)
```

裁剪到平台的限制范围内。参考客户端（`lightnav-ws-client`、EVT-Bench agent）通过将第一个航点按每步最大值归一化并裁剪到 `[-1, 1]` 来规避这一选择：`vx = clip(fwd / 0.375)`、`vy = clip(lat / 0.25)`、`vyaw = clip(yaw / (π/20))`，然后按平台的最高速度进行缩放。`lightnav.velocity.first_waypoint_to_velocity_cmd` 实现了 Habitat 风格的归一化映射，如果你想复用的话。（可视化 HUD 的速度读数假设每步 0.1 s；这是一种显示约定，见 [VISUALIZATION.md](VISUALIZATION.md)。）将 `stop=true`（模型输出了停止动作）视为“目标已到达”：停止并结束回合。错误是非致命的（`rc` 400/500 并附带消息）；复用上一条命令或停止，并保持连接。

最小 Python 客户端（任何语言都可以 —— 协议就是纯 JSON）：

```python
import base64, io, json, math
import numpy as np
from PIL import Image
from websockets.sync.client import connect          # websockets>=12

SERVER = "ws://gpu-host:8050"
V_MAX, W_MAX = 0.5, 1.0                              # your platform's top speeds (m/s, rad/s)

def jpeg_b64(rgb):                                    # rgb: HWC uint8 RGB numpy array
    buf = io.BytesIO(); Image.fromarray(rgb).save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()

with connect(SERVER, max_size=64 * 1024 * 1024) as ws:
    ws.send(json.dumps({"action": "login", "data": {"clientId": "robot-01"}}))
    assert json.loads(ws.recv())["data"]["rc"] == 0
    ws.send(json.dumps({"action": "reset", "data": {}}))          # new episode
    assert json.loads(ws.recv())["data"]["rc"] == 0

    seq = 0
    while not done:
        frame = camera.read_rgb()                                 # your camera
        ws.send(json.dumps({"action": "next", "data": {
            "seq": seq, "image": jpeg_b64(frame),
            "instruction": "follow the person in the red shirt",
        }}))
        seq += 1
        data = json.loads(ws.recv())["data"]
        if data["rc"] != 0 or "actions" not in data:
            continue                                              # keep last command
        if data["stop"]:
            robot.stop(); break
        fwd, lat, yaw = data["actions"]["actions"][0]             # first waypoint, robot frame
        vx = max(-1.0, min(1.0, fwd / 0.375))                     # normalised by per-step maxima
        vyaw = max(-1.0, min(1.0, yaw / (math.pi / 20)))
        robot.set_velocity(vx * V_MAX, vyaw * W_MAX)              # for one control period
```

`lightnav-ws-client` 是同一个循环，从 mp4 或帧目录驱动，是从机器人所在网络检查服务端最快的方式：

```bash
lightnav-ws-client --server ws://gpu-host:8050 --video clip.mp4 --fps 4 \
    --instruction "follow the person in the red shirt"
```

## 运维注意事项

- **延迟。** 在单块现代 GPU 上使用 `vllm_local` 时，一步约 60–150 ms（包括 ViT —— 只有窗口中新增的帧才会经过视觉塔）；`hf` 后端要慢好几倍。每个回复中的 `latency_ms` 是服务端的墙钟时间，包括排队时间。
- **连接卫生。** 会话随连接存亡；重新连接会开始一个空历史（发送 `reset` 并重新流式传输）。每个连接保持一个未完成的请求。
- **消息大小。** 将客户端的 WebSocket 库配置为支持 ≥ 64 MiB 的帧（服务端使用 `max_size=64*1024*1024`）；许多库默认的 1 MiB 限制会拒绝大图像。
- **指向检查点**返回的是*客户端*帧尺寸下的目标像素（`pointing.frame_size`），因此机器人可以在不知道模型输入分辨率的情况下叠加或跟踪它（[PROTOCOL.md](PROTOCOL.md)）。
- **每块 GPU 多台机器人。** 将 `--max_batch_size`（默认 8）提高到并发会话数；LLM 解码是批处理的，ViT 是每会话独立的。

## 录制与可视化

要查看模型在机器人自身帧上的预测结果，请在服务端录制并在之后渲染：

```bash
# GPU host: record every connection's episodes (the client's JPEG frames + one record per prediction)
lightnav-serve ... --record_dir output/episodes --cam_hfov_deg 112 --cam_height 0.45
#   env equivalents: RECORD_DIR, CAM_HFOV_DEG, CAM_HEIGHT (also read by scripts/start_servers.sh and docker)

# afterwards, anywhere with the video extra installed:
lightnav-render output/episodes                     # -> <episode dir>/traj_pointing.mp4
lightnav-render output/episodes --height 1080 --fps 15 --forward-offset 0 --overwrite
```

录制文件存放在 `output/episodes/run_<timestamp>/<clientId>/episode_NNN/`（`manifest.json`、`image_*.jpg`、`actions.json`）；服务端在服务循环中从不编码视频。渲染的视频将预测的航点块显示为地平面带状（使用客户端相机的 FOV 和高度投影 —— 为你的机器人设置 `--cam_hfov_deg` / `--cam_height`），指向像素显示为薄荷色（`apos`）/ 品红色（`opos`）圆盘，并带有显示指令、GO/STOP、步数、步率和第一航点速度的 HUD。默认情况下，视频以墙钟节奏播放（`realtime` 时间基准）。详细信息、录制模式和评估客户端的 `--save_video`：[VISUALIZATION.md](VISUALIZATION.md)。

---


## Docker 镜像（服务端）

```bash
docker build -t lightnav0:latest .
docker run --gpus all -p 8050:8050 -v /path/to/models:/models \
    -e MODEL_PATH=/models/LightNav-0 -e TASK=tracking \
    lightnav0:latest
# a checkpoint without a shipped decoder additionally needs
#   -e ACTION_TOKENIZER_BUNDLE=/models/action_tokenizer
```

`docker/entrypoint.sh` 将 `MODEL_PATH`、`ACTION_TOKENIZER_BUNDLE`（可选）、`TASK`、`BACKEND`、`GPU_MEM_UTIL`、`MAX_NEW_TOKENS`、`HOST`、`PORT`、`MAX_BATCH_SIZE`、`MAX_WAIT_MS`、`NUM_HISTORY_FRAMES`、`POOL_SPATIAL` 以及录制相关参数（`RECORD_DIR`、`RECORD_FPS`、`RECORD_TIMELINE`、`RECORD_IMAGES`、`CAM_HFOV_DEG`、`CAM_HEIGHT`、`TRAJ_FORWARD_OFFSET`、`WAYPOINT_DT_S`；见上文 *录制与可视化*）转换为 `lightnav-serve` 标志；额外的 `docker run` 参数会原样追加。


## Python API

```python
from lightnav.tracking import build_tracking_agent

agent = build_tracking_agent(
    model_path="checkpoints/LightNav-0",     # decoder + processing params from the checkpoint
    backend="vllm_local",                    # or "hf"
)
# A checkpoint that ships no decoder needs one passed in:
#   build_tracking_agent(model_path=..., action_tokenizer_bundle=..., horizon=10)

agent.reset(instruction="follow the person in the red shirt")
for frame in rgb_frames:                     # HWC uint8 RGB numpy arrays
    agent.observe(frame)
waypoints, raw_text, latency_ms = agent.predict_waypoints(agent.instruction)
# waypoints: (H, 3) float32 -- [forward_m, lateral_m(+=left), yaw_rad(+=ccw)]
```

`observe()` 将一帧追加到历史中（内部调整为检查点的 `video_size` 并归一化）；`predict_waypoints()` 在当前缓冲区上运行一步。SlowFast 检查点保留整个回合；其他检查点保留 `num_history_frames` 的环形缓冲区。`predict_waypoints(instruction, task_type="vlnce_traj")` 选择 VLN 提示词而非跟踪提示词。

更低层级：`lightnav.inference.InferenceConfig` + `build_engine(config, task_type)` 返回 `VLNInferenceEngine` 和 `ModelBundle`；`engine.generate_from_frames(video_tensor, instruction, frame_ids=..., task_type=...)` 返回原始 token 文本；`lightnav.velocity.first_waypoint_to_velocity_cmd` 将航点映射为归一化的 `{linear_velocity, angular_velocity}` 命令；`lightnav.habitat.run_habitat_eval(HabitatEvalConfig(...))` 以编程方式运行 Habitat 评估。

---


## 通信协议摘要

每条消息都是一个 JSON 文本帧；每个请求恰好得到一个响应。完整结构、错误码和指向载荷：[PROTOCOL.md](PROTOCOL.md)。

```
client -> {"action": "login", "data": {"clientId": "<id>"}}       # clientId optional
server <- {"action": "login", "data": {"rc": 0, "msg": "ok"}}

client -> {"action": "reset", "data": {}}                       # new episode; clears the frame buffer
server <- {"action": "reset", "data": {"rc": 0, "msg": "ok"}}

client -> {"action": "next", "data": {"seq": 12, "image": "<base64 JPEG>", "instruction": "..."}}
server <- {"action": "next", "data": {
  "rc": 0, "seq": 12,
  "actions": {"step": 64, "actions": [[0.4, 0.0, 0.0], [0.8, 0.1, 0.05], ...]},   # (H, 3)
  "stop": false, "visible": true, "latency_ms": 123.4,
  "timings_ms": {"batch_size": 1, "vit_ms": 40.1, "llm_ms": 60.2, ...},
  "raw_text": "<tpos_17><traj_3877>",
  "pointing": {...}                       # only for checkpoints that emit <apos_*>/<opos_*>
}}
```

- `actions.actions` 是预测的 `(H, 3)` 航点块，单位为机器人局部米 / 弧度；`actions.step` 是历史缓冲区中的帧数。
- 空 / `null` 的 `instruction` 仅缓冲帧：`{"rc": 0, "seq": N, "msg": "image received"}`。
- `stop=true`：模型输出了停止动作。`visible`：从 grounding token 解码而来，对于没有该 token 的检查点为 `null`。`raw_text`：解码输出（≤ 256 字符）。
- 错误是非致命的：格式错误的请求返回 `rc: 400`，推理失败返回 `rc: 500`；连接保持打开。

---
