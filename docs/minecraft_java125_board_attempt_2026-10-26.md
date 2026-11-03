# 官方 Minecraft Java 1.2.5 板端尝试

日期：2026-10-26。目标板 AXU3EG / XCZU3EG，Linux AArch64，PS 串口 COM11。此次响应“尝试下早期版本”，使用官方 1.2.5 客户端，游戏 JAR 未修改。

## 已经得到的结论

**ARM64 Java、AWT/X11、LWJGL 本地库和 GLX 上下文已经实机跑通；官方客户端在启动贴图上传处报错，尚未进入菜单和世界，不能给出可玩帧率。**

这次证明 Java 运行环境可用，尚不能据此判断世界生成、实体、GC 或实际游戏帧率。当前首先阻挡客户端的是图形接口兼容。

| 层次 | 实测结果 | 证据边界 |
|---|---|---|
| Java 8 ARM64 | 通过，1.8.0_512-b08，64-Bit Server VM | JVM 启动，不代表游戏性能通过 |
| AWT / X11 | 通过，sun.awt.X11.XToolkit | 使用板上现有 Xorg :0 |
| LWJGL 2.9.0 | 通过，is64bit=true | 自行交叉编译匹配的 ARM64 JNI 库 |
| GLX 创建和查询 | 通过，renderer=RasterIX，最大纹理128 | GL_VERSION=OpenGL ES-CM 1.1；LWJGL 的桌面 OpenGL11 标志为 false |
| 官方客户端启动 | 已执行，进入图形初始化和启动图片绘制 | 贴图上传失败，随后抛出 OpenGLException |
| 正常菜单 / 世界 / 键鼠游玩 | 未通过、未验证 | 初始化阶段已经失败 |
| 游戏 FPS / FSR / CNN 联动 | 无有效结果 | 本轮没有接入 Java 游戏的超分和风格网络 |

两个启动阶段的呈现计数变化不能作为游戏 FPS，也不构成菜单或世界画面验收。

~~~mermaid
flowchart LR
  A["官方1.2.5 JAR<br/>保持原文件"] --> B["ARM64 Java 8<br/>实测通过"]
  B --> C["AWT与LWJGL JNI<br/>实测通过"]
  C --> D["RasterIX GLX上下文<br/>创建与查询通过"]
  D --> E["256×256启动贴图<br/>超过128×128上限"]
  E --> F["菜单与世界<br/>尚未验证"]
  style E fill:#ffe0dc,stroke:#c63524
~~~

## 实际失败位置

原始日志：

    glTexImage2D texture is too big.
    org.lwjgl.opengl.OpenGLException: Invalid value (1281)
        at org.lwjgl.opengl.Display.swapBuffers(Display.java:617)
        at net.minecraft.client.Minecraft.v(SourceFile:390)
        at net.minecraft.client.Minecraft.a(SourceFile:256)
        at net.minecraft.client.Minecraft.run(SourceFile:657)

对官方客户端字节码的只读检查显示，Minecraft.v 在此启动路径读取 /title/mojang.png。该图片为256×256。客户端内的 terrain.png 和 gui/items.png 也为256×256；因此仅修复启动 Logo 还不能解决后续图集问题。

运行库的实际查询上限为128，与[项目配置](../config/rasterix_axu3eg.json)及驱动拒绝超尺寸上传的行为一致。本轮保留原上限和版本字符串，没有通过伪造能力跳过错误。

[客户端资源与方法引用审计](../report/minecraft-java-125/client-api-audit.json)记录345张 PNG 和 LWJGL 方法引用。常量池引用能证明客户端包含相关调用，不能替代完整的动态调用覆盖。

## 还需适配的内容

1. **纹理与动态纹理。** 可选择私有兼容层将256图集缩到128，或实现分页；前者会把图集中16像素的方块纹理压到8像素。动画纹理的子区域更新、偏移和尺寸也必须同步转换。颜色查找表等由 CPU 读取的图片不能一概缩小。若选择这种方案，文档必须说明纹理质量变化。
2. **显示列表。** 当前 glGenLists 返回0，glNewList/glEndList/glCallList/glCallLists 尚未实现。客户端包含这些调用。仅修复贴图并不能让区块网格正常显示；需要补充列表记录、回放和释放。捕获 glDrawArrays 时必须复制实际顶点数据，不能保存随即会被 Java 复用的缓冲指针。
3. **能力报告、光照及多纹理。** 本轮观察到部分扩展被报告可用但缺少入口，且桌面 OpenGL11 标志为 false。需逐项核对客户端实际使用的扩展和单 TMU 下的光照策略；尚未完成兼容验收。
4. **性能。** 接通正确的菜单、世界和输入后，才适合测不同视距、分辨率、堆大小和 GC。ClassiCube 既有57 FPS不能推算成官方 Java 版的帧率。

这些前端兼容工作主要位于 PS 上的 GL/JNI 适配；通过适配后，光栅化仍可以交给 PL RasterIX。FSR、CNN 后处理不会补齐缺失的显示列表或纹理语义。

## 两周提交期内如何取舍

继续把已经验收的 ClassiCube＋PL RasterIX＋PL FSR作为参赛演示主线。官方 Java 版可保留为有时间关口的扩展任务：

- 第一关：启动图、菜单和退出正确，截图可复现，无 OpenGL/DMA 错误。
- 第二关：显示列表、图集和光照适配正确，能够进入小世界并用键鼠游玩。
- 第三关：同一世界、视角、视距下测源帧率、呈现帧率和帧时间，再对比后处理开关。

前两关未通过前，不承诺原版可玩或60 FPS，也不因版本更老就默认兼容。进一步换成 Beta 版本仍须审计它的纹理与显示列表，不能假设这些缺口自然消失。

## 实现与复现资料

- [官方文件解析](../scripts/prepare_minecraft_java_125.py)、[下载与摘要校验](../scripts/fetch_minecraft_java_125.py)：固定官方客户端、依赖和 JRE；补充固定 SHA-256 的 LWJGL 发布源码及 JNI 头文件。
- [JNI 头文件生成](../scripts/lwjgl_jni_headers.py)：从已校验的2.9.0 JAR提取原型和常量，避免依赖已经废弃的 javah/apt 工具链。
- [ARM64 原生库构建](../scripts/build_lwjgl2_aarch64.sh)：使用现有2020.1 SDK，编译194个 C 源文件。LWJGL 官方 Git 标签与发布源码的65个重叠 C 文件，经换行规范化后完全一致。
- [短时探针](../linux/java_minecraft/Java125Probe.java)、[正常关闭包装器](../linux/java_minecraft/Java125ClientHarness.java)、[板端运行器](../linux/java_minecraft/run_java125_probe.py)：各阶段分开记录，保留完整错误、GPU 计数和恢复标记。
- [RAM 传输](../scripts/transfer_java125_ram.ps1)：在已保留且 no-map 的 PS DDR 区域分块暂存，经每块和整文件 SHA-256 校验后落到板上 /tmp，未把 JRE 安装到空间有限的根分区或启动分区。

官方客户端 SHA-1：4a2fac7504182a97dcbcd7560c6392d7c8139928。

ARM64 LWJGL 原生库 SHA-256：d220c44d0f26b56a82ccb25103b974c782f7d1dd136a036ebf0fd9b78a9e7ffa。

本地依赖和构建输出位于 build/minecraft-java-125；游戏本体仅用于本地测试，参赛源码提交应提供获取脚本与版本摘要，不能把官方游戏 JAR 当成项目自研源码。

## 测试退出与恢复记录

首轮客户端报错后仍保留 AWT 窗口，初版脚本45秒后以 SIGTERM 结束进程。虽然 GPU 五组队列均已完成、硬件错误计数为零，脚本仍按保守策略记录恢复标记。该轮客户端退出码143，不能标为成功。

本轮已备份、回读并校验原有 RAM 运行文件，执行正常 Linux 重启，随后通过原事务控制器依次实际加载并验证 atomic-v4 和 FSR v23；未修改 BOOT.BIN、Image 或 system.dtb。新启动 UUID 为 b007f055-e929-49ec-935f-a5325c374de7，重新生成当前启动对应的 FSR 生效凭据，未更改旧凭据的 UUID 冒充加载验证。

原 ClassiCube GL、v23 游戏入口和 ahead FSR 运行库保持原摘要，恢复检查日志见[位流加载](../report/board_serial/java125_restore_fsr.log)和[空闲状态](../report/board_serial/java125_restored_v23_idle.log)。

正常关闭包装器调用客户端原有的 windowClosing 流程；原监听器依次请求 Minecraft 停止、等待游戏线程结束，然后退出。实际复测在12.454秒结束，出现 JAVA125_NORMAL_CLOSE_REQUEST Minecraft，退出码0、未超时、未新增恢复标记；仍复现同一1281贴图错误，游戏验收为失败。退出码0只证明正常关闭，不等于游戏成功。

随后通过原 ClassiCube v23 入口进行12秒自动运行的恢复检查：视距32，FPGA FSR完成599帧并正确释放快照，全部硬件错误计数为零。该检查只验证恢复可用，不替代此前的同场景长测，也不构成新的稳定60 FPS结论。结束后无 Java、游戏或FSR进程残留，POST恢复模式1，快照占用与过期次数为零。

复测和恢复完整归档：[java125_final_evidence.bin](../report/postproc_java125_final_evidence.bin)，SHA-256为1daf252da7af927fe844b6a97d6c6641fbfc5733aaf956fd44ff0f8f84390387。[最终状态](../report/minecraft-java-125/final/java125-final-state.json)和[正常退出复测结果](../report/minecraft-java-125/final/result-client-clean/result.json)明确区分“证据与恢复验证通过”和“Java游戏尚不可玩”。

首轮完整归档：[java125_evidence.bin](../report/postproc_java125_evidence.bin)，SHA-256为365ebf0000970b429b3c54e2a5fd3d738d9bdf384e3b93a543605fb9ac0d9195。可展开查看[首次客户端完整日志](../report/minecraft-java-125/first-attempt/result-client/stdout.log)和[结果](../report/minecraft-java-125/first-attempt/result-client/result.json)。
