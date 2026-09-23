<!--
  Auto-translated from docs/HABITAT_SERVER.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](HABITAT_SERVER.md)

# Habitat 环境服务器

`habitat_server/` 是一个小型、自包含的 Python 3.9 包（`lightnav_habitat`），运行在
habitat-sim / habitat-lab conda 环境中，并通过 ZeroMQ 暴露**一个** Habitat 基准环境。
模型侧（`lightnav-eval-habitat`，参见 [EVAL_HABITAT.md](EVAL_HABITAT.md)）运行在
`lightnav` 环境中，连接到服务器，并用 `velocity_control` 命令驱动它。两个进程都不会
导入对方的依赖：服务器从不导入 torch 或 `lightnav`，客户端从不导入 habitat。

支持的基准：

| `--task`    | config                              | split (yaml) | episodes | success radius |
|-------------|-------------------------------------|--------------|----------|----------------|
| `vlnce`     | `configs/vlnce_r2r.yaml`            | val_unseen   | 1,839    | 3.0 m          |
| `vlnce`     | `configs/vlnce_rxr.yaml`            | val_unseen   | 3,669 (en-US + en-IN) | 3.0 m          |
| `objectnav` | `configs/objectnav_hm3d_v1.yaml`    | val          | 2,000    | 0.1 m (to a viewpoint) |
| `objectnav` | `configs/objectnav_hm3d_v2.yaml`    | val          | 1,000    | 0.1 m; needs `--navmesh-cell-height 0.05` |
| `objectnav` | `configs/objectnav_mp3d.yaml`       | val          | 2,195    | 0.1 m (to a viewpoint) |
| `objectnav` | `configs/objectnav_ovon.yaml`       | val_seen / val_seen_synonyms / val_unseen | 3,000 each | 0.25 m (`--success-distance 0.25`) |

全部六个 config 都以 480x270 RGB、120 度水平 FOV 渲染，相机位于地面上方 0.88 m，
`allow_sliding: true`，episode 上限为 500 步。

## 1. 安装

我们唯一验证过的组合是 **python 3.9 + habitat-sim 0.3.1（headless，bullet）+
habitat-lab 0.3.20231024 + numpy < 1.24**。更新的 numpy 会破坏 `numpy-quaternion`，
而 habitat-lab 自身的依赖会拉取 numpy 2.x，因此 habitat-lab 使用 `--no-deps` 安装，
并将 numpy 最后固定版本。

```bash
# environment.yml pulls python/cmake from the `defaults` channel; recent conda versions
# require accepting its terms once: conda tos accept --override-channels \
#   --channel https://repo.anaconda.com/pkgs/main --channel https://repo.anaconda.com/pkgs/r
conda env create -f habitat_server/environment.yml
conda activate habitat
pip install --no-deps "habitat-lab==0.3.20231024"
pip install --force-reinstall "numpy>=1.20,<1.24"
pip install -e habitat_server            # pyzmq, pyyaml, fastdtw, numpy<1.24

python -c "import habitat, habitat_sim; import lightnav_habitat.serve; print('ok')"
```

VLN-CE 的 NDTW 度量需要 `fastdtw`（或 `dtw-python`）。

### 无头渲染（EGL）

habitat-sim 通过 EGL 渲染，无需显示器。在带有 NVIDIA 驱动的机器或容器上，通常需要
满足以下条件：

```bash
export NVIDIA_DRIVER_CAPABILITIES=all
# Point glvnd at the NVIDIA EGL vendor library (create the file if it does not exist):
#   /usr/share/glvnd/egl_vendor.d/10_nvidia.json
#   {"file_format_version": "1.0.0", "ICD": {"library_path": "libEGL_nvidia.so.0"}}
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json
export LD_PRELOAD=/lib/x86_64-linux-gnu/libGLdispatch.so.0   # if habitat-sim fails to create a GL context
```

通常需要的系统包：`libgl1 libglx-mesa0 libegl1 libopengl0 libglvnd0
libglib2.0-0 libsm6 libxext6 libxrender1`。（在 Ubuntu 24.04 上，旧名称
`libgl1-mesa-glx` 和 `libegl1-mesa` 已无法解析——上面的前四个替代了它们。
缺少 `libopengl0` 时，`import habitat_sim` 会失败并报
`libOpenGL.so.0: cannot open shared object file`，这看起来像是 habitat-sim 构建
问题，但实际上是缺少 apt 包。）

### GPU 选择

渲染设备取自 `HABITAT_SIM_GPU_ID`（默认 `0`），并写入
`habitat.simulator.habitat_sim_v0.gpu_device_id`。**不要**将
`CUDA_VISIBLE_DEVICES` 限制为相同的索引：habitat-sim 通过 UUID 匹配 CUDA 和 EGL
设备，需要看到所有 GPU。如果你想要严格的隔离，请同时设置
`CUDA_VISIBLE_DEVICES=<gpu>` 和 `HABITAT_SIM_GPU_ID=0`。

## 2. 数据布局

随附的 yaml 使用相对于工作目录的示例路径。你可以编辑它们，或传入
`--data-path` / `--scenes-dir`（两者都会覆盖 yaml）。

```
data/
  scene_datasets/
    mp3d/<scene>/<scene>.glb                       # VLN-CE (Matterport3D)
    hm3d/val/<id>/<id>.basis.glb                   # ObjectNav (HM3D v0.2 val)
    mp3d/<id>/<id>.glb                             # ObjectNav (MP3D)
  datasets/
    R2R_VLNCE_v1-3_preprocessed/val_unseen/
      val_unseen.json.gz                           # episodes
      val_unseen_gt.json.gz                        # NDTW ground truth (same dir, _gt suffix)
    RxR_VLNCE_v0/val_unseen/
      val_unseen_guide.json.gz
      val_unseen_guide_gt.json.gz
    objectnav/hm3d/v1/val/
      val.json.gz                                  # stub (category maps, no episodes)
      content/<scene>.json.gz                      # one shard per scene
    objectnav/hm3d/v2/val/
      val.json.gz                                  # v2 stub; run with --navmesh-cell-height 0.05
      content/<scene>.json.gz
    objectnav/mp3d/v1/val/
      val.json.gz                                  # 21-category stub
      content/<scene>.json.gz
    ovon/hm3d/val_unseen/
      val_unseen.json.gz                           # stub (may have empty category maps)
      content/<scene>.json.gz
    ovon/hm3d/val_seen*/                           # val_seen / val_seen_synonyms: same layout
```

注意事项：

* Episode 文件将场景引用为 `data/scene_datasets/...`；加载器会去掉该前缀，
  并将剩余部分与 `scenes_dir` 拼接。
* `--data-path ROOT` 会将 `dataset.data_path` 重写为 `ROOT/{split}/{split}.json.gz`。它无法
  表达 RxR 的 `{split}_guide.json.gz`；对于 RxR，请改为编辑 `vlnce_rxr.yaml`。
* `--task vlnce` 总是写入 `dataset.split`（默认 `val_unseen`，即基准 split）；
  `--task objectnav` 保留 yaml 中的 split（HM3D / MP3D v1 为 `val`，OVON 为 `val_unseen`），
  除非给出 `--split`。
* ObjectNav 的 split 需要在 `content/` 旁边有 `<split>/<split>.json.gz` 存根（habitat 先加载
  存根，然后加载每个分片）。HM3D-OVON 的 episode 带有 habitat-lab 0.3.x 拒绝的字段，并且
  附带空的类别映射；`lightnav_habitat.objectnav_extensions` 重新注册了一个宽容的
  `ObjectNav-v1` 加载器来处理这两种情况（并且对 HM3D / MP3D v1 行为完全一致）。
* RxR：`vlnce_rxr.yaml` 没有 `languages` 条目，因此 `VLNCEEnv` 会注入
  `habitat.dataset.languages = [en-US, en-IN]`（仅英语，3,669 个 episode）。在
  `habitat.dataset` 下添加 `languages:` 列表即可更改；客户端还可以用 `--languages`
  进一步过滤。

## 3. 运行服务器

```bash
conda activate habitat
cd /path/to/LightNav-0

# VLN-CE R2R val_unseen
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve --task vlnce \
    --config habitat_server/configs/vlnce_r2r.yaml --port 5555 --ready-file /tmp/hab5555.ready

# VLN-CE RxR val_unseen (English guide annotations)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve --task vlnce \
    --config habitat_server/configs/vlnce_rxr.yaml --port 5555

# HM3D ObjectNav v1 val (success 0.1 m = env default)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve --task objectnav \
    --config habitat_server/configs/objectnav_hm3d_v1.yaml --port 5555

# HM3D ObjectNav v2 val: ALWAYS re-bake the navmesh (v2 episodes were generated at
# cell_height=0.05; the shipped .basis.navmesh is 0.20 and floors distance_to_goal)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve --task objectnav \
    --config habitat_server/configs/objectnav_hm3d_v2.yaml --navmesh-cell-height 0.05 --port 5555

# MP3D ObjectNav v1 val (success 0.1 m = env default)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve --task objectnav \
    --config habitat_server/configs/objectnav_mp3d.yaml --port 5555

# HM3D-OVON val_unseen (success 0.25 m)
HABITAT_SIM_GPU_ID=0 python -m lightnav_habitat.serve --task objectnav \
    --config habitat_server/configs/objectnav_ovon.yaml --split val_unseen \
    --success-distance 0.25 --port 5555
```

`pip install -e habitat_server` 还会安装 `lightnav-habitat-serve` 控制台脚本
（相同的标志）。服务器绑定 `tcp://*:PORT`，构建模拟器，触碰 `--ready-file`
（如果给出），然后阻塞，直到收到 `close` 命令或 SIGINT/SIGTERM。只有在就绪文件
存在后才启动客户端；首次场景加载可能需要数十秒。

### 标志

| flag | default | meaning |
|------|---------|---------|
| `--task {vlnce,objectnav}` | `vlnce` | 环境类 |
| `--config PATH` | required | Habitat Hydra yaml |
| `--port N` | 5555 | ZMQ 端口 |
| `--max-steps N` | 500 | 在 N 步后报告 `truncated`（保持 <= yaml 的 `max_episode_steps`） |
| `--image-height H --image-width W` | yaml | 覆盖 RGB/depth 传感器尺寸（两者同时或都不） |
| `--split-id I --split-num N` | none | 提供 N 个分片中的第 I 个（见下文） |
| `--early-stop-rotation N` | 0 | 在连续超过 N 步 `distance_to_goal` 不变后强制 STOP（0 = 关闭） |
| `--early-stop-steps N` | 0 | 在超过 N 步后强制 STOP（0 = 关闭） |
| `--split NAME` | `val_unseen` (vlnce) / yaml (objectnav) | 写入 `habitat.dataset.split` 的数据集 split |
| `--data-path ROOT` | yaml | `ROOT/{split}/{split}.json.gz` |
| `--scenes-dir DIR` | yaml | 场景数据集目录 |
| `--success-distance M` | 3.0 / 0.1 | 成功半径（VLN-CE / ObjectNav）；OVON 使用 0.25 |
| `--ready-file PATH` | none | 模拟器启动后触碰 |

已发布的数字是在提前停止**禁用**（两个标志均为 0）的情况下产生的：episode 仅在策略
停止（零速度命令）或达到 `--max-steps 500` 时结束。

### 图像尺寸

yaml 中的传感器尺寸（480x270）是已发布数字渲染时使用的尺寸。仅当你刻意想要不同的
分辨率时才传入 `--image-height/--image-width`；策略无论如何都会将帧调整为其自身的
输入尺寸，但不同的渲染宽高比会改变模型看到的内容。

## 4. 并行评估

一个服务器服务一个环境。要使用多个 GPU，请为每个 GPU 启动一个服务器，使用不相交的
分片和各自的端口，并为每个服务器启动一个客户端：

```bash
NUM=4
mkdir -p logs
for i in $(seq 0 $((NUM - 1))); do
  HABITAT_SIM_GPU_ID=$i python -m lightnav_habitat.serve --task vlnce \
      --config habitat_server/configs/vlnce_r2r.yaml \
      --port $((5555 + i)) --split-id $i --split-num $NUM \
      --ready-file /tmp/hab$((5555 + i)).ready > logs/habitat_$i.log 2>&1 &
done
```

分片会按 `scene_id` 对 episode 列表排序，将其切成 `split-num` 个连续块
（最后一块取剩余部分），并提供第 `split-id` 块。按场景排序可将场景重新加载降到最低。
episode 迭代器是确定性的（`shuffle=False`）并且无限循环；客户端通过观察重复的
`(scene_id, episode_id)` 对来检测回绕。将客户端的 `results.jsonl` 文件连接起来即可聚合。

## 5. 协议摘要

请求和响应是通过 ZMQ REQ/REP 对传输的 pickle 字典（协议 4）：

```
{"command": "reset", "data": {"seed": null, "options": null}}
    -> {"status": "success", "obs": {...}, "info": {...}}
{"command": "step", "data": <action>}
    -> {"status": "success", "obs", "reward", "terminated", "truncated", "info"}
{"command": "close"}  -> {"status": "success"}     (server exits)
any failure           -> {"status": "error", "message": "..."}
```

动作要么是 0..3 的 `int`（STOP、MOVE_FORWARD、TURN_LEFT、TURN_RIGHT），要么是

```python
{"action": "velocity_control",
 "action_args": {"linear_velocity": v_lin, "angular_velocity": v_ang}}   # both in [-1, 1]
```

Habitat 会在 `lin_vel_range` / `ang_vel_range` 上按
`min + (v + 1) / 2 * (max - min)` 对 `v` 进行反归一化，并积分 `time_step` 秒。如果
命令的反归一化速度都低于 `min_abs_lin_speed` / `min_abs_ang_speed`，则该命令为 STOP
（它会设置 `is_stop_called`，这是 Success 度量所要求的）。VLN-CE 使用
`lin [0, 2.5] m/s`、`ang [-300, 300] deg/s`、`dt 0.1 s`；ObjectNav 使用
`lin [0, 0.25]`、`ang [-30, 30]`、`dt 1 s`（相同的每步上限 0.25 m / 30 deg）。
客户端必须从 `info` 中读取这些值，而不是硬编码。

`obs`：`rgb` uint8 (H, W, 3)、`depth` float32 (H, W)、`instruction` `{"text": str}`、
`goal_distance` float32 (1,)、`progress` float32 (1,)。

`info`（每一步）：`steps`、`episode_id`（str）、`scene_id`、Habitat 度量
（`distance_to_goal`、`success`、`spl`、`path_length`、`oracle_success`、`steps_taken`，
以及 VLN-CE 的 `ndtw` 和 ObjectNav 的 `soft_spl`）、`instruction`、`habitat_time_step`、
`lin_vel_range`、`ang_vel_range`、`goal_distance`、`goal_position`；VLN-CE 还会添加
`reference_path` 和（RxR）`language`；ObjectNav 还会添加 `object_category`、`goal_positions`
和 `raw_episode_id`。在最后一步，`termination_reason` 是以下之一：`agent_stop`、
`early_stop_no_progress`、`early_stop_step_limit`、`max_steps_truncated`、`unknown`，
并附带一个自由格式的 `termination_details` 字典。

## 6. 故障排除

* `AttributeError: _ARRAY_API not found` / quaternion 导入错误：numpy 被升级到了
  1.23 以上。重新运行 `pip install --force-reinstall "numpy>=1.20,<1.24"`。
* `ImportError: NDTW measure requires either 'fastdtw' or 'dtw-python'`：`pip install fastdtw`。
* reset 时 NDTW 抛出 `KeyError`：该 split 的 `_gt.json.gz` 文件缺失，或与 episode 文件
  不匹配。
* 在 `step` 时 habitat 内部抛出 `AssertionError`：客户端步进超过了 `max_episode_steps`；
  保持 `--max-steps` <= yaml 值（两者默认都是 500）。
* 在一个 GPU 上运行多个服务器时模拟器在启动时挂起：错开启动它们。
