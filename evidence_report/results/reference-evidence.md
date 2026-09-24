# 参考校正证据说明

**用途：合成研究复核。不支持工程放行。**

快照摘要：`01baed21bc3979a858f6b207bbf3fa359f15e1562de3862aacd14e18dcb380f5`
核对文件：303；分支：32。
哈希一致不等于参考真实、物理有效或计量溯源；本命令没有重跑求解器。

## 仍缺少的证据

- `reference_traceability_and_systematic_error_bound`
- `independent_thermal_equilibrium_evidence`
- `correction_valid_temperature_range_and_expiry`
- `temperature_dependent_drift_bound`
- `hardware_validation`

## 可观测复核（不使用隐藏真值）

|编号|分支|拟合收敛|残差告警|建议|
|---|---|---|---|---|
|case-001|raw|True|False|复核参考及适用条件，不放行|
|case-002|corrected|True|False|复核参考及适用条件，不放行|
|case-003|raw|True|True|复核参考及适用条件，不放行|
|case-004|corrected|True|False|复核参考及适用条件，不放行|
|case-005|raw|True|True|复核参考及适用条件，不放行|
|case-006|corrected|True|False|复核参考及适用条件，不放行|
|case-007|raw|True|True|复核参考及适用条件，不放行|
|case-008|corrected|True|False|复核参考及适用条件，不放行|
|case-009|raw|True|False|复核参考及适用条件，不放行|
|case-010|corrected|True|False|复核参考及适用条件，不放行|
|case-011|raw|True|True|复核参考及适用条件，不放行|
|case-012|corrected|True|False|复核参考及适用条件，不放行|
|case-013|raw|True|True|复核参考及适用条件，不放行|
|case-014|corrected|True|False|复核参考及适用条件，不放行|
|case-015|raw|True|True|复核参考及适用条件，不放行|
|case-016|corrected|True|False|复核参考及适用条件，不放行|
|case-017|raw|True|False|复核参考及适用条件，不放行|
|case-018|corrected|True|False|复核参考及适用条件，不放行|
|case-019|raw|True|False|复核参考及适用条件，不放行|
|case-020|corrected|True|False|复核参考及适用条件，不放行|
|case-021|raw|True|False|复核参考及适用条件，不放行|
|case-022|corrected|True|False|复核参考及适用条件，不放行|
|case-023|raw|True|False|复核参考及适用条件，不放行|
|case-024|corrected|True|False|复核参考及适用条件，不放行|
|case-025|raw|True|False|复核参考及适用条件，不放行|
|case-026|corrected|True|False|复核参考及适用条件，不放行|
|case-027|raw|True|True|复核参考及适用条件，不放行|
|case-028|corrected|True|False|复核参考及适用条件，不放行|
|case-029|raw|True|True|复核参考及适用条件，不放行|
|case-030|corrected|True|False|复核参考及适用条件，不放行|
|case-031|raw|True|False|复核参考及适用条件，不放行|
|case-032|corrected|True|False|复核参考及适用条件，不放行|

均值标准误差仅描述随机采样精度，不含参考系统误差或漂移。

## 回顾性评价（仅仿真端可知）

本节含隐藏真值，不能作为现场诊断功能。跨分支共享对象与观测，不是独立设备样本。

|编号|合成情形|隐藏场RMSE K|预测不足|残差漏报|
|---|---|---:|---|---|
|case-001|clean|0.011527|False|False|
|case-002|clean|0.037184|False|False|
|case-003|stable|0.659205|True|False|
|case-004|stable|0.037184|False|False|
|case-005|reference_bias|0.659205|True|False|
|case-006|reference_bias|0.602454|True|True|
|case-007|thermal_drift|0.955914|True|False|
|case-008|thermal_drift|0.324204|False|False|
|case-009|clean|0.016644|False|False|
|case-010|clean|0.020089|False|False|
|case-011|stable|0.679366|True|False|
|case-012|stable|0.020089|False|False|
|case-013|reference_bias|0.679366|True|False|
|case-014|reference_bias|0.593123|True|True|
|case-015|thermal_drift|0.976152|True|False|
|case-016|thermal_drift|0.319569|False|False|
|case-017|clean|0.014842|False|False|
|case-018|clean|0.098904|False|False|
|case-019|stable|0.669806|True|True|
|case-020|stable|0.098904|False|False|
|case-021|reference_bias|0.669806|True|True|
|case-022|reference_bias|0.503095|True|True|
|case-023|thermal_drift|0.352798|False|False|
|case-024|thermal_drift|0.268820|False|False|
|case-025|clean|0.005139|False|False|
|case-026|clean|0.025031|False|False|
|case-027|stable|0.656261|True|False|
|case-028|stable|0.025031|False|False|
|case-029|reference_bias|0.656261|True|False|
|case-030|reference_bias|0.560694|True|True|
|case-031|thermal_drift|0.338896|False|False|
|case-032|thermal_drift|0.327752|False|False|
