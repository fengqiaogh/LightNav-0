<!--
  Auto-translated from docs/GETTING_STARTED.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](GETTING_STARTED.md)

# 快速开始

安装 LightNav-0、运行首次预测、复现基准测试结果以及驱动真实机器人所需的全部内容。[README](../README.md) 介绍了模型是什么以及它的表现如何；本页介绍如何使用它。

## 目录

- [安装](#installation)
- [快速开始](#quick-start)
- [仿真演示](#simulation-demo)
- [评估](#evaluation)
- [真实机器人部署](#real-robot-deployment)
- [可视化](#visualisation)
- [参考文档](#reference-documentation)

## 安装

### 1. 推理环境（Python 3.11，CUDA GPU）

```bash
git clone https://github.com/lightorigins/LightNav-0.git && cd LightNav-0
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[vllm,video,habitat]"      # vLLM backend + video/visualisation + Habitat client
```

仅执行 `pip install -e .` 即可获得 `hf` 后端和 WebSocket 服务器；添加 `test` 额外依赖以运行 CPU 测试套件（`make test`）。我们提供了 Docker 镜像（`docker build -t lightnav0 .`，参见 [DEPLOYMENT.md](DEPLOYMENT.md)）。

**Blackwell sm_103（B300 / B30Z）：** PyPI 上的 `torch 2.10.0` 是 cu12.8 构建版本，其捆绑的 NVRTC 拒绝 `compute_103`——此时 `hf` 后端会在 Qwen3-VL 视觉塔内部因 `nvrtc: error: invalid value for --gpu-architecture` 而崩溃。在这些 GPU 上请安装 cu12.9 的 wheel：

```bash
pip install --index-url https://download.pytorch.org/whl/cu129 \
    "torch==2.10.0+cu129" "torchvision==0.25.0+cu129"
```

`+cu129` 后缀很重要：pip 会认为裸写的 `torch==2.10.0` 已被 cu12.8 构建版本满足，从而保留原版本不变。

### 2. 检查点和动作解码器

```bash
hf download LightOriginsHQ/LightNav-0 --local-dir checkpoints/LightNav-0
```

通常，检查点是一个 Hugging Face 目录（`config.json`、`model*.safetensors`、`tokenizer*`、`processor_config.json`），旁边附带一个 `eval_config.json` 和一个 RVQ 动作分词器包（`action_tokenizer/`）。参见 [CONFIGURATION.md](CONFIGURATION.md)。

### 3. Habitat 环境（仅用于 VLN-CE / ObjectNav 评估；Python 3.9，独立的 conda 环境）

```bash
conda env create -f habitat_server/environment.yml && conda activate habitat
pip install --no-deps "habitat-lab==0.3.20231024" && pip install --force-reinstall "numpy>=1.20,<1.24"
pip install -e habitat_server
```

数据集（R2R / RxR VLN-CE、HM3D / MP3D ObjectNav v1、HM3D-OVON）和场景（MP3D、HM3D）放在 `data/` 下，参见 [HABITAT_SERVER.md](HABITAT_SERVER.md)。

### 4. EVT-Bench（仅用于跟踪评估）

按照其 README 安装 [EVT-Bench](https://github.com/wsakobe/TrackVLA)，然后添加我们的客户端：

```bash
cp evt_bench/trackvla_client_agent.py ~/EVT-Bench/
(cd ~/EVT-Bench && git apply /path/to/LightNav-0/evt_bench/run_py.patch && pip install websocket-client)
```

参见 [EVAL_EVT_BENCH.md](EVAL_EVT_BENCH.md)。

## 快速开始

### 对视频片段进行离线预测

已发布的检查点自带动作解码器，因此 `--model_path` 是唯一需要的资产参数：

```bash
lightnav-predict --model_path checkpoints/LightNav-0 \
    --backend vllm_local --video clip.mp4 --fps 4 \
    --instruction "follow the person in the red shirt"
```

### 启动模型服务并用参考客户端驱动它

```bash
PORT=8050 CUDA_VISIBLE_DEVICES=0 lightnav-serve --task tracking \
    --model_path checkpoints/LightNav-0 --backend vllm_local

lightnav-ws-client --server ws://localhost:8050 --video clip.mp4 --fps 4 \
    --instruction "follow the person in the red shirt"
```

`--task vln` 选择导航提示词。如果检查点**不**自带解码器，则需要显式传入：`--action_tokenizer_bundle /path/to/action_tokenizer`（参见 [CONFIGURATION.md](CONFIGURATION.md)）。

### Python API

```python
from lightnav.tracking import build_tracking_agent

agent = build_tracking_agent("checkpoints/LightNav-0")   # decoder read from the checkpoint
agent.reset(instruction="follow the person in the red shirt")
for frame in rgb_frames:            # HWC uint8 RGB
    agent.observe(frame)
waypoints, raw_text, latency_ms = agent.predict_waypoints(agent.instruction)   # (H, 3)
```

## 仿真演示

[`mujoco_demo/`](../mujoco_demo/) 是一个自包含的 MuJoCo TurtleBot，运行在捆绑的 ProcTHOR 场景中——客户端侧无需 ROS、无需 Habitat、无需 GPU：

```bash
cd mujoco_demo && ./run.sh        # needs uv; then open http://127.0.0.1:8088
```

将 Web 控制台指向你的 `lightnav-serve` 地址并输入指令；它使用与 [`robot_deploy/`](../robot_deploy/README.md) 中真实机器人相同的 MPC 和客户端协议进行驱动。

![MuJoCo 演示：仿真机器人根据语言指令导航到垃圾桶](assets/mujoco_demo.gif)

## 评估

| 基准测试 | 划分 | 回合数 | 成功半径 |
|---|---|---|---|
| VLN-CE R2R | `val_unseen` | 1,839 | 3.0 m |
| VLN-CE RxR（en-US + en-IN） | `val_unseen` | 3,669 | 3.0 m |
| ObjectNav HM3D v1 | `val` | 2,000 | 0.1 m |
| ObjectNav MP3D v1 | `val` | 2,195 | 0.1 m |
| ObjectNav HM3D-OVON | `val_seen` / `val_seen_synonyms` / `val_unseen` | 每个 3,000 | 0.25 m |
| EVT-Bench（DT / STT） | `val`，30 个分片 | 每个 1,405 | SR / TR / CR |

### Habitat

每个 GPU 一个环境服务器 + 一个评估客户端，自动分片并合并：

```bash
MODEL_PATH=/path/to/hf_ckpt bash scripts/eval_habitat.sh                                  # R2R, all GPUs
MODEL_PATH=/path/to/hf_ckpt HABITAT_CONFIG=habitat_server/configs/vlnce_rxr.yaml \
    LANGUAGES="en-US en-IN" GPU_IDS="0 1" bash scripts/eval_habitat.sh                     # RxR
MODEL_PATH=/path/to/hf_ckpt TASK=objectnav HABITAT_CONFIG=habitat_server/configs/objectnav_hm3d_v1.yaml \
    SPLIT=val bash scripts/eval_habitat.sh                                                 # HM3D v1
MODEL_PATH=/path/to/hf_ckpt TASK=objectnav HABITAT_CONFIG=habitat_server/configs/objectnav_mp3d.yaml \
    SPLIT=val bash scripts/eval_habitat.sh                                                 # MP3D v1
MODEL_PATH=/path/to/hf_ckpt TASK=objectnav HABITAT_CONFIG=habitat_server/configs/objectnav_ovon.yaml \
    SPLIT=val_unseen SUCCESS_DISTANCE=0.25 bash scripts/eval_habitat.sh                    # HM3D-OVON (also val_seen / val_seen_synonyms)
```

结果保存在 `output/habitat_<task>_<timestamp>/summary.json`（VLN-CE 为 SR / OS / SPL / NDTW / NE；ObjectNav 为 SR / SPL）。添加 `CLIENT_ARGS="--save_video"` 可生成每回合的叠加视频。单进程用法、参数和输出：[EVAL_HABITAT.md](EVAL_HABITAT.md)。

### EVT-Bench

启动跟踪服务器，运行 30 个分片，用 `analyze_results.py` 聚合：

```bash
MODEL_PATH=checkpoints/LightNav-0 \
    NUM_GPUS=2 SERVERS_PER_GPU=4 EVT_BENCH_REPO=$HOME/EVT-Bench TASK_VARIANTS="dt stt" \
    bash scripts/eval_evt_bench.sh
```

保持 `CHUNKS=30`（分片数量是基准测试定义的一部分）。详细信息、下颌相机 FOV 选项和指标定义：[EVAL_EVT_BENCH.md](EVAL_EVT_BENCH.md)。

## 真实机器人部署

模型运行在 `lightnav-serve` 背后的 GPU 主机上；机器人运行一个轻量级 WebSocket 客户端（任何语言），它流式传输 JPEG 帧 + 指令，并在每个控制周期执行返回的第一个路点：

```python
import base64, json
from websockets.sync.client import connect

with connect("ws://gpu-host:8050", max_size=64 * 1024 * 1024) as ws:
    ws.send(json.dumps({"action": "login", "data": {"clientId": "robot-01"}})); ws.recv()
    ws.send(json.dumps({"action": "reset", "data": {}})); ws.recv()            # new episode
    for seq, jpeg in enumerate(camera_jpegs):
        ws.send(json.dumps({"action": "next", "data": {"seq": seq,
                            "image": base64.b64encode(jpeg).decode(),
                            "instruction": "follow the person in the red shirt"}}))
        data = json.loads(ws.recv())["data"]
        if data["rc"] == 0 and "actions" in data:
            fwd, lat, yaw = data["actions"]["actions"][0]                     # robot-local, +lat = left
            if data["stop"]: break
```

路点行本身不携带时间基准：用 `dt` = 你的控制周期来换算命令 `v = fwd / dt`、`w = yaw / dt`，或者像参考客户端那样按每步最大值进行归一化。非 16:9 的相机可以通过 `--aspect_mode keep` 在不压缩的情况下使用（[CONFIGURATION.md](CONFIGURATION.md)）。多个机器人可以共享一个服务器（会话会进行微批处理）。服务器参数、完整协议和录制：[DEPLOYMENT.md](DEPLOYMENT.md)、[PROTOCOL.md](PROTOCOL.md)。

不想自己编写机器人端？[`robot_deploy/`](../robot_deploy/) 是一个完整的 ROS 2 机器人端栈——相机驱动、此 WebSocket 客户端、MPC 路点跟踪器和 Web 控制面板——带有 Unitree Go2 和 LimX TRON 1 的适配器，以及一个[自带机器人](../robot_deploy/README.md#bring-your-own-robot)适配器接口。

## 可视化

每次预测都可以在机器人自身的帧上渲染为地平面轨迹带、指向标记和遥测 HUD：

```bash
lightnav-serve ... --record_dir output/episodes --cam_hfov_deg 112 --cam_height 0.45   # record on the server
lightnav-render output/episodes                                                          # -> traj_pointing.mp4
CLIENT_ARGS="--save_video" MODEL_PATH=... bash scripts/eval_habitat.sh                   # per-episode eval videos
```

参见 [VISUALIZATION.md](VISUALIZATION.md)。

## 参考文档

| 文档 | 内容 |
|---|---|
| [CONFIGURATION.md](CONFIGURATION.md) | 检查点布局、动作解码器、`eval_config.json`、所有服务器 / CLI 参数 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 真实机器人部署、客户端循环、速度映射、Docker、Python API |
| [PROTOCOL.md](PROTOCOL.md) | 基于 WebSocket 的 JSON 通信协议 |
| [EVAL_HABITAT.md](EVAL_HABITAT.md) | VLN-CE / ObjectNav 评估客户端、多 GPU 分片、输出模式 |
| [HABITAT_SERVER.md](HABITAT_SERVER.md) | Habitat conda 环境、数据集、环境服务器 CLI |
| [EVAL_EVT_BENCH.md](EVAL_EVT_BENCH.md) | EVT-Bench 设置、分片、指标 |
| [VISUALIZATION.md](VISUALIZATION.md) | 叠加渲染、录制布局、`lightnav-render` |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Lint / 测试命令、GPU 冒烟测试（`scripts/smoke_gpu.sh`） |
| [../robot_deploy/README.md](../robot_deploy/README.md) | ROS 2 机器人端栈：全新机器设置、各机器人启动、Web 面板、适配器接口 |
| [../mujoco_demo/README.md](../mujoco_demo/README.md) | 自包含 MuJoCo 仿真演示：捆绑场景、Web 控制台、与 robot_deploy 相同的 MPC/协议 |
