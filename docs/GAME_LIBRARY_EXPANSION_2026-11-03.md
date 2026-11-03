# 游戏库扩展与东方正式版路线核对（2026-11-03）

后续已完成首批十五款目录、七款新增游戏实机验证及菜单扩容，见 [v4 实现记录](GAME_LIBRARY_V4_2026-11-03.md)。用户提出的 TH06 SDL2 项目已另做 [源码与架构核对](TH06_SDL2_FEASIBILITY_2026-11-03.md)。下面保留扩展前的候选规划，不将未移植候选计入已完成数量。

结论：可以将现有八游戏菜单扩展成游戏库。第一批建议以 **11 款可运行游戏为目标**，先增加三个适合固定功能图形链路的候选；东方优先接《红魔乡》正式版内容，再研究《妖妖梦》。这是实施建议，新增候选尚未完成本板移植或帧率验收。

## 当前实际基础

`config/launcher-games.json` 和 `linux/launcher/game_specs.py` 当前列出八个 ID：Tux Racer、Neverball、Neverputt、Quake、Quake III、东方红魔乡、ClassiCube、Minecraft Java。上一轮七游戏 CNN/FSR 测试未包括 Java；Java 继续使用独立双 TMU 配置。

游戏库按次启动一款游戏，复用 RasterIX、显示、输入和后处理。对于使用同一硬件配置的游戏，数量增加主要消耗 SD 素材空间及适配工作，不会按游戏数量累加 LUT/BRAM。运行时仍受单款游戏的 ARM 负载、DDR、纹理分页和图形 API 覆盖范围约束。需要新硬件特性的游戏须另行评估，不能据此认为任何游戏都能直接加入。

当前原生清晰菜单在 RAM 中，重启恢复与 SD 持久部署仍须单独落实。游戏库应有统一的持久素材/存档位置，保留原有游戏存档与旧发布包。

## 第一批扩展候选

| 候选 | 适合展示的内容 | 本项目需要做的工作 | 建议次序 |
|---|---|---|---|
| rRootage | 完整街机弹幕、四种玩法；可与东方对照 | SDL1→现有 SDL2 输入/窗口，固定功能 GL 接入，GLU/线条/纹理限制核对，实际关卡与退出验证 | 1 |
| Kobo Deluxe | 卷轴射击、精灵混合、完整游戏菜单 | 选择并确认 glSDL/OpenGL 路径，避免落入 CPU 软件绘制；纹理分页、输入和音频适配 | 2 |
| Chromium B.S.U. | 纵版射击、粒子、鼠标控制 | 固定功能 GL/SDL 对接，纹理与混合检查，音频依赖处理，控制与菜单返回验证 | 3 |

依据：作者的 [rRootage 页面](https://www.asahi-net.or.jp/~cs8k-cyu/windows/rr_e.html)及[实际 screen.c](https://github.com/abagames/rrootage/blob/master/src/screen.c)使用 SDL 与固定功能 OpenGL；[Kobo Deluxe 官方说明](https://olofson.net/kobodl/)提供可选 OpenGL 加速；[Chromium B.S.U. 官方 FAQ](https://chromium-bsu.sourceforge.io/faq.html)说明其 OpenGL 硬件加速路径。上述适配次序是结合本项目的工程判断，不是作者对 RasterIX 的兼容性承诺。

先实现这三款可把八款扩至十一款。更多游戏可以继续筛选，但不将体验版升级、增加关卡包或尚未移植的封面条目计作新的已运行游戏。

每款通过以下门槛才标为“可玩”：ARM 原生可执行、实际玩法出帧、确认 FPGA 渲染路径、键鼠可控、正常保存/退出/返回、长于标题页的性能采样。FSR 和 CNN 分别标注“已验证/实验/不支持”，不对所有条目统一显示已开启。

## 东方：正式版与更换作品是两件事

### 优先：《红魔乡》正式版内容

当前实机使用官方 **0.13 体验版数据**。源码里已经有 stage1–stage7 的脚本/动画/背景文件表，但不能据此宣称全部关卡已通过：

- `scripts/prepare_th06_data.py` 当前只导入五个体验版 DAT，未导入正式版 ED.DAT。
- `scripts/prepare_th06_port.py` 的 `gui()` 在 `MSG_OPCODE_STAGEEND` 中插入 `currentStage >= 3` 后转成绩页；生成补丁在 `patches/th06-rasterix.patch`。
- 菜单固定从 `th06-demo` 取素材，并校验现有包合同；正式版需要独立的素材合同、版本判断和存档目录。

因此，正式版接入应按下面的顺序做：

1. 导入用户已有 **v1.02h** 正式版资源目录，读取 PBG3 索引并记录版本/哈希；检查 CM/ED/IN/MD/ST/TL 六个 DAT、后续关卡脚本和结局资源。保留体验版原包，不混用 DAT。
2. 将“三关截止”改为由已校验的数据版本控制；正式版恢复原来的后续关卡与结局流程，体验版继续限制访问不存在的资源。
3. 验证四、五、六关、Extra 的加载及实际玩法，再验证结局、成绩、回放、重启存档；检查后段弹幕峰值和纹理缓存。
4. 最后接入游戏库，显示“正式版数据已安装”，并保留体验版作为独立回归项。

该方案复用当前 ARM 原生引擎＋RasterIX 后端，不需要把 Windows x86 EXE 放到 Box64/Wine 上执行。上游 [TH06 移植说明](https://github.com/saekaze/th06-switch#-installation-guide)也使用用户提供的 v1.02h 原作数据，不附带正式版资源。

正式版增加的是完整内容，画面不会因换 DAT 自动升级。画质还需要单独比较：保留弹幕/字体原色和清晰边缘，对比 balanced/native 图集及插值/FSR。已有 native 纹理模式不能直接当成高帧率默认档，应重新测后段关卡。东方优先保证弹幕辨识和操作延迟，CNN 风格作为可选实验。

### 第二步：《妖妖梦》；《永夜抄》继续审查

目前确有 [TH07 portable](https://github.com/some100/th07/tree/reallyportable)、[TH07 Switch](https://github.com/saekaze/th07-switch) 和 [TH08 原生移植](https://github.com/saekaze/th08-switch)可供研究。TH07 reallyportable 明确依赖 **SDL3、OpenGL ES 3.0+**；TH08 Switch 也使用 GLES3，并涉及数值兼容处理。因此它们不是现有固定功能 RasterIX 可直接运行的软件包。

若要求继续由 FPGA 渲染，需要把精灵/背景/混合/文字等路径映射到 RasterIX，适配宿主输入/音频，并核对 FBO、shader 与纹理要求。先做渲染接口清单和最小场景，确认能够合理降为现有后端，再决定投入全游戏移植。不能把 Switch 的 60 FPS 宣传值当成本板预计性能。

更现代的 [Taisei](https://github.com/taisei-project/taisei)提供完整免费同人游戏，但其[官方构建说明](https://github.com/taisei-project/taisei/blob/master/doc/BUILD.rst)要求 OpenGL 3.3 或 GLES3，并依赖 shader。其画面方向更现代，适配工作也更大，不作为当前快速完善游戏库的主线。

## 游戏库 UI 与配置需要补的内容

现有 UI 已有分类、封面、键鼠导航和全局返回，但还不是任意数量的插件库。目录配置、C++ 资源生成、Python 可启动 ID 白名单和启动适配器需一起更新；超过当前两排布局需增加分页/滚动和焦点保持。

建议统一记录每款游戏的 ID、作品/版本、封面、类型、安装状态、素材版本/哈希、输入说明、存档位置、命名启动适配器、硬件配置、FSR/CNN 能力及最后实测场景。启动仍使用受控适配器，不从素材目录任意拼接 shell 命令。

首页提供分类、搜索、最近游玩与收藏；详情页提供完整/体验版标识、清晰/FSR/可选风格预设和键位。缺少素材的游戏显示原因，不展示为已完成安装。显示设置继续区分 LCD 和尚未实机接通的 miniDP。

推荐执行次序：**先完善目录/分页和持久部署 → 接三款固定功能候选 → 红魔乡正式版 → 妖妖梦后端原型**。红魔乡正式版实际通关验收取决于用户提供的匹配数据；这一部分与三个开源候选的构建可以独立推进。
