# AXU3EG 原 SD 镜像识别记录

2026-10-16，通过 COM11、115200/8N1、无流控登录现有系统。使用厂商文档中的出厂账号成功登录，仅运行系统信息、进程、目录、脚本、内核日志和状态文件的读取命令；没有执行重新检测、刷写、FPGA 下载、网络配置或重启。

本次对象是开发板现有的厂商镜像。以下证据不能计入新 RasterIX 镜像的启动、图形或性能验收。

## 实际系统

| 项目 | 读到的结果 |
|---|---|
| 系统标识 `/etc/issue` | PetaLinux 2020.1 |
| 内核 | `5.4.0-xilinx-v2020.1`，AArch64，2022-09-06 编译 |
| 用户态版本 `/etc/version` | `20220906112312` |
| 根文件系统 | SD 的 `/dev/mmcblk1p2`，ext4，已进入 `root@petalinux:~#` |
| 存储识别 | SD 29.5 GiB；eMMC 7.09 GiB |
| PS 内存 | 内核识别约 4 GiB；`MemTotal=4030060 kB`，CMA=256 MiB |
| 桌面 | Xorg :0、Matchbox 桌面/窗口管理器正在运行 |
| 厂商界面 | `/home/root/board_check/alinx_ui1`，本次 PID 707 |
| 自启动入口 | `/etc/rc5.d/S99Start` → `/home/root/board_check/board.sh` |
| 网络服务 | Dropbear SSH 服务正在运行；已识别 eth0/eth1、can0/can1 |
| 当前网络 | eth0 无链路、无 IPv4；eth1 未启用；没有进行网口功能测试 |
| 显示 | `/dev/dri/card0` 对应 ZynqMP DP；`card0-DP-1/status=disconnected` |
| 视频/GPU | 存在 `/dev/video0`、`/dev/mali`；USB 2/3 Hub 已枚举 |

设备节点或驱动存在只说明已经识别相关接口，不表示摄像头、GPU 渲染、USB 外设和网口已经实测通过。当前没有 DP 显示器连接证据，也没有截取板上实际图形。

## 镜像包含的自检项目

从 `/home/root/board_check/shell/check_start.sh` 读到 18 个项目：QSPI、EMMC、EEPROM、M.2_SSD、MIPI、PL_CLK、USB、PS_ETH、PL_ETH、PL_UART、RS485、CAN、LM75、J45、J46、ps_key、pl_key、jtag。对应摄像头、网络、USB、串口、CAN 和扩展接口测试需要相应的外设或回环接线。

`board.sh` 启动 `shell/start.sh` 与 `ui.sh`；后者设置 `DISPLAY=:0.0` 后启动 `alinx_ui1`。启动脚本会检查 EEPROM 中保存的版本合格标志；若已有合格记录且未要求强制检测，就跳过本次完整测试。

本次读取到：

```text
/var/volatile/check_result/history_result = ok
/var/volatile/check_result/check_end = skip
/var/volatile/check_result/EEPROM = ok
```

因此，当前状态包含历史出厂合格记录，并没有完成本次 18 项重新检测。没有执行 `force` 或点击“重新检测”。

## 内核日志观察

系统已挂载 SD 根文件系统并进入正常多用户环境。内核日志含 MIPI 初次探测/时钟等提示，随后视频设备已注册；这些日志尚未用于判定接口是否损坏。DP 当前未连接，日志中的无显示模式提示与该状态一致。

FAT 启动分区日志提示上次未正常卸载。本次未运行 fsck，也没有据此判定文件已损坏。

## 原始串口记录

- `report/factory_serial/com11_system_20261016_140917.log`：内核、启动参数、进程、接口及分区。
- `report/factory_serial/com11_factory_apps_20261016_141021.log`：厂商程序、自启动脚本及完整 dmesg。
- `report/factory_serial/com11_tests_20261016_141112.log`：自检目录、DP 状态、Mali 节点及系统标识。
- `report/factory_serial/com11_test_inventory_20261016_141145.log`：完整自检脚本和结果目录。
- `report/factory_serial/com11_result_state_20261016_141227.log`：历史合格和本次 skip 标志。

读取结束后已关闭本机串口句柄，COM11 可由用户的串口终端继续打开。新 RasterIX 镜像的上板验证仍待进行。
