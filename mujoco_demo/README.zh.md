<!--
  Auto-translated from mujoco_demo/README.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](README.md)

# mujoco_demo

一个小型视觉-语言-导航仿真（Python 包 `vln_mujoco`）：
它运行在固定的 MolmoSpaces ProcTHOR 10K 验证集 `val_2` 多房间场景中，使用
天花板 MJCF 变体、MuJoCo RGB 相机渲染，以及内置的 TurtleBot 或外部的
MicroDuck 模型和行走策略。单个网页提供 VLN 指令、实时视图、WASD 驾驶、
紧急停止、重置和状态读取。

## 亮点

- 单一场景：仅打包 `val_2_ceiling` 实际引用的 MolmoSpaces 资源——无需下载
  完整数据集；
- 两种机器人模式：项目内定义的差速驱动 TurtleBot，或由 ONNX 行走策略驱动的
  可选动态仿真 MicroDuck；
- 单一进程：Python 同时运行 MuJoCo、网页和 VLN WebSocket 客户端；
- TurtleBot 指令以运动学方式积分；MicroDuck 以 50 Hz 运行重力、接触、
  14 个位置执行器和策略推理；
- 两种视图：网页在机器人的第一人称 RGB 和后方抬高的第三人称跟随相机之间
  实时切换；
- 变更时状态同步：仅当机器人、VLN、控制权或配置发生变化时才推送网页状态；
- VLN 语义反馈：第一人称视图显示 APOS/OPOS 标记，`stop=true` 结束任务并
  自动释放控制权；
- MPC 控制：与 `robot_deploy` 的 `vln_mpc` 相同的 CasADi/IPOPT 独轮车 MPC、
  参数和捕获时位姿对齐；
- 无需 ROS 2 或 Node.js；默认 TurtleBot 模式不需要运动策略；
- 网页交互和 VLN 服务器协议与 `robot_deploy` 的 `vln_web` 和 `vln_client`
  兼容。

## 运行

需要 [uv](https://docs.astral.sh/uv/) 和 Python 3.11+：

```bash
./run.sh
```

打开 <http://127.0.0.1:8088>。即使未配置 VLN 服务器，你仍然可以点击页面上的
**Take control** 并用 WASD 驾驶。也可以在启动时设置默认服务器地址：

```bash
./run.sh --vln-server ws://127.0.0.1:8050
./run.sh --host 0.0.0.0 --port 8088
```

### MicroDuck（可选）

MicroDuck 支持有意将机器人 MJCF、网格和行走策略保留在本仓库之外。它们由
Pollen Robotics 发布：MJCF 和代码采用 Apache-2.0，3D 网格文件采用
CC BY-NC-SA，策略采用 Apache-2.0。获取一次，然后将演示指向这些文件，并注意
适用于网格的 NonCommercial 条款。

#### 1. 机器人模型（MJCF + 网格）

```bash
git clone https://github.com/pollen-robotics/microduck_rl.git
# MJCF: microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml
```

网格位于 MJCF 旁边的 `assets/` 下；保持目录结构完整。其他变体
（`robot_walk.xml`、`robot_groundcontact.xml`）共享相同的 `head_camera` 和
执行器布局，但此处尚未测试。

#### 2. 行走策略（ONNX）

官方策略集随 Hugging Face Hub 上的 `pollen-robotics/microduck-policies` 提供
（镜像于 [pollen-robotics/microduck](https://github.com/pollen-robotics/microduck)
的 `policies/` 目录中）：

```bash
mkdir -p microduck_policies && cd microduck_policies
curl -L -o alpha_walking.onnx \
  https://huggingface.co/pollen-robotics/microduck-policies/resolve/main/alpha_walking.onnx
```

只有由 `microduck_rl` 的 `scripts/export.py` 生成的 ONNX 文件可用：导出器将
观测归一化器和以下元数据烘焙到计算图中。手动转换的检查点无法通过启动检查。

#### 3. 可选依赖

```bash
uv sync --extra microduck        # installs onnxruntime; TurtleBot installs stay untouched
```

#### 4. 运行

```bash
uv run --extra microduck vln-mujoco \
  --robot microduck \
  --robot-model /path/to/microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml \
  --walking-policy /path/to/microduck_policies/alpha_walking.onnx
```

像 TurtleBot 一样添加 `--host 0.0.0.0` / `--vln-server ws://<gpu-host>:8050`。
在无头 Linux 机器上，在命令前加上 `MUJOCO_GL=egl`；在 macOS 上保持
`MUJOCO_GL` 未设置，默认的 CGL 后端无需显示器即可离屏渲染。启动比 TurtleBot
多花几秒钟，因为 ProcTHOR 场景和机器人通过 `MjSpec` 组合，并且首先验证 ONNX
会话。

#### 约定

MJCF 必须提供 `trunk_base`、`trunk_base_freejoint`、`head_camera`、
`imu_ang_vel` 三轴传感器和 14 个关节执行器。ONNX 策略必须接受一个
`[1, 61]` float32 观测，返回一个 `[1, 14]` float32 动作，并提供
`joint_names`、`default_joint_pos`、`action_scale`、`observation_names` 和
`command_names` 元数据。执行器顺序必须与 `joint_names` 匹配；不兼容的文件会在
启动时失败，而不是以错误的关节映射运行。

头部相机用于 LightNav 输入，而 MuJoCo 躯干位姿和速度提供 MPC 反馈。上游的
`head_camera` 不携带视场角或光学朝向，因此演示将其重新朝向前方，并设置与
TurtleBot 相机相同的 `fovy`（16:9 下水平 112°，即真实机器人使用的镜头）。
指令被裁剪到策略范围（`±0.30 m/s`、`±1.50 rad/s`）；小的非零线速度指令进入
稳定行走范围，而停止死区内的指令保持为零。该策略以 50 Hz 训练，物理步长为
`0.005 s`，共享运行时与此匹配。

按下空格键或点击页面上的 `STOP` 会立即将速度归零。手动指令在 350 ms 内未
刷新时也会自动归零。

## 使用 LightNav-0 驾驶

在 GPU 主机上启动 `lightnav-serve`（参见
[docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md)）：

```bash
PORT=8050 CUDA_VISIBLE_DEVICES=0 lightnav-serve \
    --task vln --model_path checkpoints/LightNav-0 --backend vllm_local
```

然后将 `ws://<gpu-host>:8050` 粘贴到控制台的 **VLN Server WebSocket** 字段中，
输入指令，然后按 **Start VLN**。所选的仿真机器人将其第一人称帧流式传输到
服务器，并使用 MPC 跟踪返回的航点——与真实机器人在
[`robot_deploy/`](../robot_deploy/README.md) 中使用的客户端协议和控制器相同。

## 布局

```text
mujoco_demo/
├── vln_mujoco/
│   ├── assets/        # a single MolmoSpaces scene, nothing more
│   ├── web/           # static single page, no build step
│   ├── robots/        # backend protocol + TurtleBot and MicroDuck adapters
│   ├── model.py       # scene loading and MuJoCo compilation
│   ├── simulation.py  # shared runtime, cameras, watchdog, frame capture
│   ├── mpc.py         # CasADi/IPOPT kinematic MPC
│   ├── vln_client.py  # VLN WebSocket client
│   └── server.py      # HTTP/WebSocket and control ownership
├── scripts/
├── tests/
└── run.sh
```

仿真运行时独立于内置的 TurtleBot 实体。机器人实现满足
`vln_mujoco/robots/base.py` 中的 `RobotBackend` 协议：它们提供 MuJoCo 模型和
数据，消费共享的平面速度指令，报告位姿和速度，并选择两个渲染相机。运行时
继续拥有线程、指令超时、渲染、帧时间戳和面向服务器的快照。因此，新的实体
无需修改 VLN 客户端、MPC、网页服务器或渲染循环。

VLN 返回的机体坐标系航点首先使用图像捕获时的机器人位姿转换到世界坐标系，
然后由 MPC 在当前机器人局部坐标系中跟踪。控制速率、时域、模型、代价、约束、
IPOPT 设置和参数均与 `robot_deploy` 的 `vln_mpc` 匹配：

| 参数 | 值 |
| --- | --- |
| 控制速率 / `horizon` | `10 Hz` / `5` |
| MPC / 航点 `dt` | `0.1 s` / `0.1 s` |
| `track_v_max` / `objnav_v_max` | `1.5 m/s` / `0.8 m/s` |
| `w_max` | `3.0 rad/s` |
| `a_max_v` / `a_max_w` | `2.0 m/s²` / `5.0 rad/s²` |
| `q_x` / `q_y` / `q_yaw` | `10.0` / `10.0` / `1.0` |
| `r_v` / `r_w` | `0.1` / `0.1` |
| IPOPT | `max_iter=100`、`acceptable_tol=1e-8`、`acceptable_obj_change_tol=1e-6` |

## 为什么单个 MolmoSpaces 场景就足够

官方 MolmoSpaces 资源管理器按场景归档安装，但 ProcTHOR 场景 XML 也会引用
共享的 THOR 网格/纹理。在默认的 MolmoSpaces 初始化流程下，共享的 THOR 对象
源可能会被完整解包，因此“选择一个场景”并不一定意味着只有该场景的文件最终
出现在磁盘上。

本项目在发布前运行一次修剪脚本：它解析固定场景 XML 中的每个 `file=` 引用，
仅复制该闭包内的网格/纹理，保留原始目录结构。当前资源闭包为 62.4 MiB，
因此克隆后无需 MolmoSpaces 仓库或其下载器。

开发者可以从现有的 MolmoSpaces 检出重新生成资源：

```bash
python3 scripts/vendor_molmospaces_scene.py \
  ~/Desktop/molmospaces/assets/scenes/procthor-10k-val/val_2_ceiling.xml
```

上游修订版本、文件列表和校验和记录在
`vln_mujoco/assets/manifest.json` 中。

## 归属与许可

由 [Light Origins](https://www.lightorigins.com/en) 开发和维护。
版权所有 2026 Light Origins。

项目源代码采用 [Apache License 2.0](../LICENSE) 许可。内置的 MolmoSpaces
ProcTHOR `val_2` 场景和 THOR 资源采用 CC BY 4.0 许可；依赖项和资源的归属、
修改说明及许可链接见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

TurtleBot 是 Open Robotics（Open Source Robotics Foundation）的商标。
本演示中的机器人是为本项目创建的原创简化差速驱动几何体，灵感来自
TurtleBot 外形；它不使用任何官方网格或设计文件，本项目与 Open Robotics 或
ROBOTIS 无关联，也未获其认可。

## 已知限制

- TurtleBot 是为本项目绘制的轻量几何体，而非官方高保真 TurtleBot3 网格；
- MicroDuck 模式需要外部 MJCF 资源和兼容的 ONNX 策略；
- 生成位姿固定为 `(x=6.5, y=13.8, yaw=0)`，环境对象被冻结；
- 目前仅支持 RGB，相机分辨率为 `480 × 270`；
- MPC 仅跟踪 VLN 提供的局部航点——没有导航地图、全局规划、碰撞响应或
  ROS 接口。
