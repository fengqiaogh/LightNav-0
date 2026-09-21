<!--
  Auto-translated from docs/EVAL_EVT_BENCH.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](EVAL_EVT_BENCH.md)

# 在 EVT-Bench 上评估（具身视觉跟踪）

[EVT-Bench](https://github.com/wsakobe/TrackVLA)（来自 TrackVLA 论文）对一台必须在布满干扰人物的 HM3D / MP3D 场景中跟随目标人物的机器人进行评分。其驱动程序（`run.py`）在 Python 3.9 conda 环境中运行 Habitat，而 `lightnav` 需要 Python 3.11，因此双方通过 [PROTOCOL.md](PROTOCOL.md) 中的 WebSocket 协议通信：

```
EVT-Bench run.py (py3.9, habitat)  --ws://localhost:PORT-->  lightnav-serve (py3.11, GPU)
   trackvla_client_agent.py                                     tracking checkpoint
   jaw RGB frame -> base64 JPEG                                 waypoints [fwd, lat, yaw] x H
   first waypoint -> agent_1_base_velocity
```

所有 EVT-Bench 侧的内容（habitat-lab fork、任务配置、数据集、`analyze_results.py`）都留在你的 EVT-Bench 检出目录中。本仓库只提供客户端 agent、`run.py` 的补丁、配置修补器和编排脚本（见 [`evt_bench/`](../evt_bench/README.md)）。

## 1. 安装 EVT-Bench

按照上游 README 操作；简而言之：

```bash
conda create -n evt_bench python=3.9 cmake=3.14.0
conda activate evt_bench
conda install habitat-sim==0.3.1 withbullet -c conda-forge -c aihabitat
git clone https://github.com/wsakobe/TrackVLA ~/EVT-Bench
cd ~/EVT-Bench
pip install -e habitat-lab
pip install websocket-client          # needed by trackvla_client_agent.py
```

数据全部位于 `~/EVT-Bench/data/` 下：

- `scene_datasets/hm3d/{train,val,minival}/...`（HM3D，包括 `*.basis.glb` 文件和 `hm3d_annotated_basis.scene_dataset_config.json`）以及 `scene_datasets/mp3d/<scene>/<scene>.glb`（MP3D）；val 回合共引用两个数据集中的 101 个场景。
- 人形 avatar：`python download_humanoid_data.py`（若失败则回退到上游 README 中的 Google Drive 链接）-> `data/humanoids/humanoid_data/...`。
- 跟踪回合随仓库提供：`data/datasets/track/{DT,STT,AT}/val/val.json.gz`（每个变体 1,405 个回合；DT = 干扰物跟踪，STT = 单目标跟踪，AT = 模糊跟踪）。

无头渲染需要可用的 EGL / GL 库，且每个 Habitat 进程需要一块 GPU；每个进程还会使用几 GB 内存。

## 2. 将客户端添加到 EVT-Bench

```bash
cp /path/to/LightNav-0/evt_bench/trackvla_client_agent.py ~/EVT-Bench/
cd ~/EVT-Bench && git apply /path/to/LightNav-0/evt_bench/run_py.patch
```

该补丁为 `run.py` 添加一个 `elif model_name == 'trackvla':` 分支，该分支从复制的文件中导入 `evaluate_agent`，并将 `--model-path` 作为服务器 URL 传入。如果 `git apply` 因上游 `run.py` 变动而报错，请手动添加该分支：它就是 `baseline` 分支，加上 `from trackvla_client_agent import evaluate_agent` 和 `evaluate_agent(config, dataset_split, save_path, server_url=model_path)`。

客户端每一步的行为：读取 `observations["agent_1_articulated_agent_jaw_rgb"][:, :, :3]`（Spot 下颌相机，480x270），进行 JPEG 编码，发送 `{"action": "next", "data": {"seq", "image", "instruction"}}`，并将回复的第一个路点映射为基础速度动作 `[clip(fwd / 0.375), clip(lat / 0.25), clip(yaw / (pi/20))]`，范围在 `[-1, 1]^3` 内（+横向 = 左，+偏航 = 逆时针）。当 `rc` 非零或缺少 `actions` 字段时，它重复上一个动作。它从不特殊处理 `stop`：零轨迹直接变为零速度，回合通过 EVT-Bench 自身的规则结束（300 步，"距离过远超过 20 步" -> `Lost`，碰撞 -> `Collision`）。超时：`TRACKVLA_WS_TIMEOUT`（秒，默认 60）是每步的接收超时。

评估循环本身逐步镜像 EVT-Bench 自己的驱动程序，包括它们的怪癖：多智能体动作元组只步进 `agent_0`（目标）、`agent_1`（机器人）和干扰物 `agent_2..agent_5`（任务配置定义了 `agent_2..agent_8`；额外的干扰物静止不动，与上游完全一致），且每回合的结果 JSON 及其 `success` 规则保持不变。`EVT_NUM_DISTRACTORS=6` 会额外步进 `agent_6` 和 `agent_7`（两个额外的移动干扰物，更严格的设置）；使用不同值得到的数字不可比较，因此请始终说明你使用的是哪一个。

## 3. 运行

启动服务器，等待就绪，运行所有分片，聚合：

```bash
cd /path/to/LightNav-0
# the checkpoint ships its decoder; set ACTION_TOKENIZER_BUNDLE=/path/to/rvq_bundle only to override it
MODEL_PATH=/path/to/checkpoint \
NUM_GPUS=2 SERVERS_PER_GPU=4 \
EVT_BENCH_REPO=$HOME/EVT-Bench EVT_CONDA_ENV=evt_bench \
TASK_VARIANTS="dt" \
bash scripts/eval_evt_bench.sh
```

该脚本调用 [`scripts/start_servers.sh`](../scripts/start_servers.sh)（每个端口一个 `lightnav-serve --task tracking` 进程，共 `NUM_GPUS x SERVERS_PER_GPU` 个，vLLM 后端使用 `gpu_memory_utilization = 0.85 / SERVERS_PER_GPU`），轮询每个端口的 `.ready` 文件，然后以 `NUM_GPUS x SERVERS_PER_GPU x CLIENTS_PER_SERVER` 个进程为一批，为分片 `0..CHUNKS-1` 运行 `run.py`。分片 `i` 与服务器 `i % TOTAL_SERVERS` 通信，并在该服务器的 GPU 上渲染（`CUDA_VISIBLE_DEVICES`）。脚本退出时服务器会被终止。

所有可调项都是环境变量；`scripts/eval_evt_bench.sh` 的头部列出了它们。重要的有：

| 变量 | 默认值 | 含义 |
|----------|---------|---------|
| `MODEL_PATH` | 必填 | checkpoint 目录 |
| `ACTION_TOKENIZER_BUNDLE` | 可选 | RVQ bundle 目录；覆盖 checkpoint 自带的解码器 |
| `BACKEND` | `vllm_local` | `vllm_local` 或 `hf` |
| `NUM_GPUS`、`SERVERS_PER_GPU`、`BASE_PORT` | 1、4、8050 | 服务器拓扑；在小 GPU 上减少 `SERVERS_PER_GPU` |
| `CLIENTS_PER_SERVER` | 1 | 每个服务器的 Habitat 进程数（服务器会对并发会话进行微批处理） |
| `EVT_BENCH_REPO` | `$HOME/EVT-Bench` | 你的检出目录 |
| `EVT_CONDA_ENV` 或 `EVT_PYTHON` | `evt_bench` | conda 环境名，或显式解释器 |
| `TASK_VARIANTS` | `dt` | `dt stt at` 中的任意组合，针对同一批服务器顺序运行 |
| `CHUNKS` | 30 | 数据集分片数（`--split-num`）；保持 30，见下文 |
| `EVT_JAW_HFOV`、`EVT_JAW_HEIGHT` | 空 | 下颌相机覆盖，见下文 |
| `OUTPUT_ROOT` | `$EVT_BENCH_REPO/exp_results/lightnav_<timestamp>` | 结果；每个变体一个子目录 |
| `READY_TIMEOUT_S` | 1800 | 等待服务器的时间（vLLM 冷启动可能需要数分钟） |

手动运行一个分片（服务器已在运行）：

```bash
cd ~/EVT-Bench && conda activate evt_bench
PYTHONPATH=habitat-lab python run.py --run-type eval --model-name trackvla \
  --exp-config habitat-lab/habitat/config/benchmark/nav/track/track_infer_dt.yaml \
  --split-num 30 --split-id 0 --model-path ws://localhost:8050 \
  --save-path exp_results/manual/dt
```

### 为什么 `CHUNKS=30`

`run.py` 使用 `dataset.get_splits(split_num)[split_id]` 对 1,405 个回合进行分片。EVT-Bench 自己的驱动程序从**分片的第一个回合**读取语言指令，并将其复用于该分片的每个回合，其 `MainHumanoidDetectorSensor` 也以同样方式在第一个回合冻结目标的语义 id。因此分片中后续回合的提示和评分都使用第一个回合的目标。改变分片数量会改变哪些回合共享提示，从而改变数字；EVT-Bench 发表的结果使用 30 个分片（每个约 47 个回合），因此脚本默认使用 30，否则会发出警告。并行度（`NUM_GPUS`、`SERVERS_PER_GPU`、`CLIENTS_PER_SERVER`）只改变墙钟时间，不改变结果。

### 下颌相机视场角（`EVT_JAW_HFOV`）

EVT-Bench 将 Spot 下颌 RGB 相机安装为 hfov 86（480x270），检测器用于评分可见性的全景相机为 hfov 90。我们的跟踪 checkpoint 是在约 115 度中位水平 FOV 渲染的帧上训练的，因此 86 超出其训练分布，会使比较产生偏差；我们使用 `EVT_JAW_HFOV=120` 评估我们的 checkpoint，并保持安装高度不变。将该变量留空（或传入 `EVT_JAW_HFOV=86`）即可完全按上游方式评估。

该覆盖无法通过 `run.py` 的 Hydra `opts` 传入（`trackvla` 分支不会转发它们），因此 `evt_bench/patch_task_config.py` 会将任务 yaml 的修补副本写入 `OUTPUT_ROOT`，脚本将其绝对路径作为 `--exp-config` 传入。`jaw_rgb_sensor` 和 `jaw_panoptic_sensor` 始终一起修补，以便模型和可见性检测器通过同一镜头观察；`hfov` 写为整数（habitat 拒绝浮点数），并保留首行 `# @package _global_`。手动使用：

```bash
python evt_bench/patch_task_config.py \
  ~/EVT-Bench/habitat-lab/habitat/config/benchmark/nav/track/track_infer_dt.yaml \
  /abs/path/track_infer_dt_hfov120.yaml --hfov 120           # [--height 0.7]
```

另一个**非**上游行为的可选项：`EVT_HIDE_ROBOT_MESH=1` 会让客户端将机器人的可视网格缩放为零，使下颌相机看不到机器人本体。默认关闭。

## 4. 结果

驱动程序为每个回合写入 `<save_path>/<scene>/<episode_id>.json`：

```json
{"finish": true, "status": "Normal", "success": 1.0, "following_rate": 0.93,
 "following_step": 279, "total_step": 300, "collision": 0.0}
```

- `status`：`Normal`、`Lost`（距离目标超过 4 m 持续超过 20 个连续步）或 `Collision`（与人类距离小于 0.5 m）。
- `success`：回合提前结束时为 `human_following_success and human_following`，达到 300 步上限时为 `human_following`。`human_following` = 距离在 3 m 以内且目标可见（3,000 < 目标像素 < 全景图像的 30 %）；`human_following_success` 还要求 1 m <= 距离且执行了停止动作。
- `<episode_id>_info.json` 保存逐步轨迹（`step`、`trajectory`、`dis_to_human`、`facing`）。

`analyze_results.py`（上游，从 EVT-Bench 根目录运行）聚合结果目录：

```bash
cd ~/EVT-Bench && python analyze_results.py --path exp_results/lightnav_<ts>/dt [--n N]
# {'episode count:': 1405, 'success rate': SR, 'following rate:': FR, 'collision rate:': CR}
```

- **SR**（成功率）= `success` 为真的回合比例。
- **FR / TR**（跟随率 / 跟踪率）= `sum(following_step) / sum(total_step)`，其中当回合提前结束时，`total_step` 会被提升为 `track_episode_step/<scene>/<episode>.json` 中提供的参考长度。
- **CR**（碰撞率）= `collision` 的均值。

它必须以 EVT-Bench 根目录作为工作目录运行（它相对读取 `track_episode_step/` 并将 `following_info.json` 写入 cwd），并且在第一个回合完成之前会抛出 `ZeroDivisionError`。`--n` 按修改时间将数量限制为前 N 个结果文件，这在评估仍在运行时便于快速查看（`watch -n 60 python analyze_results.py ...`）。编排脚本将每个变体的最后一行保存到 `OUTPUT_ROOT/metrics_<variant>.txt`。

## 5. 故障排除

- `ModuleNotFoundError: magnum` / `websocket`：驱动程序未在 `evt_bench` 环境中运行，或缺少 `websocket-client`。脚本会预先检查两者。
- 分片日志（`OUTPUT_ROOT/logs/eval_<variant>_chunk_<i>.log`）每步显示一行，包含服务器延迟、原始模型文本以及解码出的 `stop` / `visible` 标志。出现 `Server error: {...}` 行表示服务器返回了 `rc != 0`，客户端重复了上一个动作。
- `act()` 内的接收超时不会重试，并会结束该分片。服务器仅在预热推理后才绑定端口，因此第一步不应超时；如果你的 GPU 上 `hf` 后端较慢，请提高 `TRACKVLA_WS_TIMEOUT`。
- 启动分片时出现 `ValueError ... could not be converted to Integer`：非整数 `hfov` 传到了 Habitat；请使用 `patch_task_config.py`，而不是手动编辑 yaml。

## 许可证

EVT-Bench / TrackVLA 在 CC BY-NC-SA 4.0（非商业）下发布。此处不重新分发其中任何内容。`evt_bench/trackvla_client_agent.py` 中的评估循环改编自 EVT-Bench 驱动程序，因此受该许可证覆盖，而非本仓库的许可证；见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
