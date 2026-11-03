# CNN 四核取帧与精确 NEON 缩放

## 已部署结果

保持相同 FPGA、160×96 油画 / 动漫权重和插值规则，进一步优化 ARM 端。Neverball 同一套自动操作和取证流程下：

| 风格 | 上轮单核 | 本轮四核 | 观察到的倍率 |
|---|---:|---:|---:|
| 油画 | 8.56057 FPS | 12.30120 FPS | 1.437 倍 |
| 动漫 | 8.52362 FPS | 12.06950 FPS | 1.416 倍 |

各自为独立游戏运行中的约六秒窗口，包含输入、CNN 输出和显示帧落盘，并非同一瞬间的画面。本轮分别处理 74 / 73 帧。正式入口无诊断落盘的连续运行单独记录在 `frame-continuous.json`，不混为同配置比较。

正式入口动漫模式连续约 60 秒处理 **724 帧，平均 12.0558 FPS**，正常退出。ARM / FPGA 两个后端的时限结束与 SIGTERM 退出均通过；最终无残留游戏、神经进程或快照租约，快照过期和五类 GPU 错误均为零。28 个安装文件全部与当前清单一致。整体工程检查 **38/38**，本轮检查 **22/22** 通过。

| 本轮平均阶段耗时 | 油画 | 动漫 |
|---|---:|---:|
| 快照获取与复制 | 19.78 ms | 20.65 ms |
| 其中四核复制 | 18.79 ms | 19.69 ms |
| 输入缩小 | 1.27 ms | 1.28 ms |
| PIO + FPGA CNN | 32.94 ms | 32.90 ms |
| 显示放大 | 7.65 ms | 7.78 ms |
| PL 写回 | 8.27 ms | 8.14 ms |
| 帧边界换页等待 | 8.24 ms | 9.04 ms |

## 实现与验证

`pl_frames.hpp` 将源行分给四个 A53 线程，读取量仍为所需的 192 行、307,200 字节。各线程写不同 CPU 缓冲区，分别完成 Device 读取屏障，全部 join 后主线程才验证 token / READY 并释放 SNP1 租约。保留预取、过期丢弃和退出释放；信号标志使用编译期保证无锁的原子变量。

`frame_resample.hpp` 使用 NEON 垂直插值。累计值 −3200～3175，绝对值加 12 后以 2622 的乘法高位精确除以 25，保持原先带符号半入舍入。A53 上已穷举该范围，同时对 14 组随机、全色域、边缘及极值图像约 1,785 万个数值与原版浮点缩放对照。线程分区测试核对单核、双核、四核输出及未读取行。

GPU 空闲、同一非显示 HR 槽、交替执行、排除预热后各五次的读取中位数为单核 **46.95 ms**、双核 **27.52 ms**、四核 **11.76 ms**；完整写入回读全部一致。真实游戏另有调度和访问开销，复制约 19 ms。停止神经处理后可运行 `bin/benchmark-frame-io` 复测。

两种最终 CNN 输出都与 NumPy 整数参考逐位一致，每种额外完整回读 1,536,000 字节显示缓冲，并核对 6,000 个真实 LCD RGB565 采样。证据位于 `report/neural-style/`：

- `cnn_parallel_final_vgfqp9k/host-verification.json`
- `frame-parallel-optimization.json`、`frame-io-benchmark.json`
- `frame-resample-selftest.txt`、`arm-pl-vectors.json`
- `cli-pl.json`、`cli-cpu.json`、`frame-continuous.json`

网络容量和训练权重未变，画质仍为原先的小网络原型，`quality_acceptance: false`。仍有 PIO 和 CPU 搬运，未宣称 30 FPS 神经显示。

## 未启用的映射试验

曾按实际 Linux 5.4 构建只读 RFM1 帧映射，测试 Normal-NC。内核对应实现为 BSP 的 `arch/arm64/include/asm/pgtable.h`；[ARM64 页属性定义](https://github.com/torvalds/linux/blob/master/arch/arm64/include/asm/pgtable-prot.h)区分普通无缓存与 Device 内存。

单核 Normal-NC 成组读取约 48.5 ms，未超过 Device，memcpy 更慢。因此模块已卸载，排除在交付包和自动启动之外；当前继续使用原有 Device 属性及屏障。实验源码在 `linux/rix-frame-mem/`，数据在 `memory-attributes-benchmark.json` 和 `parallel-memory-benchmark.json`。

## 使用与版本

```sh
rix-neural-games neverball --style anime --backend pl-int8 --seconds 60 --autoplay
```

油画使用 `--style oil`，ARM 对照使用 `--backend cpu-int8`。连续神经画面验证使用 Neverball，其余游戏按各自原有证据验收。

主程序 SHA256：`898fd26e3c42bcbb4bb7b310e9dde14cc8cdd180ffb00b235a512f6c95a1fcd5`。运行包 295,300 字节，SHA256：`61a34e2e29cd9e477be38103256f7ff276821a87d475d24ebd28b1f7a6fa797a`，已安装至 SD 根文件系统。上轮 `80aae9…20f74` 保留为 `bin/rix-neural-style-single-core`。

本轮未修改启动文件、RTL、设备树或权重，沿用已验证的 NNS1 启动包，未重新生成整卡 `.img`。更早的资料和启动包回退见 [神经风格迁移记录](NEURAL_STYLE_2026-10-20.md)。
