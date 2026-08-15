---
name: architecture-decomposition
description: Use when a user asks to audit, reverse-engineer, or decompose an AI product from visible website evidence, including user journeys, execution units, I/O contracts, orchestration behavior, model comparison, evaluation, Agent workflows, leaderboards, product architecture, or a complete evidence-backed HTML report.
---

# 架构拆解skill

## 核心原则

只基于用户可见、可复核的证据还原产品行为。把“页面事实”“行为推断”“建议设计”和“未知”严格分开；不把前端现象包装成已确认的后台实现。

## 最简调用

用户只需提供产品/目标名称和 URL，例如：

> 使用「架构拆解skill」拆解 Arena：https://example.com/conversation/123

若用户没有补充范围，默认：复用当前浏览器登录态、只读查看该 URL 及所属会话可见内容、依次完成四阶段、生成四份独立 HTML，并打包为一个 ZIP。默认范围不等于全站事实；页面之外的模式和异常仍标为未知。

## 开始前

1. 完整读取 [references/evidence-and-safety.md](references/evidence-and-safety.md)。
2. 根据用户目标读取 [references/four-stage-workflow.md](references/four-stage-workflow.md) 中对应阶段；若用户要求完整拆解，依次执行全部四阶段。
3. 需要生成 HTML、交互报告或上传包时，完整读取 [references/html-delivery.md](references/html-delivery.md)。
4. 用户给出网站、会话链接或要求复用登录态时，优先使用 `ego-browser`；若不可用，再使用具有现有登录态的浏览器能力。
5. 在浏览器操作前向用户说明正在使用浏览器进行只读取证；任何技能规则导致暂停或需要用户接管时，立即说明原因。

## 默认交付范围

| 阶段 | 目标 | 默认文件 |
|---|---|---|
| 1 | 用户旅程与决策路径 | `01-user-journey.html` |
| 2 | 执行单元、I/O、状态与评测流 | `02-execution-units.html` |
| 3 | 单执行单元功能等价编排规范 | `03-orchestration-spec.html` |
| 4 | 产品全景架构、As-Is/To-Be 与风险 | `04-product-architecture.html` |

用户要求“完整拆解”“四份报告”或只提供产品名与 URL 时，输出四份独立 HTML。用户明确只指定一个阶段时，只完成该阶段，不自动扩展。

## 标准工作流

### 1. 锁定范围

- 记录目标 URL、会话、页面模式、时间范围、用户允许的操作和交付阶段。
- 若执行单元未指定，从页面证据中选择当前会话里证据最充分的单元，并明确选择理由。
- 具体会话默认只代表该会话和可见模式；不得从单会话推成全站事实。

### 2. 建立证据台账

- 从最早可见记录开始，按时间顺序查看消息、附件、响应、模型标签、状态、按钮、错误、历史和资产。
- 每个关键状态保存并复查截图，使用 `S01`、`S02`……编号。
- 每条证据使用 `E01`、`E02`……编号，包含原文、控件、模式、模型/槽位、资产、状态、截图和来源。
- 同时记录“出现了什么”和“没有安全观察到什么”。未出现的异常统一标为未知，不得补写产品能力。

### 3. 分阶段建模

- 阶段 1：以用户目标、动作、界面反馈、决策、状态变化、情绪和阻力为主。
- 阶段 2：以实际出现的执行单元、输入、可观察判断、动作、输出、状态、上下游和数据流为主。
- 阶段 3：选择一个目标执行单元，写功能等价行为规范；不得声称还原官方 System Prompt 或隐藏思维链。
- 阶段 4：把已确认功能域、模式流、上下文、评测、资产、数据实体、风险和建议设计组合成产品架构。

### 4. 交叉验证

- 页面写“完成”时，分别检查结果槽位、文本/媒体资产、历史状态和操作入口是否真实存在。
- 模型标签出现时，记录出现时机；不得推断其此前已对用户公开。
- 比较聊天、响应卡、画布/资产、评价、揭晓、历史和任务状态；冲突必须并列展示。
- 若结论依赖多个事实，列出全部证据编号并标为合理推断。

### 5. 生成并验证 HTML

- 从 [assets/report-template.html](assets/report-template.html) 复制结构并替换语义占位符，或按同等规范创建页面。
- HTML 必须可独立打开、内联 CSS、响应式、可打印，并提供证据锚点与图例。
- 运行：

```bash
python3 scripts/validate_report.py --phase auto <report.html>
```

- 修复所有错误后，在浏览器打开最终 HTML，检查导航、表格、截图、溢出、遮挡、空白区和打印效果。
- 用户要求上传包时运行：

```bash
python3 scripts/package_reports.py --output <name>.zip <report1.html> <report2.html> ...
```

## 决策规则

| 页面情况 | 处理方式 |
|---|---|
| 模式有明确文案或选中态 | 记为页面事实，并引用原文与截图 |
| 仅从布局或行为判断模式 | 记为合理推断，列出至少两条依据 |
| 功能入口存在但未安全点击 | 记录入口事实；点击后的行为标为未知 |
| Agent 展示计划、思考或步骤 | 只称“公开执行摘要”，不等同隐藏调用链 |
| 匿名槽位未揭晓 | 使用“候选槽位 A/B”，不得猜模型身份 |
| 前端状态与结果资产冲突 | 两者并列，标记冲突，不自行选择真相 |
| 需要登录、验证码或用户授权 | 暂停并把浏览器交给用户，等待明确确认 |
| 用户要求后台实现或官方 Prompt | 转为功能等价规范，并明确证据边界 |

## 完成门槛

- 所有已确认结论都能追溯到证据编号和截图或官方资料。
- 所有推断都给出依据；所有建议都不冒充现状；证据不足处明确写“未知”。
- 正常、纠偏、失败和中断路径均被覆盖；没有证据的路径使用虚线或未知卡片。
- HTML 中不存在未替换占位符、敏感信息、失效本地资源、外部 UI 库依赖或模型身份猜测。
- 用户要求的每个阶段都有独立文件；完整拆解包还包含上传说明。

## 常见错误

- 只读聊天文字，漏掉按钮、状态、媒体、历史和结果资产。
- 把功能性命名写成官方工具/API 名。
- 把排行榜结果当成本次用户评价，或把“结果可见”当成“用户已投票”。
- 用产品宣传、常识或第三方评测补齐页面缺失流程。
- 将建议架构混入 As-Is 主图而不使用不同线型和图例。
- 输出 Markdown 后忘记生成用户要求的完整 HTML。

## 资源索引

- [references/evidence-and-safety.md](references/evidence-and-safety.md)：证据等级、只读边界、截图和敏感信息规范。
- [references/four-stage-workflow.md](references/four-stage-workflow.md)：四阶段输出结构、表格和图形要求。
- [references/html-delivery.md](references/html-delivery.md)：交互 HTML、可访问性、验证和飞书上传包规范。
- [assets/report-template.html](assets/report-template.html)：可复制的独立 HTML 页面骨架。
- `scripts/validate_report.py`：报告结构、证据、资源和敏感信息校验。
- `scripts/package_reports.py`：校验并打包多份 HTML 及其本地资源。
