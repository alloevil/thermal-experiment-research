# 半导体热处理场景的开放多保真优化：立项前调研

调研日期：2026-09-24。结论性质：公开资料可行性筛查，不是完整系统综述、算法复现实验或企业需求验证。

## 一、结论先行

**有条件推进一个小型研究案例，但不建议直接建设此前设想的通用 ChamberBench 平台。**

“热方程 + AI 控制”“多保真优化 + 求解器 API”“热预测 + 跨工况泛化”分别已有公开工作。可以继续验证的候选问题是：

> 在具有明确功率、超调和温差约束的公开加热任务中，当低保真模型存在可解释的偏差时，多保真优化是否仍值得使用？把模型构建、优化器开销和最终复核计入后，它在哪些条件下节约或浪费计算预算？

这是**待验证的选题假设**，不能表述为已确认的学术空白。其价值可能首先来自可信算例、公平评测与负结果，而不是新算法。

建议先做“一个物理问题 + 现成算法 + 可复算证据”，再决定是否成长为独立基准。不要先开发聊天界面、通用 Agent、排行榜或云平台。没有企业入口时，第一批潜在使用者应是优化、控制和科学计算研究者，而不是假设北方华创会采购。

## 二、范围、方法与证据等级

- 前提：目前无法接触北方华创，不使用其图纸、工艺配方、私有日志、客户数据或设备。
- 公司公开产品仅说明场景关联：RTP 强调升温与温度均匀性；CVD 页面涉及高温控制、气流场与温度场仿真。[S01–S02]
- 检索渠道：GitHub 仓库搜索及原始文件、OpenAlex、Crossref、arXiv、期刊网站、项目官方文档。
- 检索关键词包括 `multi fidelity benchmark`、`PDE control benchmark`、`rapid thermal processing control`、`heat transfer multi-fidelity`、`thermal benchmark` 等。主要检索查询和返回结果保存在本目录 JSON 文件中。
- GitHub 每次搜索仅取前 6–7 项，学术检索也使用有限结果窗口；宽泛搜索出现大量不相关结果。因此“本轮未发现”不代表不存在，尤其不能由零条 GitHub 命中推导市场空白。
- 证据等级：**原文**指已读取论文正文相关章节；**一手文档**指作者仓库或官方文档自述；**索引摘要**指已核对 DOI、标题或索引中的摘要，但未读到论文正文。
- 所有性能数字均为明确标注的来源自报；本轮没有运行控制、优化或神经网络性能实验。

### 本轮明确未完成的验证

1. 企业实际痛点、已有工具、采购意愿和数据授权。
2. 开源求解器安装、算例运行与复算耗时。
3. RTP 物理参数的完整公开来源及复用许可。
4. 拟议模型与真实热处理设备的物理验证。
5. 新问题相对全部现有工作的学术新颖性。

## 三、最重要的发现：经典方法不能被忽略

### 3.1 RTP 温控并不是新出现的问题

下列工作已能确认这条技术路线的长期积累；除特别说明外，本轮仅核查索引元数据或摘要，不能据此复现其设备或接受其全部实验结论。

| 年份 | 工作 | 核实到的内容 | 对我们意味着什么 |
|---|---|---|---|
| 1993 | *A Model Predictive Controller for Multivariable Temperature Control in Rapid Thermal Processing* | Crossref 标题、作者、年份、DOI。[S03] | “把 MPC 用于 RTP”不是新的切入点。 |
| 1994 | *Modeling, Identification, and Control of Rapid Thermal Processing Systems* | 索引摘要描述物理建模、实验辨识、IMC、前馈与增益调度。[S04] | 不能跳过辨识和物理模型，直接以黑箱 AI 对比弱基线。 |
| 1997 | *Control of rapid thermal processing: a system theoretic approach* | 索引摘要包含子空间辨识、凸优化轨迹设计、执行器约束和 LQG。[S05] | 轨迹优化、约束和反馈的组合也已有先例。 |
| 2001 | *Control of Wafer Temperature Uniformity in Rapid Thermal Processing Using an Optimal Iterative Learning Control Technique* | 摘要描述时变模型、Kalman 滤波、跨运行学习与仿真。[S06] | “从上一轮试验学习下一轮输入”不应当直接称为新的 AI 方法。 |
| 2003 | *Experimental application of a quadratic optimal iterative learning control method...* | 摘要描述 8 英寸晶圆、3 处测温、3 组灯及 10 轮实验学习。[S07] | 若主张跨批次调参价值，必须考虑迭代学习控制（ILC）。数字仅为该摘要中的实验设置。 |

1994 年论文的期刊入口返回 HTTP 200，但实际内容是验证码页，不是正文；证据清单将它标为不可用内容。该论文引用依据仍然只是索引摘要，不得标注“已读全文”。

### 3.2 已有 PDE 控制基准提醒我们：AI 不天然占优

PDE Control Gym 的论文已提供 1D 输运、1D 反应扩散、2D Navier–Stokes 三类环境，并包含经典方法与 PPO/SAC 的比较。[S08]

论文 v1 表 3 在每类环境 50 个测试 episode 上报告的平均回报如下，数值越大越好：

| 方法 | 1D 输运 | 1D 反应扩散 | 2D Navier–Stokes |
|---|---:|---:|---:|
| Model-based | 246.3 | 299.1 | -7.931 |
| PPO | 172.3 | 293.3 | -5.370 |
| SAC | 184.2 | 229.1 | -17.829 |

这是作者在其协议下的结果，不是本轮复测；不同 PDE 的奖励不能相互比较，模型已知的经典方法与 model-free 方法的信息条件也不同。该表只支持“不能预先假定 RL 必胜”，不支持对所有工程问题排算法名次。仓库还明确说明当前奖励函数已较论文修改，重现论文结果必须锁定对应版本。

## 四、现有基准：哪些直接重叠，哪些只是邻近

| 工作 | 已有能力与事实 | 可以复用 | 不能直接适配的部分 |
|---|---|---|---|
| **PDE Control Gym** [S08] | 3 类 PDE，边界控制、可配置观测、经典控制与 RL 示例 | 控制环境接口、基线与数值说明 | 不等于辐射加热腔体；需要另建热处理任务与约束。 |
| **ControlGym** [S09] | 作者列出 36 个工业线性控制环境、10 个 PDE 环境；论文 PDE 部分使用周期边界与分布式输入 | 稳定性和可扩展性评测组织方式 | 周期边界不能直接代表实际晶圆边缘和腔壁边界。 |
| **MF2** [S10] | 常见多保真测试函数，NumPy 依赖；GPL-3.0 | 优化器接口冒烟与算法校验 | 解析函数没有真实求解器耗时、热物理和工程约束。 |
| **Flow Reactor Design Benchmark** [S11] | Docker + Flask + REST，6 类任务，11–50 个设计变量、2 个 fidelity 参数；作者说明低保真存在系统偏差 | 容器化工程黑箱的交付方式 | 流动反应器，不是热处理；README 提示未适配 Apple Silicon。 |
| **UM-Bridge** [S12] | 跨语言数值模型接口、容器化模型库、可选导数；包含 Heat1D 反问题与 L2-Sea 优化 | 模型接入协议，避免另造通用求解器 API | 接口不解决物理正确性、访问授权或成本评测；Heat1D 是初始温度反演，不是加热轨迹优化。 |
| **BOPTEST** [S13] | 建筑控制测试案例、FMU、输入输出接口、统一 KPI、参考控制 | 初始状态、边界条件、控制接口和指标的分离 | 建筑热环境与高温辐射加热的物理及时间尺度不同。 |
| **PDEBench** [S14] | PDE 数据生成、前向/反问题模型和指标 | 数据组织与误差评价 | 主要不是预算受限的在线查询优化任务。 |
| **APEBench** [S15] | JAX、在线生成数据、可微参考求解器，1D/2D/3D 周期域 | 可生成而非必须下载大数据的设计，solver-in-the-loop | 周期边界和代理预测任务不是实际 RTP 边界与工艺验收。 |
| **The Well** [S16] | README 自报 16 个数据集、总计 15 TB，可按数据集下载/流式读取 | 数据格式、物理领域协作与模型评测经验 | 没必要为本项目下载整套数据或训练基础模型；也不是现成设备优化环境。 |
| **IC-ThermBench** [S17] | 2026 年预印本；2.5D/3D-IC 热预测，S1–S5 范围、结构 OOD、few-shot；当前 S2–S5 为 64×64、Z=1 的稳态标签 | 按结构划分数据、明确数据与代码许可、公开评价边界 | 研究对象是芯片/封装工作时的散热，不是晶圆加工设备的升温；公开 S2–S5 不提供本项目所需的瞬态控制任务。 |

上述数量是原作者对项目范围的描述，不构成同条件性能排名。

### IC-ThermBench 的版本问题必须单独记录

读取到的 arXiv v1 摘要报告 S4/S5 最佳 RMSE 为 **1.216/15.99 K**；同日仓库 README 报告为 **0.933/15.51 K**。本轮没有审计差异原因，也没有复测。两组数字不能混用或计算跨版本提升。

仓库同时明确：S2–S4 是独立生成的数据，不是样本配对的因果消融；S1 统一执行入口尚在完善。后续若引用其结果，需要同时固定论文版本、代码、数据及训练配置。

**因此：“热预测 + OOD + 漂亮温度场”已经不足以成为我们项目的独特定位。**

## 五、多保真不是无条件省钱

Fernández-Godino 的 2023 年综述专门讨论开源、基准、成本及精度报告。[S18]

- 保真差异可以来自网格、降维、线性化、部分收敛、几何或物理简化；不能把它们都当成同一种误差。
- §5.3 明确区分**单次低/高保真分析的成本比**与**完整多保真/高保真优化的成本比**。
- 其该项统计整理的 120 篇研究中，18 篇明确提供两项成本比；脚注说明该统计涉及截至 2016 年的论文，不能把它冒充 2023 年全领域统计。
- 文中要求把多保真模型构建所需时间和资源也计入报告。已核对 PDF 第 18–20 页及表 1，并渲染查看表格。

BoTorch 已提供连续及离散 fidelity 的 qMFKG 教程。[S19] 因而我们不需要先重写 BO 算法。

但教程使用 Augmented Hartmann 合成函数和人为设定的仿射成本；例如读取到的连续版本成本为 `5.0 + s`。这不能作为热仿真成本模型直接沿用。离散教程也提醒，无自然次序的信息源可能更适合 multi-task 模型。

Wu 等人的 *Practical Multi-fidelity Bayesian Optimization for Hyperparameter Tuning* 提供方法背景。[S20] 其中训练迭代带来的中间轨迹和状态复用，与物理仿真的网格细化不是一回事，不能把“粗网格算过了”直接当成“细网格结果可免费续算”。本轮未复现其算法。

## 六、求解器与复现条件

这是文档和部分源码层面的适配判断，不是安装测试或速度排名。

| 组件 | 核查内容 | 建议角色 | 边界与成本 |
|---|---|---|---|
| **py-pde** [S21] | 有限差分网格、通用 PDE、时间相关边界表达式/函数；MIT | 简单公开模型、低保真层的候选 | 不自带完整腔体辐射模型；简单域与几何表示有限，仍需数值验证。 |
| **FEniCSx / DOLFINx** [S22] | 热方程弱形式、非线性问题教程；Linux/macOS 等有包或容器路径；DOLFINx 声明 LGPL-3.0-or-later | 自定义有限元参考模型的候选 | 热方程教程不是完整 RTP；网格、非线性边界、材料与辐射交换需建模。不是只装一个纯 Python 包。 |
| **Elmer FEM** [S23] | 热求解源码包含辐射、发射率和 Stefan–Boltzmann 参数；有现成物理模块 | 辐射传热与后续独立交叉核查的候选 | 套件许可混合，不能整包称为 MIT；所读 HeatSolve 文件标 LGPL-2.1-or-later，其他组件需分别检查。 |
| **BoTorch** [S19] | qMFKG、成本模型、多保真 GP 现成教程；MIT | 算法基线 | 需锁版本并真实测量训练、采集函数优化和最终验证成本。 |
| **UM-Bridge** [S12] | 数值模型接口与示例 | 确有跨语言接入需求时复用 | 初始单个 Python 模型不必马上引入服务层，避免为接口而增加复杂度。 |
| **TCLab** [S24] | 2 个加热元件及测温通道，Python 接口、日志工具、无需硬件的模拟器 | 将来的小型实体热控制验证 | 没有硬件实测；常温附近的小型实验不能验证 RTP 的高温辐射、晶圆空间均匀性或真空条件。 |

许可描述仅为源码和文档核查，不是法律意见。底层许可、所复用文件、第三方网格/材料数据、发行方式和公司合作条款仍需逐项确认。

**不要把所有组件一次性装进项目。** 初期只选择一个主求解器；独立求解器只在确有交叉验证需求时加入。版本选择和技术栈须在方案确认后决定。

## 七、三个可选方向及取舍

### A. 单场景的“约束加热轨迹优化”案例包——建议先验证

固定结构，只搜索少量参数化加热轨迹；给出公开参考模型、低保真模型、明确约束和统一成本账本。问题重点是**保真选择与模型偏差对优化结果的影响**。

- 能独立启动：不必拿企业图纸，也不必先买硬件。
- 可复用：现成求解器、BoTorch、必要时 UM-Bridge。
- 代价：需要可信的物理假设、参数出处与热工/数值方法审查。
- 不能保证：新算法贡献、明星项目传播或工业适用性。
- 升级条件：先证明算例能区分不同策略的能力边界，再扩展成基准。

### B. 在 IC-ThermBench 等现有基准上研究“预测误差如何影响优化决策”

不重建通用热预测基准，而是考察代理模型在设计搜索后是否选出真正合格的候选，最终回到参考求解器复核。

- 可复用：已有数据、baseline、结构 OOD 划分。
- 代价：需要确认生成器、参数接口、候选设计与标签可得性；下载数据不等于拥有可任意查询的仿真器。
- 取舍：更靠近芯片/封装热设计，与北方华创的设备制造关联弱于 A；还需面对现有模型版本和硬件成本。
- 本轮未把它确认成学术空白。

### C. TCLab 上的模拟到实物热控制对照

用公开小型热控制装置，核查辨识、模型失配、PI/MPC/学习策略的行为。

- 可复用：现成模拟器、硬件接口和记录方式。
- 代价：后续需获得硬件，并遵守其电气、温度和操作安全要求。
- 取舍：可以获得真实测量证据，但与半导体设备物理差异大；不能把教育装置重新命名为半导体设备数字孪生。
- 它本身也不是新问题，仍须提出具体研究问题。

**推荐 A，保留 C 作为未来实物验证补充；B 是如果转向 AI4EDA 时的另一路线。** 这不是经性能实验得出的排序，而是根据“不依赖企业资源、仍保持设备场景关联”的约束做的选题判断。

## 八、A 方向应如何定义，才不变成玩具或大杂烩

### 8.1 物理与任务边界

- 对象：非专有、假设透明的多区加热对象，不宣称复刻任一实际设备。
- 首个任务：离线加热轨迹优化，不同时承诺在线反馈控制、传感器诊断和结构逆向设计。
- 输入：固定维度的功率/设定值轨迹参数、公开目标和边界条件。
- 输出：经参考求解器计算的跟踪误差、空间温差、超调及能量等量；先选一个主要目标，其余明确作为约束或辅助指标，不任意拼奖励。
- 约束：输入上下限、变化率、温差、超调等，具体阈值必须有公开依据或明确标为研究设定。
- 辐射计算使用绝对温度，说明发射率、视角因子/辐射简化、边缘损失与接触条件。不能把边界“直接设温”当成无限能力的真实加热器。
- 首版可研究受控简化模型；若缺少物理审查，只能定位为数学/数值任务，不能贴工业验证标签。

### 8.2 把三种变化分开

1. **数值保真度：** 同一组方程改变网格、时间步、求解容差。
2. **模型形式差异：** 集总与分布模型、辐射线性化等可解释简化。
3. **工况变化：** 材料、装载或边界参数变化。

不能把前两种与第三种混在一起，最后声称“多保真效果”或“泛化能力”。先单独研究一条轴，且通过预实验检查成本比、预测关联、候选排序与约束边界错误。低保真不保证更便宜、更准确或保持排序。

### 8.3 验证链

**方程/单位检查 → 解析或制造解验证 → 能量平衡 → 网格和时间步收敛 → 基线复算 → 独立算法/求解器交叉核查 → 实物验证（未来）**。

前面的数值验证不等于最后的物理验证；细网格参考解也不能称为实物真值。优化器找到的极端输入必须接受复核，防止它利用数值误差“刷分”。

## 九、评测协议与否决条件

### 公平比较

- 固定同一物理任务、输入参数化、约束、目标、参考求解器及盲测工况。
- 黑箱搜索方法共享初始高保真数据；任何额外低保真采样都计费，不能作为免费启动优势。
- 先考虑空间填充采样、单保真 BO、多保真 BO；若接口提供梯度，则梯度/伴随方法应作为公开模型赛道基线，并计入导数求取成本。
- PI/MPC/ILC 使用不同的反馈或跨运行信息；若比较它们，需要另设控制协议，匹配观测、模型信息和训练/调参预算。不能直接用一个黑箱优化预算给所有控制器排榜。
- 所有方法用同样的参考层复核候选；低保真分数、GP 预测值不得直接计为最终成绩。
- 计入数据生成、模型训练、采集函数优化、失败调用、并行资源和最终复核。单次延迟、端到端墙钟、总 CPU/GPU 用量分别报告。
- 报告可行率、目标值、时间/调用预算下的结果曲线、首次达标成本及多随机种子分布。种子数与预算应在初步成本测量后预先固定，不能挑最好一次。
- 多保真特有组件的因果贡献应另做同初始化、同模型与预算的配对消融；不同算法整体排名不能替代组件消融。

### 遇到以下情况，不继续扩建平台

1. 参数与边界条件缺少出处，且无法获得独立物理/数值审查。
2. 低保真与参考模型的成本差太小，优化器开销抵消节约；此时可以保留负结果，不硬造多保真优势。
3. 任务过易，所有合理基线都很快达到数值误差允许范围；或过难，所有方法始终不可行。
4. 优势仅来自更宽松约束、免费预训练数据、额外查询或不同评估网格。
5. 只能复现热方程教学例子，没有能解释的工程约束或失效机制。
6. 找不到研究者愿意独立运行/审查，也没有具体使用反馈；仓库功能数量不能替代外部价值。

## 十、建议的下一轮决策

本轮不建议直接决定项目品牌和完整架构。建议用户先决定是否批准一个**有停止条件的可行性复现阶段**：

- 按选定上游版本运行一个原生热方程验证案例。
- 运行一个上游多保真教程，核对原生输出，不修改任务制造优势。
- 测量同一热问题两档数值设置的成本与误差，判断是否存在值得优化的真实计算权衡。

这些工作本轮均未执行。若批准，才更新项目实施共识、选择依赖、确定具体计划。没有成本测量前，不承诺硬件配置、开发周期或提效百分比。

## 十一、来源清单

| 编号 | 来源与链接 | 本轮读取范围 |
|---|---|---|
| S01 | [北方华创：快速热处理](https://www.naura.com/product/details_82_2302.html) | 官网正文快照。 |
| S02 | [北方华创：CVD](https://www.naura.com/product/details_82_1586.html) | 官网正文快照。 |
| S03 | [Breedijk 等，1993，RTP MPC](https://doi.org/10.23919/ACC.1993.4793449) | Crossref 元数据；没有论文全文。 |
| S04 | [Modeling, Identification, and Control of RTP Systems，1994](https://doi.org/10.1149/1.2059302) | OpenAlex 索引摘要；期刊入口为验证码页。 |
| S05 | [Control of RTP: a system theoretic approach，1997](https://doi.org/10.1109/87.641407) | OpenAlex 索引摘要。 |
| S06 | [RTP Optimal Iterative Learning Control，2001](https://doi.org/10.1021/ie0005553) | OpenAlex 索引摘要。 |
| S07 | [RTP Experimental Quadratic Optimal ILC，2003](https://doi.org/10.1109/TSM.2002.807740) | OpenAlex 索引摘要。 |
| S08 | [PDE Control Gym 论文 v1](https://arxiv.org/html/2405.11401v1)、[仓库](https://github.com/lukebhan/PDEControlGym) | 原文任务定义、实验、表 3、局限及 README。 |
| S09 | [ControlGym 论文](https://arxiv.org/html/2311.18736)、[仓库](https://github.com/xiangyuan-zhang/controlgym) | 原文概述、PDE 边界定义及 README。 |
| S10 | [MF2](https://github.com/sjvrijn/mf2)、[JOSS](https://joss.theoj.org/papers/10.21105/joss.02049) | README、JOSS 发布页。 |
| S11 | [Flow Reactor Design Benchmark](https://github.com/trsav/reactor_benchmark) | README 的任务、接口、保真与安装边界。 |
| S12 | [UM-Bridge](https://um-bridge-benchmarks.readthedocs.io/en/docs/)、[Heat1D](https://github.com/UM-Bridge/benchmarks/tree/main/benchmarks/heat-1d)、[L2-Sea](https://github.com/cnr-inm-mao/l2-sea-benchmark) | 官方介绍、Heat1D 和 L2-Sea README，模型库树。 |
| S13 | [BOPTEST](https://github.com/ibpsa/project1-boptest) | README：接口、测试结构、KPI 与部署。 |
| S14 | [PDEBench](https://github.com/pdebench/PDEBench) | README：数据、任务、模型、版本限制。 |
| S15 | [APEBench](https://github.com/tum-pbs/apebench) | README：周期域、数据生成、训练与许可。 |
| S16 | [The Well](https://github.com/PolymathicAI/the_well) | README：范围、下载/流式路径、训练与局限。 |
| S17 | [IC-ThermBench 论文 v1](https://arxiv.org/html/2608.23977v1)、[仓库](https://github.com/Day333/ThermalBench)、[复现说明](https://github.com/Day333/ThermalBench/blob/main/docs/REPRODUCE.md) | 原文任务/数据/结果相关部分、README 和复现文档。版本结果有差异。 |
| S18 | [Review of multi-fidelity models，2023](https://doi.org/10.3934/acse.2023015) | 期刊页及完整 PDF 的相关章节，重点 §4、§5 和表 1。 |
| S19 | [BoTorch 连续多保真教程](https://github.com/pytorch/botorch/blob/main/tutorials/multi_fidelity_bo/multi_fidelity_bo.ipynb)、[离散教程](https://github.com/pytorch/botorch/blob/main/tutorials/discrete_multi_fidelity_bo/discrete_multi_fidelity_bo.ipynb) | 教程源码、方法引用、成本假设、MIT 文件；未执行。 |
| S20 | [Wu 等，Practical Multi-fidelity BO，2019](https://arxiv.org/abs/1903.04703) | PDF 摘要、引言、方法适用条件；未复现。 |
| S21 | [py-pde](https://github.com/zwicker-group/py-pde)、[边界条件](https://py-pde.readthedocs.io/en/latest/manual/advanced_usage.html) | README、边界文档。 |
| S22 | [DOLFINx](https://github.com/FEniCS/dolfinx)、[安装](https://docs.fenicsproject.org/dolfinx/main/python/installation.html)、[热方程教程](https://jsdokken.com/dolfinx-tutorial/chapter2/heat_equation.html)、[非线性教程](https://jsdokken.com/dolfinx-tutorial/chapter2/nonlinpoisson.html) | README 许可声明、安装、弱形式；未安装。 |
| S23 | [Elmer](https://github.com/ElmerCSC/elmerfem)、[许可说明](https://github.com/ElmerCSC/elmerfem/blob/devel/license_texts/ElmerLicensePolicy.md)、[HeatSolve](https://github.com/ElmerCSC/elmerfem/blob/devel/fem/src/modules/HeatSolve.F90) | README、许可、热模块的辐射参数与文件头。 |
| S24 | [TCLab](https://github.com/jckantor/TCLab) | README 的硬件、模拟器和实验记录能力；无硬件实测。 |

## 十二、交付与可追溯性

- `intent.md`：本轮调研范围；不替换上级原有会话修复共识。
- `*-search*.json`：检索查询与结果，包含不相关结果和失败记录，不将它们全算作已读论文。
- `sources/`：公开资料快照、PDF、部分源码/目录及获取记录；保留原作者许可与归属，未作为我们原创代码使用。
- `sources/*receipts.json`：请求 URL、获取时间、HTTP 状态、文件路径和 SHA-256。HTTP 成功不等于内容有效。
- `source-audit.json`、`verification.log`：本地来源完整性、错误状态与关键证据检查。
- `tmp/pdfs/review-cost-table.png`：综述成本表的视觉核查图，不是本项目实验结果。

网页与分支会更新，本次快照不是上游完整依赖锁定；实际复现必须另固定代码 commit、数据版本和环境。所有实现、训练与工业实验仍未开始。
