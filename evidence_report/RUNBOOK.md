# 只读证据报告的运行与边界

该命令是第七阶段固定数据格式的报告适配器，不是通用证书验证器，不接受真实设备安全批准。报告中的“完整性通过”只表示与调用者指定快照一致。

## 生成现有实验报告

在本目录运行：

```sh
../feasibility/.venv/bin/python report.py \
  --stage ../reference_correction \
  --manifest-sha256 01baed21bc3979a858f6b207bbf3fa359f15e1562de3862aacd14e18dcb380f5 \
  > results/reference-evidence.json

../feasibility/.venv/bin/python report.py \
  --stage ../reference_correction \
  --manifest-sha256 01baed21bc3979a858f6b207bbf3fa359f15e1562de3862aacd14e18dcb380f5 \
  --format markdown > results/reference-evidence.md
```

清单摘要为本轮核对的旧实验快照，必须从可信的独立记录确认；不要为了绕过错误直接计算篡改后的清单摘要传进去。如果明确重新运行旧实验，需先审查新产物并更新快照记录。工具不提供签名和身份认证，无法对抗同时替换所有数据及确认摘要的行为。

命令只向stdout输出报告，失败向stderr输出原因并返回2，不修改stage目录。shell重定向可能在失败时留下空文件，自动化使用时应检查退出码，不能只看输出文件存在。输入不是任意互联网归档，不解压到文件系统；本命令没有资源配额或恶意压缩包隔离。

## 测试

```sh
set -o pipefail
../feasibility/.venv/bin/python -m unittest discover -s . -p 'test_*.py' -v \
  2>&1 | tee results/tests.log
```

测试使用真实第七阶段快照，并在临时目录副本中验证篡改/缺失/危险路径/错误数字/矛盾结论被拒绝。不会修改旧实验或发起新的仿真。源码的验证不使用assert作为运行门禁，在`python -O`下依旧执行。

## 报告语义

- `integrity`：清单303个文件及config引用的依赖哈希。不是作者身份、计量溯源或物理有效性证明。
- `validation_scope.performed`：本次实际重算的数组和判定范围。
- `validation_scope.source_verifier_reported_status`：旧检查器保存的状态，只标为来源自报，不冒充本命令重新执行全部数值验证。
- `observable_review`：已观测残差、拟合状态、参考样本及随机SE，无场景标签或隐藏真值。
- `retrospective_evaluation`：明确仿真回顾，保存场景、真实评分及漏报。编号可与可观测报告关联，但本区不参与建议生成。
- `missing_evidence`：本阶段没有提供参考溯源/系统误差界、独立均温证据、温区/有效期、漂移界和硬件验证。
- `engineering_release=not_supported`：始终不能用于放行。不会因为拟合成功、无告警、SE小或隐藏误差为0而改变。

## 当前缺口

工具只重算保存的offset、残差判定及场评分，不执行ODE、拟合或独立求解器，不重建全部噪声/能量检查。要复现完整科学实验，仍需运行reference_correction的原检查器和按协议重跑。

没有声称支持接收或鉴定真实校准证书，也未规定证书适用范围或系统误差界。未知证据不得由一个用户填入的“已验证”布尔值替代。未来如接入新的实验格式、真实参考文件或工程审查，须明确可核验字段和审查责任，而不是添加自动safe状态。
