# 多游戏供帧与 CNN/FSR 优化

当前结论和逐游戏实测见 [2026-11-02 报告](../../docs/MULTIGAME_OPTIMIZATION_2026-11-02.md)。本目录保留经过实机运行的源码；执行版本的字节与归档索引分别校验。

- `multi_game_r4.py`：七游戏源供帧 ABBA、CNN/FSR ABBA、实际输出回读。历史首轮 Quake 停在菜单、Neverball 停在关卡介绍页；补测独立保留，不能把首轮数字当作这两个游戏的关卡帧率。
- `native_validation_r4.py`：在原 v23 上通过真实菜单播放器验证 Neverball async 和 Quake III 60 FPS 上限；只有通过后才保留新 `game_specs.py`，失败正常回退。
- `cfs_games_play.py`、`multigame_play_r4_tasks.py`：七游戏独立 CNN/FSR 入口，按策略选择早提交或提前通知版本，正常退出游戏、恢复原 FPGA 和清晰菜单。
- `multigame-play-r4-policy.json`、`multigame-play-r4-index.json`：经过检查的逐游戏策略和源码身份。

普通菜单供帧改动位于 `../launcher/game_specs.py`。普通菜单风格开关没有自动指向本实验；Minecraft Java 保留自己的双 TMU 配置。

已有本轮验证环境时，在板端执行：

```sh
python3 -B /tmp/rix-cnn-group-r1/cfs_games_play.py --game quake --style oil --seconds 30
python3 -B /tmp/rix-cnn-group-r1/cfs_games_play.py --game neverputt --style comic --seconds 30
```

可选游戏：`tuxracer neverball neverputt quake quake3 touhou classicube`；可选风格：`comic oil both`。`--upscaler pl-fsr` 为默认值；`bilinear` 用于比较。正常入口关闭测试自动操控，键鼠/触摸维持现有引擎设置。

入口依赖本轮 RAM stage 内的冻结加载器、已验证的 NGR1/原位流、模型、两套运行时、既有素材和原生菜单；不是可单文件拷贝运行的安装包。完整产物在 `build/multigame-opt-r4/`，证据在 `report/multigame-opt-20261102/`。RAM stage 重启后需要按项目既有部署流程恢复，未写入新的 SD 启动镜像。

复核入口：`scripts/accept_multigame_opt_r4.py`、`scripts/accept_quake_gameplay_r4b.py`、`scripts/accept_neverball_gameplay_r4c.py`、`scripts/accept_multigame_final_r4.py`。前几项会重算整数 CNN、融合与固定点 FSR；最后一项检查普通菜单实际采用的源码、逐游戏策略、恢复状态和启动文件哈希。执行生成脚本会创建新的独立目录，已存在的历史归档不应覆盖。

本轮没有更换模型或修改 RTL；动态场景的短窗口吞吐不等于完整游戏稳定帧率。CNN 处理/呈现次数也不能替代源游戏唯一帧数。
