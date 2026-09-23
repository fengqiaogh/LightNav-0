<!--
  Auto-translated from evt_bench/README.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](README.md)

# EVT-Bench 集成文件

需要复制到你自己的 [EVT-Bench / TrackVLA](https://github.com/wsakobe/TrackVLA)
检出目录中的文件，以便其 `run.py` 能通过 WebSocket 驱动正在运行的 `lightnav-serve` 服务器。

| 文件 | 用途 |
|------|---------|
| `trackvla_client_agent.py` | 最小化的 WebSocket 客户端 agent（`evaluate_agent`、`TrackVLAClientAgent`）。复制到 `run.py` 旁边。Python 3.9，需要 `websocket-client`。 |
| `run_py.patch` | 统一 diff，向上游 `run.py` 添加 `--model-name trackvla` 分支（`git apply` / `patch -p1`）。 |
| `patch_task_config.py` | 写入一份 `track_infer_*.yaml` 的修补副本，使用不同的下颌相机 hfov / height。由 `scripts/eval_evt_bench.sh` 使用；不会复制到 EVT-Bench 中。 |

端到端流程（conda 环境、数据集布局、服务器启动、分片运行、
`analyze_results.py`）见 [docs/EVAL_EVT_BENCH.md](../docs/EVAL_EVT_BENCH.md)。

EVT-Bench 本身（habitat-lab fork、任务配置、数据集、`analyze_results.py`）
采用 CC BY-NC-SA 4.0 许可，不在此处再分发；`trackvla_client_agent.py` 中的
评估循环改编自其驱动程序，参见 `THIRD_PARTY_NOTICES.md`。
