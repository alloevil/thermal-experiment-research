# 三层协同研究工作流

流程状态：`pending_review`
提案标识：`4300066f348cca57c58f7bfb3d7d4ab7da64d4e6fbc633baa85cd9adbd68c14e`

A：有限网格信息增益试验选择；B：既有热方程模型；C：确定性工具编排与显式审核。
未调用 LLM、未训练代理模型、未执行真实设备命令。

## 工具事件

- 1. `ExperimentBank.recommend` → `experiment_recommended`

## 原始提案

# 下一次试验建议

状态：`experiment_recommended`

Highest estimated model-label information among enabled budget-feasible experiments; estimate is not a performance guarantee.

## 当前候选支持（不是根因确认）

- convection: 51.161%
- offset: 48.839%

## 建议：heat_high

预期信息增益 0.4990 nat；蒙特卡洛标准误差 0.0240。
声明成本 1 单位；噪声假设 σ=0.25 K。
有限参数网格与离散时间预测最高温度：362.5937344187673 K（不是连续或实物安全保证）。

每次从 296.15K 均温重新开始；以下为声明的吸收功率指令，非设备控制命令。

|时刻 s|三区功率 W|
|---|---|
|0|[0, 0, 0]|
|45|[0.5, 0.5, 0.5]|
|180|[0.5, 0.5, 0.5]|

|观测|时间 s|位置 m|散热解释均值/5–95% K|零偏解释均值/5–95% K|
|---|---|---|---|---|
|1|90|0.03|330.809 / [329.485, 332.137]|332.297 / [330.790, 333.878]|
|2|135|0.03|342.546 / [339.827, 345.776]|346.033 / [343.975, 347.934]|
|3|180|0.03|349.224 / [345.370, 354.309]|354.435 / [352.115, 356.926]|

按标准化预测分离度最值得关注的是第 3 个观测；不要只读取这一点更新，其余测量同样要保留。

## 限制

区间来自有限参数后验和测量噪声的模拟，不是经实物校准的置信界。
- Each experiment restarts from independently confirmed 296.15K equilibrium.
- User must approve inputs and instrument/reference validity; modeled constraints are not safety clearance.
- Finite-grid predictions and assumed independent noise may be wrong; other causes are not excluded.
- 不支持工程放行，不自动执行试验。

## 工作流边界

提案摘要只检测不一致，不是签名或访问控制。预算只记本条结果链的新实验，不是全局账本。
旧审核快照另开输出分支不会被全局去重；操作者必须避免重复记录同一次物理实验。
所有状态 engineering_release=not_supported。
