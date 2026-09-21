<!--
  Auto-translated from docs/EVAL_HABITAT.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](EVAL_HABITAT.md)

# Habitat 评估：VLN-CE（R2R / RxR）与 ObjectNav（HM3D v1/v2 / MP3D / HM3D-OVON）

评估分为两个进程：

* **Habitat 环境服务器**（`habitat_server/`，独立的 conda 环境，不含 torch）：渲染仿真器，通过一个 ZMQ REP socket 暴露一个环境并计算指标。conda 配置、数据集和 CLI 参见 [HABITAT_SERVER.md](HABITAT_SERVER.md)。
* **评估客户端**（`lightnav-eval-habitat`，`lightnav` 环境，GPU）：加载 checkpoint，连接服务器，运行 episode 并写出汇总。

## 基准测试

| 任务 | 服务器配置 | 划分 | Episode 数 | 相机 | 成功半径 |
|---|---|---|---|---|---|
| R2R (VLN-CE) | `habitat_server/configs/vlnce_r2r.yaml` | `val_unseen` | 1,839 | 480x270，hfov 120，高度 0.88 m | 3.0 m |
| RxR (VLN-CE) | `habitat_server/configs/vlnce_rxr.yaml` | `val_unseen` | 3,669（使用 `--languages en-US en-IN`，共 11,006） | 同上 | 3.0 m |
| HM3D ObjectNav v1 | `habitat_server/configs/objectnav_hm3d_v1.yaml` | `val` | 2,000（20 个场景 x 6 个类别） | 同上 | 0.1 m（到视点） |
| HM3D ObjectNav v2 | `habitat_server/configs/objectnav_hm3d_v2.yaml` | `val` | 1,000（HM3D v0.2 场景） | 同上 | 0.1 m；**需要 `--navmesh-cell-height 0.05`** |
| MP3D ObjectNav v1 | `habitat_server/configs/objectnav_mp3d.yaml` | `val` | 2,195（21 个类别） | 同上 | 0.1 m（到视点） |
| HM3D-OVON | `habitat_server/configs/objectnav_ovon.yaml` | `val_seen`、`val_seen_synonyms`、`val_unseen` | 各 3,000（36 个场景，开放词汇） | 同上 | 0.25 m |

RxR 语言划分：hi-IN 3,669 / te-IN 3,668 / en-IN 2,446 / en-US 1,223 个 episode。
英文数据在 `--languages en-US en-IN` 上报告。

所有任务均使用 `velocity_control` 动作，上限 500 步。解码为贪心。

## 1. 启动环境服务器

在 habitat conda 环境中（每个 GPU / 端口一个服务器）：

```bash
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve \
    --task vlnce --config habitat_server/configs/vlnce_r2r.yaml \
    --split val_unseen --port 5555 --ready-file /tmp/habitat_5555.ready
```

ObjectNav 变体：

```bash
# HM3D ObjectNav v1 (success distance defaults to 0.1 m)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve \
    --task objectnav --config habitat_server/configs/objectnav_hm3d_v1.yaml \
    --split val --port 5555

# HM3D ObjectNav v2: the re-baked navmesh is REQUIRED (see "Navmesh alignment" below)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve \
    --task objectnav --config habitat_server/configs/objectnav_hm3d_v2.yaml \
    --split val --navmesh-cell-height 0.05 --port 5555

# MP3D ObjectNav v1 (same defaults as HM3D v1)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve \
    --task objectnav --config habitat_server/configs/objectnav_mp3d.yaml \
    --split val --port 5555

# HM3D-OVON: success distance 0.25 m; splits: val_seen, val_seen_synonyms, val_unseen
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve \
    --task objectnav --config habitat_server/configs/objectnav_ovon.yaml \
    --split val_unseen --success-distance 0.25 --port 5555
```

注意事项：

* `HABITAT_SIM_GPU_ID` 选择渲染 GPU。**不要**据此推导 `CUDA_VISIBLE_DEVICES`；habitat-sim 通过 UUID 匹配 CUDA 和 EGL 设备，需要看到所有 GPU。
* 服务器仅在仿真器启动后才写入 `--ready-file`；在启动客户端之前等待它。
* 传感器分辨率来自 yaml（480x270）。仅当你确实想更改时才传入 `--image-height/--image-width`；参考数值使用 yaml 中的值。

## 2. 运行客户端

在 `lightnav` 环境中：

```bash
lightnav-eval-habitat \
    --model_path /path/to/checkpoint \
    --server tcp://localhost:5555 \
    --backend vllm_local \
    --episodes -1 \
    --output_dir output/r2r
```

为 RxR 添加 `--languages en-US en-IN`。`--episodes -1`（默认）运行整个划分：
当服务器的 episode 迭代器循环回到已见过的 `(scene_id, episode_id)` 时，客户端停止。`--episodes N` 在接纳 `N` 个 episode 后停止。

### 客户端标志

| 标志 | 默认值 | 含义 |
|------|---------|---------|
| `--model_path DIR` | 必填 | checkpoint 目录（其 `eval_config.json` 提供处理参数） |
| `--server ADDR` | `tcp://localhost:5555` | 环境服务器 ZMQ 地址 |
| `--backend {hf,vllm_local}` | `vllm_local` | 进程内 vLLM（推荐）或普通 transformers |
| `--episodes N` | `-1` | `<= 0` = 完整划分（在第一个重复的 episode 键处停止），否则在接纳 N 个 episode 后停止 |
| `--max_steps N` | `500` | 客户端每 episode 步数上限（服务器在其自身的 `--max-steps` 处截断） |
| `--no_force_stop` | 关闭 | 默认情况下，预算的最后一个动作是显式 STOP（零速度），因此步数耗尽的 episode 以 `agent_stop` 结束，Success / SPL 在最终位姿处测量；传入此项则让环境截断（每个超时 episode 的 `success=0`）。按 episode 记录为 `forced_stop` |
| `--output_dir DIR` | `output/habitat_eval` | `results.jsonl` 和 `summary.json` 的输出位置 |
| `--languages L [L ...]` | 无 | 仅 RxR：保留 `info["language"]` 在列表中的 episode；跳过的 episode 不计入 |
| `--action_tokenizer_bundle DIR` | 环境变量 `ACTION_TOKENIZER_BUNDLE` | RVQ 解码器（见下文） |
| `--gpu_memory_utilization F` | `0.65` | vLLM GPU 显存占比 |
| `--max_num_seqs N` | `1` | vLLM 批宽度（每个客户端一个环境，故为 1） |
| `--num_history_frames N` | 来自 `eval_config.json` | 覆盖历史窗口（通常不设置） |
| `--max_new_tokens N` | `64` | 每步解码上限；当更小时自动提升为 grounding 前缀 + 动作 token |
| `--zmq_timeout_ms N` | `600000` | 每次尝试的接收超时（Habitat 场景加载较慢） |
| `--verbose` | 关闭 | 每步一行，包含原始模型文本和所选 waypoint |
| `--save_video` | 关闭 | 为每个 episode 写出 `<output_dir>/videos/<episode_id>.mp4`（预测轨迹、指向标记、叠加在 agent 帧上的 HUD；每步一帧）。需要 `pip install -e ".[video]"` |
| `--video_fps N` | `10` | 保存视频的播放帧率 |
| `--hfov_deg F` | `120.0` | 用于轨迹叠加的 agent 相机水平 FOV（随附的 yaml） |
| `--cam_height F` | `0.88` | 用于轨迹叠加的 agent 相机高度（米）（随附的 yaml） |
| `--waypoint_dt_s F` | `0.1` | HUD 速度读数假定的每 waypoint 行秒数 |
| `--record_dir DIR` | 关闭 | 同时记录原始 episode（JPEG 帧 + 每步记录）以供 `lightnav-render` 使用 |

解码为贪心（温度 0）；客户端从不触碰采样旋钮。可视化标志在 [VISUALIZATION.md](VISUALIZATION.md) 中描述；它们都不会改变评估。

### 动作解码器

策略需要知道如何将模型的轨迹 token 转换为 waypoint。
按以下顺序解析：

1. 显式标志 `--action_tokenizer_bundle <dir>`（RVQ bundle，`<act_l*>` token）；
2. checkpoint 旁边的 `eval_config.json` 快照
   （`tasks.*.action_tokenizer.bundle_path`），当该路径存在时；
3. 同级目录 `<model_path>/action_tokenizer/`（带 `manifest.json` 的 RVQ bundle）。

发布的 checkpoint 自带其 bundle，因此无需解码器标志。错误的
`--action_tokenizer_bundle` 会以显式消息报告，但注意*何时*：解码器在推理引擎之后加载，因此只有在权重加载完成后（数十秒）才会显现，而非在参数解析时。

### Navmesh 对齐（HM3D ObjectNav v2）

HM3D 为每个场景提供一个 `<scene>.basis.navmesh`，使用 habitat 默认值
（`cell_height=0.20`）烘焙。ObjectNav **v2** episode——起始位置和目标视点
均如此——是在 `cell_height=0.05` 烘焙的 navmesh 上生成的，因此在随附的 mesh 上
每个 v2 视点都恒定地位于可行走表面*下方* 0.05 / 0.10 / 0.15 m（因场景而异）。
`geodesic_distance` 保留该垂直残差（`geo = sqrt(h^2 + offset^2)`），因此
`distance_to_goal` 获得等于该偏移量的硬下限，官方的 0.1 m 成功
半径最终测量的是数据对齐而非策略。

`--navmesh-cell-height 0.05`（启动器：`NAVMESH_CELL_HEIGHT=0.05`）通过在加载时通过公共 `sim.recompute_navmesh` API 使用 yaml 中的 agent 半径 / 高度重新烘焙每个场景的 navmesh 来修复此问题。该钩子包装 `sim.reconfigure`，因此场景的第一个
episode（及其 SPL 分母）已在重新烘焙的 mesh 上评分；重新烘焙失败会记录警告并回退到随附的 navmesh。对 mesh 本身的影响微乎其微
（可导航区域在 ~2% 以内，起始/目标可达性不变，每场景 ~0.1-0.15 s）。

启用时，服务器日志显示：

```
[navmesh] rebake hook installed (cell_height=0.05)
[navmesh] rebaked TEEsavR23oF at cell_height=0.05 (r=0.18, h=0.88): ok=True area=62.7m2 in 88ms
```

其他基准测试的情况（存储目标与加载 navmesh 的垂直偏移）：
HM3D v1、MP3D 和 R2R 是干净的（零偏移），必须在**不带**该标志的情况下运行；RxR 的
最差偏移（0.03 m）在其 3.0 m 半径下无关紧要；HM3D-OVON 带有相同的
0-0.15 m 偏移，但其 0.25 m 半径吸收了它们（实测：SR 变化 < 1.2 个百分点，
三个划分上 p > 0.3）——那里也保持关闭，以便数值与先前的 OVON 评估保持可比。

### 速度映射

每一步策略解码 `(H, 3)` 机器人局部 waypoint `[forward_m, lateral_m, yaw_rad]`，
取第一个 forward 或 yaw 分量非零的行，并发送

```
linear_velocity  = clip(2 * (forward_m / dt - lin_min) / (lin_max - lin_min) - 1, -1, 1)
angular_velocity = clip(2 * (deg(yaw_rad) / dt - ang_min) / (ang_max - ang_min) - 1, -1, 1)
```

其中 `dt`、`lin_*` 和 `ang_*` 是服务器报告的 env 的 `velocity_control` 设置
（`habitat_time_step`、`lin_vel_range`、`ang_vel_range`）。零 waypoint（或
无法解码的输出）映射为零速度，Habitat 将其视为 STOP 并结束 episode。

## 3. 并行评估（每个 GPU 一个分片）

`scripts/eval_habitat.sh` 在本地 GPU 上完成全部工作：每个 GPU 一个环境服务器 + 一个
评估客户端（模型和仿真器共享 GPU），各自在划分的不相交分片上，然后将分片合并为一个 `summary.json`：

```bash
# R2R on every visible GPU
MODEL_PATH=/path/to/checkpoint bash scripts/eval_habitat.sh
# RxR (English) on GPUs 0 and 1
MODEL_PATH=/path/to/checkpoint HABITAT_CONFIG=habitat_server/configs/vlnce_rxr.yaml \
    LANGUAGES="en-US en-IN" GPU_IDS="0 1" bash scripts/eval_habitat.sh
# HM3D ObjectNav v2 (NAVMESH_CELL_HEIGHT is required, see "Navmesh alignment")
MODEL_PATH=/path/to/checkpoint TASK=objectnav HABITAT_CONFIG=habitat_server/configs/objectnav_hm3d_v2.yaml \
    SPLIT=val NAVMESH_CELL_HEIGHT=0.05 bash scripts/eval_habitat.sh
# MP3D ObjectNav v1
MODEL_PATH=/path/to/checkpoint TASK=objectnav HABITAT_CONFIG=habitat_server/configs/objectnav_mp3d.yaml \
    SPLIT=val bash scripts/eval_habitat.sh
# HM3D-OVON (SPLIT=val_seen / val_seen_synonyms / val_unseen)
MODEL_PATH=/path/to/checkpoint TASK=objectnav HABITAT_CONFIG=habitat_server/configs/objectnav_ovon.yaml \
    SPLIT=val_unseen SUCCESS_DISTANCE=0.25 bash scripts/eval_habitat.sh
```

旋钮（环境变量，见脚本头部）：`GPU_IDS` / `NUM_GPUS`（默认：来自
`nvidia-smi` 的所有 GPU）、`TASK`、`HABITAT_CONFIG`、`SPLIT`、`SUCCESS_DISTANCE`、`DATA_PATH`、
`SCENES_DIR`、`LANGUAGES`、`EPISODES`（每分片）、`BACKEND`、`GPU_MEM_UTIL`（0.65）、
`CLIENT_ARGS`（例如 `"--save_video"`）、`HABITAT_CONDA_ENV`/`HABITAT_PYTHON`、
`INFER_VENV`/`CLIENT_PYTHON`、`OUTPUT_ROOT`（默认 `output/habitat_<task>_<timestamp>`）。
输出：每个 GPU 的 `OUTPUT_ROOT/shard_<i>/` 加上合并的 `OUTPUT_ROOT/results.jsonl` 和
`summary.json`；日志在 `OUTPUT_ROOT/logs/` 下。脚本退出时服务器和客户端被终止。合并也可以手动运行：

```bash
lightnav-eval-merge output/r2r                 # merges output/r2r/*/results.jsonl -> output/r2r/summary.json
lightnav-eval-merge shard_a shard_b --output merged
```

`summary.json` 中的每个指标都是未加权的每 episode 均值，因此合并值
正是拼接后 episode 的汇总；`total_time_sec` 是最长分片的时间（墙钟），
`shards` 列出各分片的 episode 数。

手动等价方式（服务器确定性地划分划分：episode 按
场景排序，切成 `split-num` 块）：

```bash
# GPU i of N: one server + one client pair, distinct port and output dir
HABITAT_SIM_GPU_ID=$i python -m lightnav_habitat.serve --task vlnce \
    --config habitat_server/configs/vlnce_r2r.yaml --split val_unseen \
    --split-id $i --split-num $N --port $((5555 + i)) --ready-file /tmp/hab_$i.ready

CUDA_VISIBLE_DEVICES=$i lightnav-eval-habitat --model_path /path/to/checkpoint \
    --server tcp://localhost:$((5555 + i)) --episodes -1 --output_dir output/r2r/shard_$i
```

每个 GPU 运行一对，然后 `lightnav-eval-merge <parent-dir>`。

## 4. 输出文件

`<output_dir>/results.jsonl` 每个完成的 episode 得到一行 JSON（写入时 fsync，
因此被终止的运行会保留已完成的部分）。该文件是仅追加的：每次运行使用新的
`--output_dir`，否则先前运行的行会留在其中（`summary.json` 仅
覆盖当前运行）：

```json
{"episode_id": "episode_000", "habitat_episode_id": "1234", "scene_id": "...",
 "rollout_idx": 0, "success": 1.0, "oracle_success": true, "spl": 0.81, "ndtw": 0.77,
 "soft_spl": 0.0, "object_category": "", "steps": 42, "final_distance": 1.9,
 "min_distance": 1.9, "instruction": "Walk past the ...",
 "termination_reason": "agent_stop", "termination_details": {...}}
```

`min_distance` 是已执行步骤中 `distance_to_goal` 的最小值。`oracle_success`
在存在时使用服务器的 `oracle_success` 指标，否则使用 `min_distance < 3.0 m`
（VLN-CE）/ `< 0.1 m`（ObjectNav）。

使用 `--save_video` 时，每条记录还带有 `"video": "videos/episode_000.mp4"`（相对于
`output_dir`），且 `<output_dir>/videos/` 为每个 episode 保存一个 mp4：每一步策略
所依据的帧，带有预测轨迹带、指向标记和 HUD
（指令、GO/STOP、步数、第一 waypoint 速度），加上终端观测。
`--record_dir DIR` 额外将原始 episode（帧 + 记录）写入
`DIR/run_<timestamp>/eval/episode_NNN/`，之后 `lightnav-render DIR` 可用其他
设置渲染。参见 [VISUALIZATION.md](VISUALIZATION.md)。

`<output_dir>/summary.json` 在结束时写入。VLN-CE（无 `object_category`）：

```json
{
  "num_episodes": 1839,
  "metrics": {"SR_success_rate_pct": 0.0, "OS_oracle_success_pct": 0.0, "SPL_pct": 0.0,
              "NDTW_pct": 0.0, "NE_navigation_error_m": 0.0},
  "table_format": "SR / OS / SPL / NDTW / NE",
  "avg_steps": 0.0,
  "total_time_sec": 0.0,
  "episodes": [{"episode_id", "habitat_episode_id", "scene_id", "rollout_idx", "success",
                "oracle_success", "spl", "ndtw", "steps", "final_distance", "min_distance",
                "instruction"}],
  "model": "/path/to/checkpoint",
  "backend": "vllm_local"
}
```

ObjectNav（任何结果的 `object_category` 非空）：

```json
{
  "num_episodes": 2000,
  "metrics": {"SR_success_rate_pct": 0.0, "SPL_pct": 0.0, "SoftSPL_pct": 0.0,
              "NE_navigation_error_m": 0.0},
  "table_format": "SR / SPL / SoftSPL / NE",
  "per_category_sr": {"chair": 0.0, "...": 0.0},
  "avg_steps": 0.0,
  "total_time_sec": 0.0,
  "episodes": [{"episode_id", "habitat_episode_id", "scene_id", "rollout_idx", "success",
                "spl", "soft_spl", "object_category", "steps", "final_distance",
                "min_distance"}],
  "model": "/path/to/checkpoint",
  "backend": "vllm_local"
}
```

百分比为每 episode 均值 x 100，四舍五入到 2 位小数；`NE` 是平均最终
`distance_to_goal`，单位为米。

## Python API

```python
from lightnav.habitat import HabitatEvalConfig, run_habitat_eval

results = run_habitat_eval(HabitatEvalConfig(
    model_path="/path/to/checkpoint",
    server="tcp://localhost:5555",
    episodes=-1,
    output_dir="output/r2r",
))
```

`run_habitat_eval` 还接受 `env_factory`、`policy_factory` 和 `engine_factory`
关键字参数以替换为测试替身。

## 故障排查

* `ConnectionError: Timeout waiting for response ... 'reset'`：服务器仍在加载场景，或者未运行。客户端每次尝试会等待 `--zmq_timeout_ms`（600 秒），并在不重新发送的情况下重试接收两次。
* `KeyError: Habitat env did not expose velocity-control config keys`：该服务器不是来自 `habitat_server/` 的服务器（它必须在 `info` 中报告 `habitat_time_step`、`lin_vel_range`、`ang_vel_range`）。
* `FileNotFoundError: Could not resolve the action decoder`：请显式传入 `--action_tokenizer_bundle`（见上文）。
* 每个 episode 都在一步后以 `agent_stop` 结束：模型输出无法用所选解码器解码（bundle 错误）；请使用 `--verbose` 运行以查看原始文本。
