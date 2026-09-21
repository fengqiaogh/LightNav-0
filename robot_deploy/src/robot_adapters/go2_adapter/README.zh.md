<!--
  Auto-translated from robot_deploy/src/robot_adapters/go2_adapter/README.md. Edit the English source, not this file.
  Frozen human translations: put translate: skip in an HTML comment.
-->

[English](README.md)

# go2_adapter

通过 `unitree_sdk2py` 将 Go2 接入本项目通用的 ROS 2 机器人接口。

## 接口

- 订阅：`web/cmd_vel`、`mpc/cmd_vel`
- 发布：`odom`、`cmd_vel`、`control/source`、`diagnostics`、`robot/events`
- 服务：`control/set_manual`、`control/set_auto`、`control/stop`
- 服务：`robot/stand`、`robot/walk`、`robot/sit`、`robot/emergency_stop`

在 Go2 上，`robot/sit` 会先释放速度控制，然后调用 `StandDown()` 执行受控趴下。

`odom` 直接转发 Go2 的 `rt/lf/sportmodestate`；底层状态来自 `rt/lowstate`。部分固件不会填充其 BMS 电量百分比，此时网页会显示空电量读数，而不会将无效值误报为 0%。速度通过 `ObstaclesAvoidClient.Move()` 发送，模式命令通过 `SportClient` 发送。

当控制源为 `disabled` 时，适配器不会获取 Unitree API 控制权。只有在收到第一条有效的手动或 MPC 速度命令时，它才会获取控制权；当控制源关闭时，它会先发送零速度，然后将控制权交还给遥控器。

在遥控器的 `START` 解锁后，机器人可能仍持续上报 Unitree `mode=0`。适配器将机身高度至少为 0.2 m 的 `mode=0` 映射为通用接口的 `WALK`；机身高度过低或 `error_code=1001` 仍映射为 `DAMPING`。

## 运行

系统需要预先安装 Unitree 官方的 `unitree_sdk2_python` 及其所需的 CycloneDDS 0.10.2。默认网络接口为 `enP8p1s0`：

```bash
ros2 launch vln_bringup go2.launch.py
```

使用 `network_interface:=eth0` 覆盖默认接口。
