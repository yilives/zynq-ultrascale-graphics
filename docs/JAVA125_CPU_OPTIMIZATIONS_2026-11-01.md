# Java 1.2.5 CPU 优化验证记录

日期：2026-11-01

范围：仅检查 ARM 侧几何前端与命令准备；没有修改 RTL、位流、FSR/CNN、`build/minecraft-java-125/dual-tmu/`、Java ABI、内存池、纹理/TMU 配置或 `Rasterizer::increment`。

## 结论

| 优化 | 源码处理 | 结论 |
|---|---|---|
| MVP 预合并 | 未保留改动；`VertexTransformer.hpp` 维持原变换链 | **不采用**。变换字段探针发现大量逐位差异，且无法运行编译后的整套几何回归确认字节级输出。 |
| `View` 指针视图 | 已改为指针与长度，空属性由长度判断 | **保留源码改动**。语义按原逻辑实现；编译与板端收益没有验证。 |
| 输出引用与右值提交 | `at()` 写入调用方对象；增加右值 `pushVertex` 和命令构造 | **保留源码改动**。预期移除一份参数复制；编译与板端收益没有验证。 |

## 1. MVP 合并：不采用

当前 `Mat44::transform` 按行向量计算。先执行 modelView、再执行 projection 时，数学上的合成顺序应为 `modelView * projection`；按需求文字中的 `projection * modelView` 会倒置顺序。即使使用正确顺序，矩阵先合并再变换也会改变浮点运算分组。

用现有几何夹具的确定性输入做了 binary32 探针：重放 96 draws、每 draw 120 次提交，并对比原先的 `projection.transform(modelView.transform(v))` 与 `transform(v, modelView * projection)`。探针在每次乘法和加法后舍入到 float32，结果如下：

| 指标 | 结果 |
|---|---:|
| 被比较的变换坐标字段 | 46,080 |
| 逐位不同字段 | 21,696（47.08%） |
| 至少有一项不同的顶点 | 10,683 / 11,520 |
| 最大绝对差 | `3.5762786865234375e-7` |
| 最大 ULP 差 | 1,144 |

探针脚本为 [mvp_float_probe.py](../tmp/mvp_float_probe.py)。它是按夹具和 float32 运算顺序实现的软件探针，不是目标 C++ 编译器的执行结果，也不等价于最终三角形流回归。鉴于严格字节比较尚未通过，而且这里已经出现大量中间坐标逐位变化，本轮不把 MVP 变换写入运行源码。

代码约定依据：`external/RasterIX/lib/gl/math/Mat44.hpp` 的 `transform` 计算 `src * mat`；现有逻辑在 [VertexTransformer.hpp](../external/RasterIX/lib/gl/transform/VertexTransformer.hpp) 先执行 modelView，再执行 projection。该文件保留原实现。

## 2. `java_prepared::View`：保留源码改动

[java_prepared_arrays.hpp](../ports/java_prepared_arrays.hpp) 中，`View` 的五组数组现在只保存 `const T*` 与 `std::size_t`。`empty()` 检查长度，访问使用指针下标；常量属性回退和索引语义保持原样。`View` 仍不拥有数组，原有 `OwnedBatch` 所有权约束继续负责指针生命周期。

## 3. 输出引用与右值提交：保留源码改动

[java_prepared_arrays.hpp](../ports/java_prepared_arrays.hpp) 的 `at(i, value)` 现在直接填充调用方提供的 `VertexParameter`。 [Renderer.hpp](../external/RasterIX/lib/gl/renderer/Renderer.hpp) 增加 `pushVertex(VertexParameter&&)` 路径；[DataTransferCmdBase.hpp](../external/RasterIX/lib/gl/renderer/commands/DataTransferCmdBase.hpp) 增加右值构造，并将参数移动到命令缓冲。原有 `const&` 入口保留给其他调用者。

当前源码搜索没有找到 `View::at` 的生产调用点，因此实际调用方仍需采用“创建局部参数、`at(i, value)` 填充、`pushVertex(std::move(value))` 提交”的新接口，才能获得这条路径的复制消除。该调用链没有经过本机编译验证。

## 几何回归证据

工作区内**已有的基线产物**一致：96 draws、11,520 vertices、11,710 triangles、2,248,320 bytes。`geometry-reference.bin`、`geometry-mode0.bin`、`geometry-mode1.bin` 三份既有文件逐字节相同，SHA-256 为：

`cf6827033e79ba094bd7d55b45d66d1d00cd9d46193c8c7f74b64033753274c0`

这些是既有参考文件，不是本轮改动后的重建结果。本轮没有拿到编译后输出字节数或 SHA，因此不能声称本轮几何回归通过。

## CPU 采样

本轮没有运行板端采样。当前会话明确限制上电、串口、写卡与 FPGA manager 操作；本机没有可用的 C++ 编译器，WSL 启动返回 `E_ACCESSDENIED`，无法构建本轮版本并部署到同一 Tiny 静止场景。没有生成“优化后”CPU 数据，也不据此声称 CPU 占比下降。

历史 R85 样本（2 ms 周期，7,845 个样本；不是本轮同场景的前后对照）供参考：

| 符号 | R85 占比 | 本轮优化后 |
|---|---:|---|
| `rr::Mat44::transform` | 12.04% | 未采样 |
| `rr::Vec<4>::operator=(const&)` | 11.39% | 未采样 |
| `java_prepared::View::at` | 7.63% | 未采样 |
| `rr::Vec<4>::operator=(const&&)` | 4.89% | 未采样 |

## 本轮可复核检查

- 运行了 float32 MVP 探针，记录逐位差异与最大绝对差。
- 检查了既有基线几何文件的长度、SHA 与三份文件逐字节一致性。
- 对 `View` 输出引用、指针视图字段、`Renderer` 右值入口和命令右值构造做了源码结构断言。
- 未运行 C++ 编译、编译后的几何回归或优化后 CPU 采样；原因如上。
