# skill/tools —— 可直接运行的校验脚本

> 这是技能包的**第 ③ 类**内容（指南 3.3.5.2：「校验脚本：自动比对黄金参考、
> 检查资源与时序、验证工程可复现性的脚本」）。
>
> 三个脚本都是**独立可运行**的，不依赖本项目任何代码。
> 换一个 FPGA 项目，把它们拷过去就能用。

---

## 为什么技能包不能只有文字

`skill/README.md` 的 17 条踩坑是**经验描述**，但指南的评价标准是「可复用性」：

> 「一支陌生队伍拿到该目录，**能否直接用在自己的题目上**」

**一段能被 `python3 xxx.py` 直接跑起来的代码，比十段解释更有说服力。**
而且脚本可以**验证自己**——这是文字做不到的。

---

## 三个脚本

### S1　`numeric_compare.py` —— 数值逐位比对器

**对应踩坑**：P10（浮点重排会改变结果，必须量化）

**解决什么**：判断「数学上等价」的改动是否真的**逐位等价**。

```bash
python3 numeric_compare.py old.bin new.bin --dtype float32 --shape 11520,3
```

输出：

```
元素数      : 34560
逐位不同    : 16270  (47.08%)
最大绝对差  : 3.5762786865e-07
最大 ULP 差 : 1144
首个不同    : index=7  old=1.25  new=1.250000119
VERDICT: DIFFERENT
```

**判据**：`VERDICT` 为 `IDENTICAL` 时退出码 0，`DIFFERENT` 时退出码 1，可直接接 CI。

**为什么最大值不够**：本项目实测 MVP 预乘的**最大绝对差只有 3.58e-7**（看起来可忽略），
但 **47.08% 的字段逐位不同，最大 ULP 差 1,144**。若下游要定点化或做深度比较，这就是缺陷。

**自测过**：相同输入 → `IDENTICAL` / exit 0；差 1 ULP → `DIFFERENT` / exit 1。

---

### S2　`check_route_report.py` —— 布线报告检查器

**对应踩坑**：P1（OOC 面积不能直接相加）、P3（布局失败时任何时序数字都不存在）

**解决什么**：从 Vivado 报告里判定「这份数据能不能作为最终结论」。

```bash
python3 check_route_report.py --util utilization.rpt --log implement.log
```

真实输出（本项目 125 MHz 工程）：

```
== 资源（routed）==
  LUT      64033.0 / 70560.0     90.75%
  FF       67501.0 / 141120.0    47.83%
  BRAM       177.5 / 216.0       82.18%
  DSP        347.0 / 360.0       96.39%
== 实现日志 ==
  位流已生成 : 是
  WNS        : 0.258 ns
  WHS        : 0.011 ns

VERDICT: PASS
```

**它会做的三件事**：

1. 从 `Design State` 行判定阶段（`Synthesized` / `Placed` / `Routed`）
2. **阶段不是 `Routed` 就拒绝给结论**，退出码 2
3. 校验每条时钟的 WNS / WHS / 失败端点数，任一为负即 FAIL

**自测过**：对真实 `java256-fold16-split-125` 工程解析出 64,033 LUT / 347 DSP /
177.5 BRAM，`VERDICT: PASS`，与人工核对一致。

**注意一个实现细节**：Vivado 的 utilization 表格列数不固定（有 Dedicated / Programmable /
Available / Util% 四段），用正则贪婪匹配会抓错列。本脚本**按 `|` 分列后从右往左取 Total 与 Pct**，
这是踩过一次坑才写对的。

---

### S3　`acceptance_with_negative_control.py` —— 带强制负对照的验收器

**对应踩坑**：P14（验收脚本本身会是最大的假失败源）

**解决什么**：**保证「通过」这个结论本身是可信的。**

```bash
python3 acceptance_with_negative_control.py --reference golden.bin --actual new.bin
```

输出：

```
参考文件     : golden.bin  (2248320 字节)
实际文件     : new.bin     (2248320 字节)
负对照       : 通过（验证器能检出错误）
逐字节一致   : 是

VERDICT: PASS（含有效负对照）
```

**核心机制**：在比对真实数据**之前**，先对参考数据的副本做三种人工破坏——

1. 翻一个字节
2. 截断一半
3. 末尾追加一字节

**三种都必须被检出**，否则脚本输出：

```
VERDICT: INCONCLUSIVE —— 验证器本身无效，不能给出通过结论
exit 3
```

**为什么这个最重要**：本项目的 CNN 存储复用验证了 **93 个用例、279 层输出零差异**。
但「零差异」不说明验证器有效——**验证器可能永远返回通过**。
所以另外做了一个「故意提前覆盖同一行」的负对照，验证器抓到 **85 个通道值差异**，
这才证明前一个结论成立。

**自测过**：一致输入 → `PASS` / exit 0；差 1 字节 → `FAIL` / exit 1，且两种情况下负对照都通过。

---

## 作为库使用

三个脚本都可以直接 import：

```python
import sys
sys.path.insert(0, 'skill/tools')

from numeric_compare import load, ulp_diff
from acceptance_with_negative_control import acceptance

ref = open('golden.bin', 'rb').read()
act = open('new.bin', 'rb').read()
r = acceptance(ref, act)          # 默认强制负对照
assert r['negative_control_ok'], '验收器无效，结论不可信'
print(r['ok'], r['detail'])
```

`check_route_report.py` 的 `parse_util()` / `parse_timing()` / `parse_log()` 也可以单独调用。

---

## 三个脚本的边界（诚实说明）

| 脚本 | 能做什么 | 不能做什么 |
|---|---|---|
| `numeric_compare.py` | 二进制数组的逐位/ULP 比较 | 不理解结构体布局，需要调用方给对 `--dtype` 与元素数 |
| `check_route_report.py` | 解析标准 Vivado 报告格式 | 不解析自定义格式；版本升级改了表头就需同步改 |
| `acceptance_with_negative_control.py` | 逐字节比较 + 三种破坏的负对照 | 只做字节级；语义级验收（如「图像是否视觉正确」）需另写检查器并接入同一负对照框架 |

**三个脚本都只依赖 Python 3 标准库**（`argparse` / `struct` / `re` / `os` / `sys`），
无需 numpy，拷到任何环境都能跑。

---

## 与本项目证据的对应

| 脚本 | 本项目里的实际用途 | 证据 |
|---|---|---|
| `numeric_compare.py` | MVP 矩阵预乘的 ULP 探针 | `docs/` MVP 探针表（47.08% / 1,144 ULP） |
| `check_route_report.py` | 判定 120/125 MHz 工程是否真的布线通过 | `build/java256-fold16-split-125/utilization.rpt` |
| `acceptance_with_negative_control.py` | CNN 原地复用的 93 用例 + 85 差异负对照 | `docs/` CNN 存储复用记录 |
