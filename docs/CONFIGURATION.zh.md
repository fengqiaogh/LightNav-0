<!--
  Auto-translated from docs/CONFIGURATION.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](CONFIGURATION.md)

# 模型资产与参数

检查点布局、动作解码器、`eval_config.json` 以及所有服务器 / CLI 参数。

## 检查点

一个 Hugging Face 目录（或包含 `hf_ckpt/` 的目录），其中含有 `config.json`、
`model*.safetensors`、`tokenizer*`、`processor_config.json`，最好还有
`eval_config.json`。架构必须是原版 `Qwen3VLForConditionalGeneration`；
轨迹 / 动作 token 是嵌入表中的普通行。

## 动作解码器

一个 **RVQ 动作分词器包**：一个目录，其中含有 `manifest.json`、各层级的
码本 `.npy` 文件以及它所指定的 `jacobian_weights` 文件。发布的检查点将其作为
`action_tokenizer/` 一同提供，并由 `eval_config.json` 引用，因此无需标志即可找到；
`--action_tokenizer_bundle` 可覆盖它。

## `eval_config.json`（处理参数）

如果它存在于检查点旁边或上层（搜索会向上遍历四层父目录，因此
`hf_ckpt/`、`global_step_*` 目录和运行根目录都涵盖在内），它会提供必须与训练一致
且无法猜测的处理参数：

```json
{
  "version": 1,
  "common": {"video_size": [224, 320], "pool_enable": true, "pool_spatial": 2,
             "pool_mode": "avg", "pool_stage": "pre_vit"},
  "tasks": {
    "trackvla": {"num_history_frames": 64, "predict_horizon": 10, "video_fps": 4,
                 "slowfast_tiers": null,
                 "action_tokenizer": {"method": "rvq", "bundle_path": "/path/to/action_tokenizer"}},
    "vlnce":    {"num_history_frames": 64, "predict_horizon": 10, "video_fps": 4,
                 "action_tokenizer": {"method": "rvq", "bundle_path": "action_tokenizer"}}
  }
}
```

| 键 | 含义 |
|---|---|
| `common.video_size` | 模型输入帧尺寸 `[H, W]`；每一帧都会被缩放到该尺寸 |
| `common.pool_*` | 视觉 token 的空间池化（`pool_stage` 为 `pre_vit` 或 `post_vit`） |
| `tasks.<task>.num_history_frames` | 每步馈送给模型的历史窗口（帧数） |
| `tasks.<task>.predict_horizon` | 轨迹视界 `H`（每个 chunk 的行数） |
| `tasks.<task>.video_fps` | 检查点训练时的帧率（以该帧率或更快速度发送帧；路点行本身不携带时间基准，见 [DEPLOYMENT.md](DEPLOYMENT.md)） |
| `tasks.<task>.slowfast_tiers` | 可选的多速率历史布局（SlowFast 检查点保留整个 episode） |
| `tasks.<task>.action_tokenizer` | 解码器快照：`{"method": "rvq", "bundle_path"}`；相对路径相对于配置文件所在目录解析 |

`tasks` 以任务为键：`trackvla` 用于跟踪（`--task tracking`），`vlnce` 用于
导航（`--task vln`，以及 Habitat 评估）。这些值会被自动读取；CLI 的
`--num_history_frames`（以及提供时的 `--pool_spatial`）会覆盖它们。没有该文件时，代码
会回退到保守默认值（`num_history_frames=16`、无池化、
`video_size=(224, 320)`），这些值不会与训练过的检查点匹配——请将缺失
`eval_config.json` 视为警告信号。完整 schema：`src/lightnav/eval_config.py`。


### 随检查点一同提供动作解码器

`tasks.<task>.action_tokenizer.bundle_path` 可以是**相对路径**；它会相对于
存放 `eval_config.json` 的目录解析（回退到检查点目录）。发布的检查点以这种方式
提供其解码器：

```
hf_ckpt/
  config.json, model-*.safetensors, tokenizer*, processor_config.json
  eval_config.json          # bundle_path: "action_tokenizer" (both tasks)
  action_tokenizer/         # manifest.json + codebook_l*.npy + jacobian_weights.npy (+ alpha)
```

在这种布局下，`lightnav-serve`、`lightnav-predict`、`lightnav-eval-habitat` 和
`build_tracking_agent()` 无需 `--action_tokenizer_bundle`：解码器会从与服务器任务
匹配的任务条目中获取（`--task tracking` → `trackvla`，`--task vln` → `vlnce`），
然后从其他任务中获取，再从同级目录 `action_tokenizer/<task>` 或
`action_tokenizer/` 中获取。显式标志始终优先。

## 服务器 / CLI 参数

`lightnav-serve` 标志（环境变量名即 `scripts/start_servers.sh` 和
`docker/entrypoint.sh` 所读取的名称）：

| 标志 | 环境变量 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `--model_path` | `MODEL_PATH` | 必填 | 检查点目录 |
| `--action_tokenizer_bundle` | `ACTION_TOKENIZER_BUNDLE` | 来自检查点 | RVQ 包目录；覆盖检查点自带的解码器 |
| `--task` | `TASK` | `tracking` | `tracking`（跟踪提示词，`tasks.trackvla`）或 `vln`（VLN 提示词，`tasks.vlnce`） |
| `--backend` | `BACKEND` | `vllm_local` | `vllm_local` 或 `hf` |
| `--gpu_memory_utilization` | `GPU_MEM_UTIL` | `0.85` | 分配给 vLLM 引擎的 GPU 显存比例 |
| `--max_batch_size` | `MAX_BATCH_SIZE` | `8` | 每个调度 tick 的最大会话数；也用于设置 vLLM 的 `max_num_seqs`。`1` = 严格串行 |
| `--max_wait_ms` | `MAX_WAIT_MS` | `8` | 填充一个批次的最大等待时间；单个请求在 2 ms 后即被冲刷 |
| `--quantization` | `VLLM_QUANT` | 无（bf16） | `fp8_llm_only`：fp8 LLM，bf16 ViT（在 Jetson Thor 上约 1.5×）。在 SM 11.0 上还需设置 `VLLM_DISABLED_KERNELS`；`scripts/serve_thor.sh` 会同时完成这两项。见 [JETSON_THOR.md](JETSON_THOR.md) |
| `--vit_cache_entries` | `VLN_VIT_CACHE_ENTRIES` | 自动（SlowFast 时为 512） | ViT tubelet LRU 容量（`vllm_local`；仅影响速度，绝不影响输出）。长时间机器人会话建议设为 `1024` |
| `--num_history_frames` | `NUM_HISTORY_FRAMES` | 检查点配置 | 历史窗口覆盖值（通常保持未设置） |
| `--pool_spatial` | `POOL_SPATIAL` | 检查点配置 | 空间池化覆盖值 |
| `--aspect_mode` | `ASPECT_MODE` | `stretch` | `stretch`：将每一帧缩放到 `video_size`（训练行为）；`keep`：在相同像素预算下，按会话使用与相机宽高比一致的尺寸（对于 256×448 检查点，4:3 → 288×384） |
| `--max_new_tokens` | `MAX_NEW_TOKENS` | `8` | 每步解码上限的下界（见下文） |
| `--host` / `--port` | `HOST` / `PORT` | `0.0.0.0` / `8050` | 绑定地址 |
| `--ready_file` | – | 无 | 端口绑定后触碰的文件（供启动器使用） |
| `--no_warmup` | – | 关闭 | 在绑定端口前跳过合成预热推理 |
| `--record_dir` | `RECORD_DIR` | 关闭 | 记录每个连接的 episode（帧 + 每步记录），供 `lightnav-render` 使用（见 [DEPLOYMENT.md](DEPLOYMENT.md)） |
| `--record_fps`、`--record_timeline`、`--no_record_images` | `RECORD_FPS`、`RECORD_TIMELINE`、`RECORD_IMAGES` | `10`、`realtime`、图像开启 | 写入清单 / 帧存储的录制默认值 |
| `--cam_hfov_deg`、`--cam_height`、`--traj_forward_offset`、`--waypoint_dt_s` | `CAM_HFOV_DEG`、`CAM_HEIGHT`、`TRAJ_FORWARD_OFFSET`、`WAYPOINT_DT_S` | `90`、`0.5`、自动、`0.1` | 仅由渲染叠加层使用的客户端相机几何与 HUD 约定 |

### MuJoCo 演示参数

`mujoco_demo` 是一个单独的 `uv` 项目。运行 `./run.sh` 以使用其自带的
TurtleBot，或在选择可选的 MicroDuck 后端时使用
`uv run --extra microduck vln-mujoco ...`。MicroDuck 需要两个外部文件：来自
`pollen-robotics/microduck_rl` 的 MJCF，以及来自
`pollen-robotics/microduck-policies` 的 ONNX 策略；下载步骤见
[mujoco_demo/README.md](../mujoco_demo/README.md#microduck-optional)。

| 标志 | 默认值 | 含义 |
| --- | --- | --- |
| `--host` / `--port` | `127.0.0.1` / `8088` | Web 控制台绑定地址 |
| `--vln-server` | 空 | 控制台中显示的默认 LightNav WebSocket URL |
| `--robot` | `turtlebot` | 机器人后端：`turtlebot` 或 `microduck` |
| `--robot-model` | 无 | 外部 MicroDuck MJCF；仅在 `--robot microduck` 时必填 |
| `--walking-policy` | 无 | 外部 MicroDuck ONNX 策略；仅在 `--robot microduck` 时必填 |

引擎级环境变量（无对应标志）：

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `VLN_KV_CACHE_GIB` | 自动 | vLLM KV 缓存大小，单位为 GiB（随 `max_num_seqs` 自动缩放，下限 2 GiB） |
| `VLN_VLLM_ENFORCE_EAGER` | `0` | `1` 禁用 CUDA 图捕获（启动更快，步进更慢） |
| `LIGHTNAV_ATTN` | `sdpa` | `hf` 后端的注意力实现（例如 `flash_attention_2`） |
| `VLN_EVAL_TEMPERATURE` / `TOP_P` / `TOP_K` | 贪心 | 用于实验的采样旋钮；基准测试数值假定它们未设置 |

**解码 token 预算。** 一步会先输出一个*定位前缀*，随后是动作 token：
每个 RVQ 层级一个 `<act_l{d}_*>`。服务器会探测分词器以识别它所知的定位族，
并将生成上限设为
`max(--max_new_tokens, prefix + action_tokens)`，从而省去原本用于到达 `eos` 的解码步，
同时绝不会截断动作。

| 检查点族 | 定位前缀 | token 数 |
|---|---|---|
| 跟踪，旧版 | `<tpos_k>` | 1 |
| 跟踪 + 网格指向 | `<opos_k>` | 1 |
| 导航 + 双指向 | `<apos_A><opos_O>` | 2 |

**GPU 规模。** 4B 检查点的 bf16 权重需要约 10 GB，外加 vLLM KV 缓存；
一块 24 GB GPU 可以轻松地以 `--gpu_memory_utilization 0.85` 服务一个引擎。当
多个服务器共享一块 GPU 时，`scripts/start_servers.sh` 会将利用率除以
`SERVERS_PER_GPU`。

请注意 `--gpu_memory_utilization` 在这里*不*做什么。引擎会传入一个显式的
`kv_cache_memory_bytes`（`VLN_KV_CACHE_GIB`，下限 2 GiB），因此会跳过 vLLM 的
性能分析运行，所以无论该比例是多少，实际用量大致为权重 + 该 KV 缓存 + CUDA 图
（发布的 4B 检查点约 15 GB）。该比例仍作为 vLLM 在启动时对照空闲显存检查的上限，
因此当 GPU 与其他作业共享时应调低它，而当你想要更大的 KV 缓存时，应调高
`VLN_KV_CACHE_GIB`——而不是该比例。

---

## 输入宽高比（`--aspect_mode`）

检查点是在缩放到固定 `common.video_size` 的帧上训练的（发布的检查点为 256×448，
≈16:9）。默认情况下（`stretch`），每个客户端帧无论其宽高比如何都会被缩放到
该尺寸，与训练时完全一致——因此 4:3 相机的画面会以水平方向被挤压的方式到达。

`--aspect_mode keep`（环境变量 `ASPECT_MODE=keep`；也适用于 `lightnav-predict --aspect_mode`、
`lightnav-eval-habitat --aspect_mode`、`build_tracking_agent(aspect_mode=)`）则会在每个会话中
根据其第一帧，选择具有**源宽高比**、面积最接近 `video_size` 且边长均为 32 的倍数
（patch × merge；当检查点在 ViT 之前进行池化时，还需为 pre-ViT 池化因子的倍数）的尺寸。
每帧的视觉 token 数保持在训练预算内，因此历史长度和序列长度不变：

| 相机 | `stretch` | `keep` |
|---|---|---|
| 16:9（480×270、1920×1080） | 256×448 | 256×448（相同） |
| 4:3（640×480） | 256×448（被挤压） | 288×384 |
| 1:1 | 256×448 | 352×352 |

同一会话内的帧必须共享同一尺寸（由第一帧决定；`reset` 会重新开始）。`keep` 避免了
几何畸变，但会改变模型看到的 token 网格，而发布的检查点并未在此网格上训练过——
在依赖它之前，请先在你的机器人上验证。不支持完整原生分辨率（即馈送相机自身的
像素数）。
