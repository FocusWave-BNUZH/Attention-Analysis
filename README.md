# Attention-Analysis｜NVIDIA近红外第8版生产入口

2026-10-13入口定位核验。当前分支为 `nvidia-cuda-v8`，负责NVIDIA近红外最终全类别分割与测量生产层。根目录此前沿用AMD说明模板；当前硬件/运行事实以本分支的运行包、配置和代码为准。

## 当前读取入口

- [运行包与最终输出契约](runtime/nir-formal/README.md)
- [NVIDIA安装、模型与执行后端检查](runtime/nir-formal/INSTALL.md)
- [完整全类别扩展契约](runtime/nir-formal/RITNET_FULLCLASS_EXTENSION.md)
- [CUDA执行性能记录](runtime/nir-formal/CUDA_PERFORMANCE_NOTES.md)

NVIDIA并行计算平台（Compute Unified Device Architecture [CUDA]）执行由 `cuda_runtime.py` 与 `ritnet_fullclass_final_runtime.py` 实现。配置声明NVIDIA执行目的；第8版恢复清单记录执行后端/提供者，不能静默接续AMD恢复数据库。源码主体与AMD第8版来源相关，跨硬件真实数据等价性仍须按现有契约检验，文档定位纠正不替代实机验收。

最终生产入口为 `runtime/nir-formal/run_ritnet_fullclass_batch.py` 和单次扩展入口；读取既有初始生产的眼框、帧表和完成清单，依据原始近红外视频执行最终测量。参数、模型、安装和恢复细节集中在上述运行包说明，不在根目录另复制一套操作手册。

## 仓库角色

正式下游行为、眼部、动作与监督学习分析继续从 [当前默认分支](https://github.com/kyandi233-dev/Attention-Analysis/tree/codex/formal-analysis-v2-portable) 的根入口读取；方法、结果和正式报告以 [正式分析仓库当前主线](https://github.com/kyandi233-dev/FocusWave-Formal-Analysis/tree/main) 为准。本硬件分支不替代这些入口。

旧 `nvidia-cuda` 保存初始生产、旧环境及恢复程序来源。AMD硬件使用 `amd-DirectML`；本分支不执行根目录旧模板中的AMD切换命令或机器路径。

## 本次变更边界

本次只纠正根入口及分支导航事实，旧根说明保留于本分支提交历史。执行代码、模型、配置、参数、数据、恢复数据库和输出不变；未重跑研究数据。

## 2026-10-14 分支与历史版本入口

[当前活动分支、完整历史版本及执行证据](https://github.com/kyandi233-dev/Attention-Analysis/blob/codex/formal-analysis-v2-portable/docs/060-formal-analysis/020-分支收敛与环境剥离执行_20261014.md)。旧版本按精确固定版本恢复；本分支执行代码、模型和配置不变。
