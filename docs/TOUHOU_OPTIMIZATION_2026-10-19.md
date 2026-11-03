# 东方第二轮优化：画质、输入、显示与运行维护

本轮已部署至 AXU3EG 的 SD 根分区。当前默认 **balanced**：按游戏 640×480 → 320×240 内容分辨率做透明边缘预滤波，再用 128×128 页面在 FPGA 上采样。原作逻辑、资源和关卡脚本不变，ARM 继续处理逻辑、顶点与纹理准备，FPGA 继续完成像素渲染和 LCD 输出。

本轮 **28 项验收全部通过**，见 [验收报告](../report/touhou/opt2/acceptance.json)。首版二进制、图像和验收记录保存在 `build/touhou/baseline-v1`、`report/touhou/baseline-v1`；修复菜单前的中间测量保存在 `report/touhou/opt2-before-menu-fix`。

## 画质和渲染开销

旧版把每张图集整体缩到最大 128×128，大图集中的小字和弹幕会丢失。现在有三种可选模式：

| 模式 | 纹理处理 | 相同 20～55 秒区间平均渲染 FPS | 逻辑 Hz | ARM 绘制提交中位数 |
|---|---|---:|---:|---:|
| scaled | 旧版整图缩小，保留作对照 | 28.96 | 60.00 | 0.856 ms/帧 |
| **balanced，默认** | 2×2 透明度加权预滤波，再分页 | **28.99** | **60.00** | **1.109 ms/帧** |
| native | 原始图集逐页采样 | 18.86 | 60.00 | 4.741 ms/帧 |

以上为同一二进制、官方体验版素材和普通输入 bot 的实机结果，随机种子及同一时刻的具体场景可能不同，不能把微小的均值差视为确定的加速收益。本轮主要收益是改善纹理细节，同时保持默认模式的速度与旧缩图模式相近。

balanced 持续 90 秒测试中，启动之后的完整采样区间平均 **28.18 FPS**，复杂场景的 60 帧采样窗口最低约 **21.22 FPS**；逻辑仍为 **59.99 Hz**。尚未实现稳定的 60 渲染 FPS，约 30 FPS 也不是所有场景的保证。GPU 忙时、ARM 提交、后台光栅化/DMA 和显示等待存在重叠，不应简单相加。

具体改动位于 `ports/th06/RasterIXTextures.cpp`、`AtlasTiles.hpp` 和 `AtlasImage.hpp`：

- 保留大图集的归一化 UV；跨页三角形在 UV 平面裁切，并插值位置、深度和顶点颜色，处理负 UV 与重复纹理。
- 同页批次直接复用原顶点数组和纹理矩阵；跨页片段按原顺序合并连续同页批次，保留透明混合次序。
- 剔除裁切边界上的零面积片段，避免向 RasterIX 提交无效小三角形。
- 图片和字体变更只使受影响页面失效，按需上传，其余页面复用。缓存优先回收前一帧以前使用的页面，不回收当前帧正在引用的页面。常规预算 192 页，当前实测 balanced 最多 10 页、native 最多 27 页。
- balanced 用预乘透明度的盒式平均，再还原直通 RGB，减少透明边缘的黑边；预滤波发生在纹理准备/修改时，并非逐帧 CPU 后处理。

SDK、RTL、100 MHz GPU 时钟、400×240 帧缓冲和 `0x9adb505e` 配置均保持原值。

## 菜单稳定性与背景缓存

实际发布入口检查发现，官方体验版不含移植引擎所期待的 `data/demo/demo00.rpy`，静置 720 个逻辑帧后尝试播放会退出。现在仅在文件存在时进入演示回放；不存在时保留标题/菜单，并限制空闲计数，避免无意义增长。

另一个瓶颈是 `ApplySurfaceToColorBuffer` 每帧创建、转换、上传并删除同一张标题 JPEG。现按不可变 SDL Surface 缓存其纹理，在 `ReleaseSurface`/`ReleaseSurfaces` 中同步失效，避免指针复用造成旧图。菜单由约 **15 FPS 提升至 30.06 FPS**，预热后背景上传为 **0 字节**，绘制提交中位数约 **0.103 ms/帧**。

已用真正的 `rix-th06-run` 入口静置运行 40 秒，正常到达超时退出；物理 Goodix 自动识别成功，GPU/LCD 6000 点全部一致。触摸从菜单进入关卡、返回资源释放和三模式关卡测试均重新通过。

![修复后的实际标题画面](../report/touhou/opt2/menu/final-frame.png)

## 触摸控制和真实 FPS

游戏现在直接读取 Goodix evdev 多点触摸事件，无需依赖 X11 窗口位置，也不独占触摸设备。键盘和手柄仍可并用。

| 场景 | 操作 |
|---|---|
| 菜单 | 点中部确认；上/下区域选择；中部左右区域左右选择；最右边返回 |
| 游戏 | 在游戏区域按住并拖动：移动、持续射击和低速模式 |
| 炸弹 | 第二根手指点右侧 HUD 下部 |
| 暂停 | 点右侧 HUD 上部 |

炸弹和暂停只在新触点按下时触发。手指释放、事件丢同步或设备断开会清除对应触摸输入。可用 `--no-touch` 关闭。

已通过主机状态机测试，并通过临时 uinput 设备在真实游戏中操作菜单进入第一关，验证拖动、射击/低速、第二指炸弹、暂停和释放清零。虚拟设备在测试结束后销毁。**这不等于实际手指验证**，物理屏幕方向和操作手感仍需确认。

屏幕右下角 FPS 现取自真实 FPGA 呈现 ACK 的最近 30 帧，不再沿用原引擎的 frameskip 换算值。

## 统一启动入口和 FPGA 风格化

```sh
# 默认平衡画质、原色、最近邻、自动接入物理触摸
/opt/rasterix/touhou/th06-runtime/bin/rix-th06-run

# 平衡画质 + FPGA 双线性输出 + 复古配色
/opt/rasterix/touhou/th06-runtime/bin/rix-th06-run --quality balanced --filter bilinear --style sepia

# 其他配色：original / poster / sepia / binary
# 全原图模式更慢，可按需选择
/opt/rasterix/touhou/th06-runtime/bin/rix-th06-run --quality native --no-touch --seconds 120

# 自动操作一局，120 秒后正常退出
/opt/rasterix/touhou/th06-runtime/bin/rix-th06-run --autoplay --seconds 120
```

参数在访问硬件前验证，`--help` 无硬件副作用；也兼容原来的 `--autoplay 120` 写法。分辨率和 4:3 原作比例保持不变。这里的滤波和色彩风格化运行在已有 FPGA 显示链路上，不启用 CPU FSR。音频本轮仍使用 dummy 驱动。

![实际 LCD 稀疏采样对照](../report/touhou/opt2/lcd-styles.png)

图中是同一 GPU 留帧的实际 LCD 100×60 稀疏采样放大预览，非完整分辨率截图。

## 部署可靠性和空间维护

串口辅助文件改为 gzip 压缩、逐块 ACK、整文件 SHA256 校验后原子替换，修复 PS 串口偶发输入 overrun 时可能得到损坏脚本的问题。大运行包继续通过 JTAG 暂存区传输及逐块/整包校验；传输时仍要求 GPU 空闲。

本轮 30,490,009 字节的过期 TH06 构建缓存已移入 SD 的 `/mnt/sd-mmcblk1p1/rasterix-touhou-cache-backup-20261019`，每份文件先做回读 SHA256，再释放根分区副本。当前运行包、素材和已有游戏未迁移。根分区可用空间由约 **30.78 MiB 增至 59.92 MiB**；备份目录附有清单，可按原文件名复制回原缓存目录。BOOT.BIN、DTB 摘要前后相同。

部署运行包 SHA256：`4d16ed47662b37123841de38ef62471ddf6793c8256088e3b60d2b8097c9b8a7`；原生程序 SHA256：`a6fd453637d0ccbbcd5c63a9bdf731439e0e56683b1e4dacdad69e3821255989`。官方体验版数据包未变。

## 验证和复现

- 主机 3000 个随机三角形裁切测试，以及透明边缘预滤波、菜单/拖动/多点触摸/释放/丢同步测试全部通过。
- 三模式 GPU 数值参考检查累计 **790,028** 个像素全部通过；覆盖跨页、负 UV 重复、单页快路径和局部更新。RGB565 量化允许逐通道最多 9/255 的误差；测试按当前 RasterIX 的整数像素插值约定构造参考，并避开定点采样的精确边界点。
- 同一留帧下，最近邻原色、海报色、复古色、黑白以及双线性原色的 **30,000 个实际 LCD 采样**与 RTL 公式完全一致。独立的原色 GPU/LCD 对照另有 6000 点全部匹配。
- 三模式均完成第一关自动操作并正常退出；硬件读写、超时、显示错误和纹理分配错误均为零。启动文件与硬件配置未变。
- 原有 `rix-danmaku` 的 10 项验收记录保留。

构建仍使用 `scripts/build_th06.sh` 与 `scripts/package_th06.py`。新增验证命令：

```sh
python3 /opt/rasterix/touhou/th06_board_trial.py --attempt fresh_name --texture-mode balanced --seconds 90 --hold 10 --style-qa --autoplay
python3 /opt/rasterix/touhou/th06_board_trial.py --attempt fresh_qa --texture-mode native --seconds 5 --atlas-qa
```

主机归档和复核使用 `scripts/record_th06_optimization.py`、`scripts/verify_th06_styles.py`，原始回读为 `report/postproc_th06_*`。本轮没有验证体验版第二/第三关通关或声音，也没有接入完整版商业素材。
