# FPGA FSR1 第三轮优化：EASU 调度

目标是在 XCZU3EG 上保留完整的定点 EASU12＋RCAS5，继续降低 400×240→800×480 的处理时间。此前 v10 快照预取实测为 18.52 FPS；这属于最终新输出，游戏源约 60 FPS。

## 当前本地结果

| 版本 | EASU／RCAS 启动间隔 | HLS 最大计算延迟，100 MHz | HLS LUT | HLS DSP | HLS BRAM18K |
|---|---:|---:|---:|---:|---:|
| v10 pipeline | 12／6 | 46.138 ms | 31,088 | 118 | 122 |
| v12 e10r6 | 10／6 | 38.458 ms | 33,674 | 150 | 124 |
| v13 e8r6 | 8／6 | 30.778 ms | 33,974 | 150 | 124 |

v13 从 v12 生成，仅将 EASU 及调用循环的 PIPELINE II 从 10 调整为 8，继续使用两个 tap 单元、两个 decode 单元和一个共享 fdiv 单元。RCAS 保持 II6。与旧的 II8／RCAS4 实验不同，这次不增加 RCAS 除法单元。

v12、v13 均通过 19 张完整图，共 7,296,000 像素的逐字节比较，输出与已验收的 v8 定点参考一致。v13 的 native 结果在 `build/fsr-pl/fixed-v13-e8r6/functional/result.json`，源 manifest SHA256 为 `cef5cf6578f86a473dd844462db33e01e102cb50c1b0e6855beb15abca8046fc`。

v12、v13 的独立缩小 C/RTL 均已通过：8×6→16×12、两帧、九次命令，FIFO 深度 16；输入／输出 AXI 声明仍为 96000／384000，保留有效输出范围外的 sentinel 检查。两套整机工程正在构建，不能将上述 HLS 延迟转换为已实测的游戏帧率。

## DDR 和显示所有权

继续采用 v11 的固定 64-word 内部写请求：收齐一块后再发起写操作，接收该块最后 B 响应后才开始下一块。v13 的 CSR、AXI 适配器、store_burst、store_task 与 v11 逐字节一致。运行程序继续等待 AP_DONE 和帧标签，再提交非活动高分辨率 bank。

ARM 端沿用已验证的快照预取控制程序；正常游戏路径无 CPU 像素处理。新程序必须重新绑定新位流和源 manifest 摘要，旧 v10 可执行文件不能直接用于新镜像。

FSR 的 BRESP／RRESP 尚未传播到 ap_return，旧 GPU 错误计数不能替代全帧金标准检查。部署前仍需完整路由／时序、实际位流来源核对、三组完整输出和 LCD 样本检查、真实游戏测量。

## 独立工程

- v12：`build/vivado_fsr_fixed_v12_e10r6/rasterix_fsr_fixed_v12_e10r6.xpr`
- v13：`build/vivado_fsr_fixed_v13_e8r6/rasterix_fsr_fixed_v13_e8r6.xpr`
- 实现使用短路径 `build/fsr-v12-runs`、`build/fsr-v13-runs`，避开 Windows 调试 IP 路径长度限制。
- 原 v10 已验收的工程、源、工具脚本、位流和报告保持不变。

本轮计划使用 RAM 加载与回退；当前尚未加载 v12／v13，没有修改 SD 启动包或默认游戏入口，也没有把风格化串入本次性能测量。
