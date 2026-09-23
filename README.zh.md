<!--
  Auto-translated from README.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](README.md)

<h1 align="center">LightNav-0</h1>

<h3 align="center">激发 VLM 空间智能，实现通用具身导航</h3>

<p align="center"><b>Light Origins 团队</b></p>

<div id="top" align="center">

[![arXiv](https://img.shields.io/badge/arXiv-2608.30935-b31b1b.svg)](https://arxiv.org/abs/2608.30935)
[![Project Page](https://img.shields.io/badge/Project%20Page-9c403d?style=flat)](https://www.lightorigins.com/en/blog/lightnav-0)
[![Model](https://img.shields.io/badge/🤗%20Model-LightNav--0-yellow.svg)](https://huggingface.co/LightOriginsHQ/LightNav-0)
[![Discord](https://img.shields.io/badge/Discord-5865F2?style=flat&logo=discord&logoColor=white)](https://discord.gg/zwZuD9JG)
[![WeChat](https://img.shields.io/badge/WeChat-07C160?style=flat&logo=wechat&logoColor=white)](#community)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB.svg)](pyproject.toml)

</div>

<div align="center">

![LightNav-0 driving four different robots through an unseen park from language instructions, with the predicted trajectory overlaid on each robot's own camera](docs/assets/hero_cross_embodiment.gif)

*人形、四足、轮式与空中机器人在一个未见过的公园中，各自跟随以语言指定的目标。
无遥操作，完全自主。*

</div>

## 🏡 简介

<div align="center">
  <img src="docs/assets/teaser.png" alt="LightNav-0 overview: a simulation-based data engine, three-stage model training, zero-shot deployment onto four robot embodiments, and success-rate comparisons on ten public benchmarks" width="95%"/>
</div>

<br>

**LightNav-0** 是一个紧凑的通用具身导航模型，它激发预训练视觉语言模型（Qwen3-VL）的空间
智能，并使其与导航对齐，且不含任务专用的预测头。多种任务共享同一个 token 接口：双通道
指向表达与任务、场景和本体无关的空间意图，而残差向量量化动作分词器将该意图映射为精确的、
本体特定的轨迹——因此指令跟随、开放词汇物体导航和视觉跟踪都存在于同一个模型中，并可零样本
跨机器人本体和场景迁移。

## 🧠 方法

<div align="center">
  <img src="docs/assets/pipeline.png" alt="LightNav-0 architecture: a pretrained VLM backbone consumes a compressed egocentric RGB history and a language instruction, then emits dual-channel pointing tokens followed by three RVQ action tokens that decode to ten SE(2) waypoints" width="95%"/>
</div>

<br>

LightNav-0 基于 **Qwen3-VL-4B-Instruct** 实例化，未添加任何导航专用模块——没有路点预测器，
没有任务专用的动作头，也没有针对各本体的专家模型。仅扩展了词表，加入带索引的指向 token 和
RVQ 动作 token，因此空间推理轨迹和动作编码都通过主干网络原有的自回归 LM 头解码。

在每个决策步，模型接收带时间戳的自我中心 RGB 历史与自然语言指令，二者交错于单一因果序列中，
并输出：

1. **双通道指向**——一个*可供性*点（可行的局部方向或自由空间路点）和一个*物体*点（任务目标），
   各为一个图像网格 token。这是一条显式的空间推理轨迹，在生成任何动作之前就将规划落地到像素上。

2. **三个 RVQ 动作 token**，解码为 10 个未来 SE(2) 路点——一个通用几何接口，交给各本体自身的
   底层控制器。

任务语义完全来自指令；不存在任务识别 token，同一个主干网络、token 接口和目标函数服务于每一项
导航任务。

### 时间感知的历史压缩

导航既需要近期的几何细节，也需要长时程上下文，但以原生分辨率编码每一帧会使视觉 token 数量
无界增长。LightNav-0 按时间新近度压缩历史，遵循艾宾浩斯遗忘曲线的形态：采样率随帧龄指数衰减，
同时空间池化步长指数增长，因此久远的观测贡献更少、更粗的 token，而当前观测保留最精细的细节。
时间戳 token 在池化后保持顺序。压缩器运行在视觉 Transformer 之后，可配置的像素预算为 256K、
576K 和 1M，在不将整段历史坍缩为单一固定分辨率摘要的前提下限制上下文长度。

### RVQ 动作分词器

<div align="center">
  <img src="docs/assets/rvq.png" alt="Hierarchical residual vector-quantized action tokenizer: a coarse codebook plus two residual codebooks quantize a ten-step SE(2) trajectory, and the composed codewords decode back into a trajectory" width="95%"/>
</div>

<br>

一个 10 步 SE(2) 轨迹由 256 项粗码本和两个 256 项残差码本量化，分辨率分别约为 0.9 m、7 cm
和 4 cm。任何非空 token 前缀都已能解码为可执行的粗轨迹，而每增加一级残差都会细化几何精度——
因此同样的三个 token 既表达整体运动，也表达路径的厘米级形状。

## 🏆 基准测试

一个共享检查点，无逐基准微调。下文中每个 LightNav-0 数值都来自单一前向 RGB 流——不使用深度、
里程计或全景装置。基线为最强的单目条目；完整表格（包括 NE / nDTW / CR 以及全景对比）见论文。

### 指令跟随（VLN-CE）

R2R 的 val-unseen 划分以及更长时程的 RxR。

| 模型 | R2R SR (%) | R2R SPL (%) | RxR SR (%) | RxR SPL (%) |
| :--- | :---: | :---: | :---: | :---: |
| NaVILA | 54.0 | 49.0 | 49.3 | 44.0 |
| StreamVLN | 56.9 | 51.9 | 52.9 | 46.0 |
| DualVLN | 64.3 | 58.5 | 61.4 | 51.8 |
| CorrectNav | 65.1 | 62.3 | 69.3 | 63.3 |
| Qwen-RobotNav-8B | 65.7 | 59.6 | 73.4 | 63.5 |
| **LightNav-0** | **68.5** | **62.8** | **73.6** | **64.5** |

### 物体目标与开放词汇导航

六个 ObjectNav 设置上的成功率。HM3D-OVON 测试训练中从未见过的类别名称，包括以同义词形式
和完全未见类别形式出现的情况。

| 模型 | MP3D | HM3D v1 | HM3D v2 | OVON Seen | OVON Syn. | OVON Unseen |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| VLFM | 36.4 | 52.5 | 63.6 | 35.2 | 32.4 | 35.2 |
| SG-Nav | 40.2 | 54.0 | 49.6 | — | — | — |
| CogNav | 46.6 | 72.5 | — | — | — | — |
| Uni-NaVid | — | 73.7 | — | 41.3 | 43.9 | 39.5 |
| MTU3D | — | — | — | 55.0 | 45.0 | 40.8 |
| **LightNav-0** | **53.3** | **74.5** | **77.2** | **55.3** | **54.6** | **47.0** |

### 具身视觉跟踪（EVT-Bench）

STT 为单目标跟踪；DT 加入与目标相似的干扰物。

| 模型 | STT SR (%) | STT TR (%) | DT SR (%) | DT TR (%) |
| :--- | :---: | :---: | :---: | :---: |
| Uni-NaVid | 53.3 | 67.2 | 31.9 | 50.1 |
| TrackVLA | 85.1 | 78.6 | 57.6 | 63.2 |
| VLingNav | 88.4 | 81.2 | 67.6 | 73.5 |
| ReferTrack | 89.4 | **92.5** | 73.3 | **81.8** |
| **LightNav-0** | **91.7** | 87.7 | **82.6** | 80.1 |

在 DT 上，LightNav-0 也超过了论文中所有全景和多相机系统，包括达到 74.2 SR 的 CoMaTrack。

### INSIGHT-Bench

我们面向部署的基准：涵盖 210 个室内外场景的 1,097 个回合，每个策略都通过同一个共享的 120°
前向 RGB 接口和 300 步动作预算驱动。

| 模型 | SR (%) | SPL (%) | NE (m) |
| :--- | :---: | :---: | :---: |
| StreamVLN | 11.6 | 10.8 | 6.56 |
| Uni-NaVid | 24.3 | 22.1 | 4.91 |
| NaVid | 26.9 | 23.0 | 4.25 |
| JanusVLN | 27.4 | 24.0 | 4.89 |
| **LightNav-0** | **43.7** | **41.5** | **3.88** |

回合数据与评测代码单独发布于
[lightorigins/Light-INSIGHT-Bench](https://github.com/lightorigins/Light-INSIGHT-Bench)。

### 扩展性分析

R2R 和 RxR val-unseen 如何随主干规模、训练数据量和训练环境覆盖度变化。

<div align="center">
  <img src="docs/assets/scaling.png" alt="Three line charts on continuous VLN: success rate and SPL against backbone size, fraction of training data, and fraction of training environments, for R2R and RxR" width="95%"/>
</div>

<br>

三种不同的行为。**模型扩展**会饱和：2B → 4B 使 R2R SR/SPL 提升 8.6/7.4 个点，但 8B 表现
参差，且大多略差。**数据扩展**单调但收益递减——最后一次翻倍，即从语料库的一半到全部，仅换来
0.8 的 R2R SR。**环境扩展**是唯一持续有回报的维度：从 1/8 的训练环境增加到全部，在 R2R 上
增加 16.7/16.2 个点，在 RxR 上增加 21.1/19.1 个点，超过数据扩展在相同范围内的收益。场景多样性，
而非参数量或单纯的时长，才是可靠的杠杆。

<details>
<summary><b>具身推理（LightNav-ER）</b></summary>

<br>

用于初始化 LightNav-0 的 Stage-I 具身推理检查点，在任何导航对齐之前评测。一个 4B 模型在
全集平均分上超过了一个 8B 的空间专用模型。

| 模型 | 参数量 | Point-Bench | RefSpatial | RoboSpatial POI | RoboSpatial VQA | Where2Place | CV-Bench | ERQA | EmbSpatial | 平均 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Qwen3-VL | 4B | 58.2 | 45.5 | **64.8** | 69.7 | 64.0 | 85.6 | 39.5 | 77.6 | 63.1 |
| Qwen3.5-4B | 4B | 60.4 | 54.6 | 47.9 | 59.7 | 61.3 | 85.0 | 40.8 | 76.8 | 60.8 |
| Molmo2-ER | 8B | **77.3** | 52.5 | 32.0 | **73.4** | 54.0 | 87.8 | **46.8** | 78.8 | 62.8 |
| **LightNav-ER** | 4B | 64.5 | **57.4** | 56.5 | 71.9 | **76.6** | **88.4** | 43.8 | **79.8** | **67.4** |

</details>

## ⚡ 快速开始

```bash
git clone https://github.com/lightorigins/LightNav-0.git && cd LightNav-0
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[vllm,video]"
hf download LightOriginsHQ/LightNav-0 --local-dir checkpoints/LightNav-0
```

在视频片段上预测——发布的检查点自带动作解码器，因此 `--model_path` 是唯一需要的资产参数：

```bash
lightnav-predict --model_path checkpoints/LightNav-0 \
    --backend vllm_local --video clip.mp4 --fps 4 \
    --instruction "follow the person in the red shirt"
```

或将其作为服务运行，并通过 WebSocket 流式传输帧：

```bash
PORT=8050 lightnav-serve --task tracking --model_path checkpoints/LightNav-0 --backend vllm_local
lightnav-ws-client --server ws://localhost:8050 --video clip.mp4 --fps 4 \
    --instruction "follow the person in the red shirt"
```

Habitat 评测、EVT-Bench、Python API、Docker 以及 Blackwell `sm_103` 变通方案：
**[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**。

## 🕹️ 在仿真中试用

[`mujoco_demo/`](mujoco_demo/) 是一个自包含的 MuJoCo TurtleBot，位于捆绑的 ProcTHOR 场景中——
客户端无需 ROS、无需 Habitat、无需 GPU：

```bash
cd mujoco_demo && ./run.sh        # needs uv; then open http://127.0.0.1:8088
```

将 Web 控制台指向你的 `lightnav-serve` 地址并输入指令；它使用与
[`robot_deploy/`](robot_deploy/README.md) 中真实机器人相同的 MPC 和客户端协议进行驱动：

![MuJoCo demo: the simulated robot navigates to the trashcan from a language instruction](docs/assets/mujoco_demo.gif)

同一运行时还支持可选的 **MicroDuck** 双足机器人：Pollen Robotics 的 MJCF 和 ONNX 行走策略
位于同一 MPC 之下，因此 LightNav 的路点会转化为步态指令。需要获取的两个外部文件列于
[`mujoco_demo/README.md`](mujoco_demo/README.md#microduck-optional)：

![MuJoCo demo at 2x speed: the MicroDuck biped follows "turn around, go to the TV" from its head camera, with LightNav's pointing markers and waypoint trail overlaid and a third-person picture-in-picture](docs/assets/mujoco_microduck.gif)

## 🤖 真机部署

模型运行在 `lightnav-serve` 背后的 GPU 主机上；机器人端运行一个轻量级 WebSocket 客户端
（任意语言），它流式传输 JPEG 帧和指令，并在每个控制周期执行返回的第一个
路标点。多台机器人可以共享一个服务器——会话会进行
微批处理。

不想自己编写机器人端？[`robot_deploy/`](robot_deploy/) 是一套完整的
ROS 2 机器人端栈——相机驱动、WebSocket 客户端、MPC 路标点跟踪器和一个 Web 控制
面板——带有 Unitree Go2 和 LimX TRON 1 的适配器，以及一个
[自带机器人](robot_deploy/README.md#bring-your-own-robot)适配器接口。

客户端循环、速度映射和通信协议见
[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md#real-robot-deployment)、
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) 和 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

## ✍️ 提示词指南

什么构成一条好的导航指令：一个**动作动词**（`Go to` / `Walk to` / `Head to`
/ `Walk towards` / `Approach`——任意一个都可以）、一个可选的**方向**、一个**无歧义的物体
短语**，以及一个可选的 `and stop`：

```
[action verb] + [direction (optional)] + [disambiguated object phrase] + [and stop (optional)]
```

“无歧义”意味着*哪个*物体是目标毫无疑问。每条指令从下面四种
策略中选**一种**——不要叠加使用。按可靠性排序（每个示例都是
经过验证的真实指令）：

**① 方向 + 物体——最可靠，优先使用。**

```
Turn left and walk to the red lamppost
Go to the front-left TV
Go to the desk on your right and stop.
Turn right, then walk to the chair and stop.
```

方向可以放在动作之前（`Turn left and go to X`），也可以跟在物体之后
（`the desk on your right`）——两者都可行。室内优先使用 `front-left` / `front-right` /
`in front`；室外优先使用 `turn left` / `turn right`。方向是相对于
**机器人**的，而不是相对于房间的。

**② 关系锚点（`next to` / `on` / `behind`）——次选。**

```
Walk towards the trash can next to the green lawn
Walk to the vase on the dining table ahead.
Go to the table behind you
Head to the plant behind you on the right.
```

`A next to B` / `A on B` / `A behind you` 都可行——`behind you` 尤其有效，
因为它同时给出了方向（转身）和消歧。选择一个**大而
显著**的锚点 B（草坪 / 树木 / 餐桌 / 走道），而不是另一个小物体。

**③ 极值（`leftmost` / `nearest`）——可用。**

```
Go to the leftmost TV in front
Walk to the rightmost curtain.
Turn left and walk to the nearest grey pointed stone bollard on the park lawn
```

`leftmost` / `rightmost` 优于 `nearest` / `farthest`：前者直接可见，
后者需要深度估计。

**④ 序数（`first` / `second` / `third`）——最弱，谨慎使用。**

```
Walk to the first wooden park bench on the right
Turn left and walk to the second stone bench from the left.
Go to the first chair on the right side of the dining table
```

序数**必须**附带计数方向（`from the left` / `on the right`），
否则从哪里开始计数会有歧义。避免使用超过 `third` 的序数；要单独指出
某个物体，优先使用极值（`leftmost`）或关系（`next to the door`）而不是序数。

## 🔗 引用

如果你觉得这项工作有帮助，请考虑引用：

```bibtex
@misc{lightnav0,
  title  = {LightNav-0: Eliciting VLM Spatial Intelligence for Generalist Embodied Navigation},
  author = {Light Origins Team},
  year   = {2026},
  eprint = {2608.30935},
  archivePrefix = {arXiv},
  url    = {https://arxiv.org/abs/2608.30935}
}
```

## 🙏 致谢

基于 [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL)、[vLLM](https://github.com/vllm-project/vllm)、
[Habitat](https://github.com/facebookresearch/habitat-lab)、[VLN-CE](https://github.com/jacobkrantz/VLN-CE)
和 [EVT-Bench / TrackVLA](https://github.com/wsakobe/TrackVLA) 构建。第三方代码和许可证
列于 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 📄 许可证

本项目基于 [Apache License 2.0](LICENSE) 发布。EVT-Bench 本身采用
CC BY-NC-SA 4.0，未在此处再分发。

<a id="community"></a>

## 💬 社区

问题、部署说明和发布新闻——在
[Discord](https://discord.gg/zwZuD9JG) 上加入我们，或扫码加入微信群：

<div align="center">
  <img src="docs/assets/wechat_group.png" alt="WeChat QR code for the LightOrigins discussion group" width="280"/>
</div>
