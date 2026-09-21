<!--
  Auto-translated from robot_deploy/src/vln_mpc/README.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](README.md)

# vln_mpc

VLN 轨迹位姿对齐与 MPC 控制节点。

运行时需要 CasADi `>=3.7,<4`。

## 接口

| 名称 | 类型 | 方向 | 说明 |
| --- | --- | --- | --- |
| `vln/response` | `std_msgs/String` | 订阅 | JSON 推理结果；路点为图像采集时刻 `base_link` 坐标系下的坐标 |
| `vln/status` | `std_msgs/String` | 订阅 | VLN 状态：`IDLE`、`RUNNING` 或 `ERROR` |
| `vln/mode` | `std_msgs/String` | 订阅 | 任务模式：`objnav` 或 `track`；Transient Local |
| `mpc/enable` | `std_msgs/Bool` | 订阅 | `true` 启用 MPC，`false` 禁用；Reliable、Volatile、深度 1 |
| `odom` | `nav_msgs/Odometry` | 订阅 | `odom` 到 `base_link` 的位姿与时间戳 |
| `mpc/cmd_vel` | `geometry_msgs/TwistStamped` | 发布 | MPC 输出的线速度与角速度 |
| `vln/path_odom` | `nav_msgs/Path` | 发布 | 对齐到 `odom` 的原始 VLN 路点；Transient Local |
| `mpc/reference` | `nav_msgs/Path` | 发布 | 跟踪 MPC 使用的位姿对齐参考轨迹 |
| `mpc/prediction` | `nav_msgs/Path` | 发布 | MPC 预测轨迹 |
| `mpc/status` | `std_msgs/String` | 发布 | `IDLE`（已禁用）、`RUNNING`（已启用）或 `ERROR`；状态变化时发布，Transient Local |

## 说明

该节点维护一段近期 odom 历史，并通过 `capture_stamp_ns` 查找图像采集时刻的机器人位姿，将 `vln/response` 中的机体坐标系路点变换到 `odom`。

跟踪 MPC 以 `10 Hz` 运行。每次求解时，它选取距离当前机器人位姿最近的离散路点，用 `q_x`、`q_y` 和 `q_yaw` 对位姿误差加权，然后从下一个点开始取 `horizon` 个点，点数不足时重复最后一个点。随后它在当前机器人位姿处构建固定的局部坐标系，将当前状态归一化为 `[0, 0, 0]`；第 `k` 个控制量产生的 `state[k+1]` 跟踪第 `k` 个参考点。每次求解都用当前参考的有限差分速度作为控制初值，并用独轮车模型推演状态初值——不复用上一周期的解。MPC 约束线速度、角速度、线加速度和角加速度。参考轨迹和预测轨迹仍以 `odom` 发布。

控制频率固定为 `10 Hz`，horizon 为 `5`，MPC 与路点时间步为 `0.1 s`。其余 MPC 参数由各机器人的 launch 文件配置。

`q_x`、`q_y`、`q_yaw`、`r_v`、`r_w`、速度/加速度约束以及输出缩放均支持通过 ROS 2 参数服务热重载。仅在 MPC 禁用且当前求解已结束时才能修改参数；网页在 VLN/MPC 运行时会锁定 MPC 参数面板。修改不会写回 launch 文件——重启节点会恢复机器人的 launch 配置。`v_output_scale` 和 `w_output_scale` 分别在 MPC 求解与约束之后对线速度和角速度输出进行缩放。

任务模式独立于上述 MPC 控制模式。`track` 忽略 VLN 的 `stop` 标志；`objnav` 在 `stop=true` 时立即作废当前求解并停止发布速度。`vln_web` 直接读取同一 VLN 响应，禁用 MPC，释放自动控制，并停止 VLN 请求。

该节点仅在 MPC 求解成功后发布 `mpc/cmd_vel`。在禁用、等待输入、odom 过期或求解失败时不发布速度；停止、控制源选择以及命令看门狗由机器人适配器负责。具体的等待原因、错误和求解耗时记录在日志中。

## 默认参数

| 参数 | 默认值 |
| --- | --- |
| `enabled` | `false` |
| `odom_frame` / `base_frame` | `odom` / `base_link` |
| `track_v_max` / `objnav_v_max` | `1.5 m/s` / `0.8 m/s` |
| `w_max` | `3.0 rad/s` |
| `a_max_v` / `a_max_w` | `2.0 m/s²` / `5.0 rad/s²` |
| `q_x` / `q_y` / `q_yaw` | `10.0` / `10.0` / `1.0` |
| `r_v` / `r_w` | `0.1` / `0.1` |
| `v_output_scale` / `w_output_scale` | `1.0` / `1.0` |
| `odom_match_max_gap_s` | `0.3 s` |
| `odom_timeout_s` | `0.5 s` |
| `metrics_log_period_s` | `2.0 s` |

## 目录结构

- `mpc_node.py`：ROS 接口、位姿对齐与控制循环。
- `geometry.py`：odom 插值与坐标变换。
- `mpc.py`：位姿参考构建与轨迹跟踪 MPC。
