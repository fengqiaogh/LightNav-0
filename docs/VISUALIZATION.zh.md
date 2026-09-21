<!--
  Auto-translated from docs/VISUALIZATION.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](VISUALIZATION.md)

# 可视化：轨迹叠加视频

`lightnav.viz` 将模型预测的内容渲染到它所看到的画面上：将路点块渲染为地平面带状轨迹，将指向 token 渲染为像素标记，以及一个小型遥测 HUD。同一个渲染器同时服务于引擎的两类使用者：

* **真实机器人** — `lightnav-serve --record_dir DIR` 记录每个连接的 episode（客户端的 JPEG 帧 + 每次预测一条 JSON 记录）；`lightnav-render DIR` 随后将它们转换为 mp4。服务器从不进行在线渲染。
* **Habitat 评估** — `lightnav-eval-habitat --save_video` 在运行时为每个 episode 写一个 mp4，`--record_dir` 可选地以相同布局保留原始 episode。

渲染需要 `video` 附加依赖（`pip install -e ".[video]"`：OpenCV、imageio、imageio-ffmpeg）。录制只需要核心安装（numpy + Pillow）。

## 1. 叠加层显示的内容

渲染帧的布局：带有指令的标题栏、`GO` / `STOP` 胶囊标签、步数计数器和步率；地面上用于预测路径的蓝色走廊；用于指向通道的薄荷色和品红色圆盘；左下角的 `VX` / `VY` / `VYAW` 读数。

### 轨迹带状

预测的 `(H, 3)` 块 `[forward_m, lateral_m, yaw_rad]` —— 第 `k` 行是机器人局部地平面位姿，位于前方 `k` 步 —— 通过针孔相机模型（水平 FOV + 相机高度，见 §7）投影到地面平面上，并绘制为走廊。其在帧底边处的宽度为帧宽度的 `--traj-width`（默认 0.25），并随距离缩小；颜色从蔚蓝色（近处）渐变到冰蓝色（远处），并在块末尾淡出。机器人自身的位姿被前置，因此走廊从相机下方开始。

**前向偏移注意事项。** 使用默认的 `--forward-offset auto` 时，走廊会向外偏移 *底边深度* —— 即相机看到图像底边处的地面距离 —— 这样前向相机无法看到的近处路点仍保持可见。路径的形状是精确的；其位置被该深度所偏移（对于 0.5 m 相机、112° 镜头、16:9 帧，约为 0.6 m）。传入 `--forward-offset 0` 可获得精确放置（此时前几个路点会落到帧下方）。

带状轨迹至少需要两行路点；解码失败后没有块也没有带状轨迹，但 HUD 仍会显示原始模型文本的后果（如果回退是停止则显示 `STOP` 胶囊标签、指令、步数）。

### 指向圆盘

发出 grounding token 的检查点会在解码像素处获得带光晕的圆盘：

| 颜色 | 通道 | 含义 |
|---|---|---|
| 薄荷色 | `apos` | 智能体应前往的位置（目标 / 下一位置） |
| 品红色（最后绘制） | `opos` | 目标物体所在的位置 |

只绘制 *像素* 通道 —— 即在 `pointing` 载荷（[PROTOCOL.md](PROTOCOL.md)）中状态为 `point` 的通道。指令状态（`rot_left`、`rot_right`、`stop`）和 `not_visible` 没有像素，因此不绘制。HUD 的 `GO` / `STOP` 胶囊标签显示的是 **解码动作**（全零块 / `<traj_0>`），这与 `apos` 停止指令是不同的东西。像素会从载荷的 `frame_size` 重新缩放到渲染帧，因此 `--height` 放大后它们仍保持在原位。

### HUD

| 字段 | 来源 |
|---|---|
| instruction | 记录的 `instruction`，已规范化：折叠空白、首字母大写、当没有终止标点时添加句号 |
| `GO` / `STOP` | 记录的 `stop`（解码动作） |
| `STEP nnnn` | 记录的 `step`（服务器：历史缓冲区中的帧数；评估：策略步数） |
| 速率 `x.xx Hz` | 记录的 `1000 / step_dt_ms`（上一区间的完成到完成时间）；未知时为 `--.-- Hz`（第一步，或评估视频，它们没有墙钟计时） |
| `VX` / `VY` / `VYAW` | **第一个路点** 除以 `dt`：`forward_m / dt`（m/s）、`lateral_m / dt`（m/s）、`yaw_rad / dt`（rad/s）；条形图有固定的满量程（3.0 m/s、0.5 m/s、3.5 rad/s），因此可跨帧比较 |

`dt` 是一种显示约定，而非模型的属性：路点行是每步位移，本身不携带时间基准（轨迹词表将一步限制在约 0.25 m / 30°）。默认 `dt = 0.1 s`（`lightnav-render` 中的 `--dt`，服务器和评估客户端中的 `--waypoint_dt_s`，存储在 manifest 中）使读数在录制之间可比；它不必与你的控制周期匹配。

## 2. 录制布局与记录模式

服务器和评估客户端每次运行都会写入：

```
<record_dir>/
  run_<YYYYmmdd_HHMMSS>/
    <connection label>/                # server: clientId if it is a safe name, else conn001, ...
                                       # eval:   eval
      episode_000/
        manifest.json                  # run parameters (below)
        image_000002.jpg               # one frame per recorded step, named by `step`
        image_000003.jpg
        actions.jsonl                  # appended + flushed per step WHILE the episode is open
        actions.json                   # the same records as one JSON array, written when it ends
        traj_pointing.mp4              # added by lightnav-render
      episode_001/
        ...
```

`actions.jsonl` 仅在 episode 打开期间存在（它能在崩溃后保留，且 `lightnav-render` 接受它）；`end_episode` 原子地写入 `actions.json` 并删除 jsonl。在服务器上，帧是客户端 JPEG 字节的原样（从不重新编码）；在评估客户端中，帧是 JPEG 编码（质量 95）的 `obs["rgb"]`。

`manifest.json`：

```json
{"schema": 1, "created_at": "2026-…", "conn": "robot-01", "episode": 0,
 "task": "tracking", "model_path": "/path/to/hf_ckpt",
 "video_fps": 10, "video_timeline": "realtime", "waypoint_dt_s": 0.1,
 "overlay_hfov_deg": 90.0, "overlay_cam_height": 0.5, "overlay_forward_offset": null,
 "frame_size": [480, 270], "instruction": "follow the man in the black shirt", "extra": {}}
```

一条记录（`actions.jsonl` 的一行，`actions.json` 的一个元素）：

| 键 | 含义 |
|---|---|
| `step` | 服务器：进行预测时历史缓冲区中的帧数（线上的 `actions.step`）；评估：策略步数 |
| `seq` | 服务器：客户端的 `seq`；评估：等于 `step` |
| `received_at` | ISO 时间戳（毫秒） |
| `step_dt_ms` | 上一区间的完成到完成时长，第一步为 `0.0` |
| `step_fps` | `1000 / step_dt_ms`，或 `null` |
| `instruction` | 该请求的指令 |
| `waypoints` | `(H, 3)` 块，形式为 `[forward_m, lateral_m, yaw_rad]` 的列表，解码失败后为 `null` |
| `stop` | 解码的停止（全零块） |
| `visible` | 跟踪可见性标志，或 `null` |
| `raw_text` | 模型的 token 文本 |
| `latency_ms` | 服务器：该请求的端到端预测时间；评估：`policy.act` 墙钟时间 |
| `pointing` | 客户端收到的（服务器）/ 本应收到的（评估）`pointing` 载荷，或 `null` |
| `frame_size` | 所记录帧的 `[width, height]` |

评估客户端为每条记录添加 `episode_id`、`habitat_episode_id` 和 `scene_id`。

## 3. 时间基准：`realtime` 与 `per_step`

录制中每次预测携带一帧，`lightnav-render` 决定每一帧在屏幕上停留多久：

* **`realtime`**（服务器默认）—— 一步重复 `round(step_dt_ms * fps / 1000)` 次，限制在 `[1, 20]` 帧，因此视频以机器人运行的速度播放，卡顿会表现为卡顿（240 秒的网络故障在 10 fps 下仍最多只占 2 秒视频）。
* **`per_step`**（评估默认）—— 每步恰好一帧；视频长度是步数除以 `fps`。模拟器步数没有有意义的墙钟间隔。

manifest 的 `video_timeline` 和 `video_fps` 是默认值；`--timeline` 和 `--fps` 在每次渲染时覆盖它们。

## 4. `lightnav-render`

```bash
lightnav-render output/episodes                 # every episode under the tree
lightnav-render output/episodes/run_*/robot-01/episode_003 --fps 15 --height 1080 --overwrite
lightnav-render output/episodes --timeline per_step --forward-offset 0 --no-hud
```

| 标志 | 默认值 | 含义 |
|---|---|---|
| `paths` | 必填 | episode 目录，或包含它们的目录树（`actions.json` 或 `actions.jsonl`） |
| `--out-name` | `traj_pointing.mp4` | 每个 episode 目录内的输出文件名 |
| `--fps` | manifest `video_fps`（10） | 输出帧率 |
| `--timeline {realtime,per_step}` | manifest `video_timeline` | 见 §3 |
| `--dt` | manifest `waypoint_dt_s`（0.1） | HUD 速度读数中每行路点的秒数 |
| `--traj-width` | `0.25` | 底边处带状轨迹宽度，占帧宽度的比例 |
| `--min-steps` | `0` | 跳过记录数少于该值的 episode |
| `--height` | `0`（保持） | 绘制前将每帧放大到此高度（例如对 270 px 录制使用 `1080`） |
| `--forward-offset` | `auto` | `auto` = 底边深度（近处路点可见）；以米为单位的数字会加到 manifest 的 `overlay_forward_offset` 上；`0` = 精确放置 |
| `--no-pointing` / `--no-hud` | 关闭 | 去掉圆盘 / 遥测叠加层 |
| `--overwrite` | 关闭 | 替换现有输出（否则该 episode 被跳过并计为已完成） |

输出为 H.264 / yuv420p（奇数帧尺寸会复制一行/一列边缘），先写入临时名称，完成后重命名。每个 episode 打印一行摘要；图像缺失的记录会被跳过并列出。当且仅当每个 episode 都渲染成功时退出码为 0。Python：`lightnav.viz.render_episode_dir(episode_dir, ...)` 使用相同的关键字参数，`lightnav.viz.render_frame(rgb, waypoints=..., pointing=..., ...)` 用于单帧。

## 5. 服务器：`lightnav-serve --record_dir`

```bash
RECORD_DIR=output/episodes CAM_HFOV_DEG=112 CAM_HEIGHT=0.45 lightnav-serve --task tracking ...
# or
lightnav-serve ... --record_dir output/episodes --cam_hfov_deg 112 --cam_height 0.45
```

| 标志 | 环境变量 | 默认值 | 含义 |
|---|---|---|---|
| `--record_dir` | `RECORD_DIR` | `""`（关闭） | 录制树的根目录；每次服务器启动一个 `run_<timestamp>/` |
| `--record_fps` | `RECORD_FPS` | `10` | 写入 manifest 的 `video_fps` |
| `--record_timeline` | `RECORD_TIMELINE` | `realtime` | 写入 manifest 的默认时间基准 |
| `--record_images` / `--no_record_images` | `RECORD_IMAGES`（`1`/`0`） | 开启 | 存储帧；没有它们时记录仍会写入，但无法渲染视频 |
| `--cam_hfov_deg` | `CAM_HFOV_DEG` | `90.0` | **客户端**相机的水平 FOV（仅用于带状轨迹投影） |
| `--cam_height` | `CAM_HEIGHT` | `0.5` | 客户端相机离地高度，米 |
| `--traj_forward_offset` | `TRAJ_FORWARD_OFFSET` | 未设置（自动） | 带状轨迹的固定前向位移，米 |
| `--waypoint_dt_s` | `WAYPOINT_DT_S` | `0.1` | HUD 速度读数约定 |

行为：每个 WebSocket 连接一个连接记录器，当 `login` 时发送的 `clientId` 是纯名称（`[A-Za-z0-9._-]`）时以其为标签，否则为 `conn001`、`conn002`、……。`reset` 开始一个新 episode；连接的第一次预测会在没有打开的 episode 时开始一个。每个 **被预测的** `next`（而非仅缓冲区的确认）都会添加一条记录，包含请求的 JPEG 字节和上线传输的 `pointing` 载荷。连接的 episode 在套接字关闭时结束；服务器的关闭会关闭一切。

录制是诊断性的：它在回复发送后运行，从不改变响应或其顺序，任何每步记录器故障（磁盘满……）都会被记录并丢弃；不可用的 `--record_dir` 会在启动时、模型加载前被拒绝。每次预测花费一次 JPEG 写入和一行 JSON；渲染被有意留给 `lightnav-render`，这样服务循环永远不会为视频编码付出代价。

`scripts/start_servers.sh` 和 `docker/entrypoint.sh` 读取相同的环境变量。`start_servers.sh` 为每个服务器分配 `RECORD_DIR/port<PORT>/`，这样在同一秒启动的多个服务器永远不会共享运行目录；在 Docker 中，将 `RECORD_DIR` 挂载为卷，使录制在容器结束后仍然保留。

## 6. Habitat 评估：`lightnav-eval-habitat --save_video`

```bash
lightnav-eval-habitat --model_path /path/to/hf_ckpt --server tcp://localhost:5555 \
    --episodes 20 --output_dir output/r2r_viz --save_video
```

| 标志 | 默认值 | 含义 |
|---|---|---|
| `--save_video` | 关闭 | 为每个 episode 写入 `<output_dir>/videos/<episode_id>.mp4`，每个策略步骤一帧（`per_step` 时基）加上终止观测 |
| `--video_fps` | `10` | 这些视频的播放帧率 |
| `--hfov_deg` | `120.0` | 智能体相机的水平 FOV（随附的 `habitat_server/configs/*.yaml`） |
| `--cam_height` | `0.88` | 相机高度，单位为米（同上 yaml） |
| `--waypoint_dt_s` | `0.1` | HUD 速度读数约定 |
| `--record_dir` | `""`（关闭） | 同时将原始 episode（JPEG 帧 + 记录，§2）记录到 `<record_dir>/run_*/eval/episode_NNN/` 下，供 `lightnav-render` 使用 |

每一帧都根据策略所依据的观测渲染，并带有该步骤的预测，*在*环境推进*之前*；最后一步返回的观测会附加最后的预测一并追加，以便终端视图可见。写入器在第一帧时打开，episode 结束时文件被重命名到位，因此中断的运行不会留下写了一半的 `episode_*.mp4`。当写入了视频时，每个 episode 的结果记录（`results.jsonl`）会新增 `"video": "videos/episode_000.mp4"`。

`--save_video` 需要 `video` 附加项；缺失的 `cv2` / `imageio` / `imageio_ffmpeg` 会在模型加载前报告。在 episode 中途编码失败的视频会被丢弃并给出警告；评估本身会继续。

## 7. 相机参数

带状投影假设一个朝前的针孔相机，与地面齐平，位于 `cam_height` 米处，水平 FOV 为 `hfov_deg`（垂直 FOV 由帧宽高比推导得出）。只有叠加层使用这些数值——模型从不会看到它们。

| 位置 | 水平 FOV | 高度 | 来源 |
|---|---|---|---|
| 服务器（`--cam_hfov_deg`、`--cam_height`） | 你的机器人相机 | 你的机器人相机 | 默认值 90° / 0.5 m 是占位符——请为你的平台设置它们 |
| 评估（`--hfov_deg`、`--cam_height`） | 120° | 0.88 m | `habitat_server/configs/*.yaml` |

错误的 FOV 会横向拉伸或挤压走廊；错误的高度会使其上移或下移。两者都不影响指向圆盘（那些是像素）或 HUD。

## 8. 字体

HUD 在安装了 TrueType 字体时使用它——来自 `/usr/share/fonts/truetype/` 的 DejaVu Sans（Condensed / Mono Bold）或 Liberation Sans Narrow / Mono——否则回退到 OpenCV 内置的 Hershey 矢量字体，因此它能在裸容器中渲染。`apt-get install fonts-dejavu-core`（Debian/Ubuntu）可恢复预期的外观。
