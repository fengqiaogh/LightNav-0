<!--
  Auto-translated from docs/DEVELOPMENT.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](DEVELOPMENT.md)

# 开发

```bash
pip install -e ".[test]"   # pytest + pytest-asyncio; not part of the runtime extras
make check                 # ruff check .
make test                  # CPU test suite: pytest -m "not gpu"
```

`tests/` 下的测试仅使用 CPU（模拟引擎、合成 token），覆盖 token 解码、
样本构建器与 SlowFast 布局、微批调度器、通信协议、
Habitat 客户端循环、EVT-Bench 客户端的响应解析以及可视化模块
（视频编码测试在缺少 `video` 额外依赖时跳过）。

注意事项：

- **帧约定。** `observe()` 和服务端接受任意分辨率的 HWC `uint8` RGB 帧；
  它们会在内部被缩放到检查点的 `video_size` 并归一化到 `[-1, 1]`。
  指向像素以*客户端*的帧尺寸报告。
- **`hf` 注意力。** 默认为 `sdpa`；可通过 `LIGHTNAV_ATTN=flash_attention_2` 覆盖。
- **vLLM 版本。** `inference/vllm_utils.py` 针对 **vLLM 0.19.x** 修补了 vLLM 内部实现；
  运行时守卫会拒绝其他版本（`LIGHTNAV_SKIP_VERSION_GUARD=1`
  可绕过它，且不受支持）。
- **CUTLASS DSL。** `nvidia-cutlass-dsl` 在 `vllm` 额外依赖中被固定版本。vLLM 0.19.1 仅要求
  `>=4.4.0.dev1`，这会让 pip 解析到一个删除了
  `cutlass.cute.core.ThrMma` 的开发构建；截至 0.6.4 的每个 `quack-kernels` 发行版仍会导入该
  符号，因此未固定版本的安装会在引擎启动时失败，并报 `AttributeError: module 'cutlass.cute.core' has
  no attribute 'ThrMma'`。
- **GPU 架构。** 原版 cu12.8 torch wheel 无法为 `sm_103`
  （B300 / B30Z）进行 JIT：`hf` 后端会在 transformers 的 Qwen3-VL 视觉塔中失败，并报
  `nvrtc: error: invalid value for --gpu-architecture`。在这些设备上请使用 cu12.9 wheels（参见
  README 安装说明）；`vllm_local` 两种方式均可工作。

---

## GPU 冒烟测试

CPU 测试套件无法实际运行模型。在带有 GPU 和检查点的机器上，
`scripts/smoke_gpu.sh` 会以最小规模各运行一次所有真实硬件路径，并打印
PASS / FAIL / SKIP 表格：

```bash
MODEL_PATH=checkpoints/LightNav-0 \
    HABITAT_CONFIG=habitat_server/configs/vlnce_r2r.yaml EVT_BENCH_REPO=$HOME/EVT-Bench \
    bash scripts/smoke_gpu.sh
```

`ACTION_TOKENIZER_BUNDLE` 仅对不自带解码器的检查点需要。

步骤：使用 `hf` 和 `vllm_local` 后端的 `lightnav-predict`；带 `--record_dir` 的 `lightnav-serve` +
`lightnav-ws-client`，然后运行 `lightnav-render`；通过
`scripts/eval_habitat.sh` 运行一个 Habitat episode（在没有 `HABITAT_CONFIG` 时跳过）；针对
正在运行的服务端运行一个 EVT-Bench 分片（在没有 `EVT_BENCH_REPO` 时跳过）。日志和输出位于
`output/smoke_<timestamp>/`。
