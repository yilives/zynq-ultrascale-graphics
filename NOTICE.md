# NOTICE —— 第三方组件与许可声明

> 本作品链接上游 RasterIX（GPLv3），因此**整体按 GPLv3 分发**。
> 根目录 `LICENSE` 是 GPLv3 全文；本条文件只列出各组件的来源与许可。

---

## 一、按 GPLv3 分发的部分

| 组件 | 来源 | 许可 | 位置 |
|---|---|---|---|
| RasterIX | `https://github.com/Xilinx/RasterIX`，固定提交 `9269a01c9bd4c3342bfa70ef8e3cdd751c15c6d0` | **GPLv3** | `external/rasterix/`、`LICENSE` |
| RasterIX 的板级改动 | 本项目（28 个文件） | GPLv3（衍生作品） | `external/rasterix/0001-board-ports.patch` |
| ARM 侧 GL 端口补丁 | 本项目（47 个文件） | GPLv3（链接 RasterIX） | `ports/` |

**为什么整体是 GPLv3**：本作品的板级 RTL 与 ARM 侧补丁与 RasterIX 构成一个可执行整体，
按 GPLv3 的传染性，分发该整体时须整体遵循 GPLv3。

---

## 二、按各自许可分发的部分

| 组件 | 来源 | 许可 | 位置 |
|---|---|---|---|
| FidelityFX FSR1（EASU + RCAS 算法） | AMD, 2021 | AMD 自定义 MIT 式许可，全文见 `src/hls/fsr1/LICENSE.FSR1.txt` | `src/hls/fsr1/` |
| tuxracer / tuxracer-data | 上游 Tux Racer 项目 | GPLv2 | 未随包分发（运行时外部引入） |
| SDL2 | `https://github.com/libsdl-org/SDL` | zlib 许可 | 未随包分发 |
| gl4es | 上游 gl4es | MIT | 未随包分发 |
| classicube | 上游 ClassiCube | 自定义（非商用） | 未随包分发 |
| th06（东方红魔乡引擎） | 上游开源复刻 | 各自许可 | `ports/th06/` 仅含适配代码 |
| Quake / Quake III | id Software，GPLv2 | GPLv2 | 未随包分发 |

**说明**：游戏本体与大型第三方库（SDL2、gl4es、Mesa、vendor 树）**未随包分发**，
以保持提交包体积可控且不违反各自许可。构建时由脚本从固定源拉取。

---

## 三、本项目原创的部分

| 内容 | 位置 | 说明 |
|---|---|---|
| 板级 RTL（23 个 .v/.sv） | `src/rtl/` | 帧桥、CSR、呈现握手、缩放、三域复位、CNN 引擎与 AXI |
| 板级顶层（2 个） | `src/board/` | `axu3eg_rasterix_top.v` 等 |
| PS 侧 C++（7 个） | `src/ps/` | DMA 连接器、呈现器、性能采样 |
| 超分 HLS（50 个文件） | `src/hls/fsr1/` | 行流式 EASU/RCAS 的定点实现 |
| ARM 侧 GL 端口（47 个文件） | `ports/` | 几何前端、显示列表、纹理页、重放设备 |
| 六款小游戏规则 | `ports/arcade/rules.hpp` | 贪吃蛇、落块消行、打砖块、2048、推箱子、扫雷 |
| CNN 存储调度与权重 | `src/rtl/neural/`、`data/models/` | 3→8→8→3 / 160×96 / INT8 / 1,027 参数 |
| 板测事务与隔离机制 | `board/runtime/` | 三锁、隔离守卫、回滚包 |
| 证据文档（107 篇） | `docs/` | 均带 `path:line` 引用 |
| 配图脚本 | 主仓库 `scripts/build_amd_fig*.py` | 7 张图可完整重建 |

**原创部分同样以 GPLv3 发布**，以便与 RasterIX 整体一致。

---

## 四、上游版权声明保留情况

- `external/rasterix/LICENSE` —— RasterIX 原始 GPLv3 全文，未修改
- `src/hls/fsr1/LICENSE.FSR1.txt` —— AMD FSR1 原始许可全文，未修改
- 各源码文件头部的原始版权注释**均保留**，未删除、未替换

---

## 五、若要重新分发

1. 保留根目录 `LICENSE`（GPLv3）
2. 保留 `external/rasterix/LICENSE` 与 `src/hls/fsr1/LICENSE.FSR1.txt`
3. 保留各源文件的原始版权头
4. 修改过的文件需注明修改（本包通过 `0001-board-ports.patch` 显式标注全部 28 处改动）
5. 提供完整对应源码（本包已包含）
