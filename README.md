<div align="center">

# QuantEvoLens — Open-Source QuantEvoLens

**A 股 / 港股 / 美股QuantEvoLens量价分析智能体 — 你说人话，他读盘面。**

[![PyPI](https://img.shields.io/pypi/v/quantevolens?color=blue)](https://pypi.org/project/quantevolens/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Web App](https://img.shields.io/badge/Web-React%20App-0ea5e9.svg)](https://quantevolens-analysis.pages.dev/)
[![Homepage](https://img.shields.io/badge/homepage-QuantEvoLens%20Homepage-0ea5e9.svg)](https://crystallatsyrc.github.io/quantevolens-homepage/)

[English](docs/README_EN.md) | [日本語](docs/README_JA.md) | [Español](docs/README_ES.md) | [한국어](docs/README_KO.md) | [架构文档](docs/ARCHITECTURE.md)

</div>

---

用自然语言和一位QuantEvoLens大师对话。系统把 A 股日线行情、QuantEvoLens结构识别、AI 研报、持仓风控、形态复盘和通知推送串成一条自动化链路，并已扩展支持港股与美股漏斗扫描。

React Web、CLI、MCP 与 GitHub Actions 共同组成当前产品形态；日线行情通过 TickFlow 实时拉取（无 Supabase 行情缓存），Supabase 仅用于用户配置、持仓、形态复盘、市场信号、信号反馈与任务结果。

> Risk disclosure: QuantEvoLens is for educational, research, and informational use. It does not provide investment advice, does not account for every personal financial circumstance, and does not guarantee future performance.

## Special Thanks

<table>
  <tr>
    <td width="150" align="center">
      <a href="https://tickflow.org/auth/register?ref=5N4NKTCPL4">
        <img src="attach/tickflow-logo.png" alt="TickFlow" width="120" />
      </a>
    </td>
    <td>
      <strong><a href="https://tickflow.org/auth/register?ref=5N4NKTCPL4">TickFlow</a></strong><br />
      感谢 TickFlow 为 QuantEvoLens 提供高质量 A 股 / 美股 / 港股行情数据能力支持。
    </td>
  </tr>
  <tr>
    <td width="150" align="center">
      <strong><a href="https://github.com/waditu/czsc">CZSC</a></strong><br />
      <sub>缠中说禅</sub>
    </td>
    <td>
      <strong><a href="https://github.com/waditu/czsc">缠中说禅（CZSC）</a></strong><br />
      感谢顶级交易开源项目缠中说禅（CZSC）的作者 <a href="https://github.com/zengbin93">zengbin93</a> 在交易策略上的指导与点拨。
    </td>
  </tr>
</table>

---

## 快速开始

### CLI（推荐）

```bash
# 一键安装
curl -fsSL https://raw.githubusercontent.com/crystallatsyrc/QuantEvoLens/main/install.sh | bash

# 或 Homebrew / pip
brew tap crystallatsyrc/quantevolens && brew install quantevolens
uv pip install quantevolens
```

```bash
quantevolens          # 启动 Agent 对话
quantevolens dashboard  # 启动本地可视化面板
```

启动后 `/model` 选择模型（Gemini / Claude / OpenAI），输入 API Key 即可对话。

<p align="center">
  <img src="attach/cli-home.png" alt="CLI 启动界面" width="900" />
</p>

<details>
<summary><strong>展开更多 CLI 截图</strong></summary>

| 持仓查询 | 诊断报告 | 操作指令 |
|:---:|:---:|:---:|
| <img src="attach/cli-running.png" width="300" /> | <img src="attach/cli-analysis.png" width="300" /> | <img src="attach/cli-result.png" width="300" /> |

</details>

### Web App

在线地址：**[quantevolens-analysis.pages.dev](https://quantevolens-analysis.pages.dev/)**

<p align="center">
  <img src="docs/screenshots/web-chat.png" alt="Web 读盘室" width="900" />
</p>

<details>
<summary><strong>展开更多 Web App 截图</strong></summary>

| 漏斗选股 | 形态复盘 |
|:---:|:---:|
| <img src="docs/screenshots/web-screen.png" width="450" /> | <img src="docs/screenshots/web-track.png" width="450" /> |

| 持仓管理 | 单股分析（脱敏样例） |
|:---:|:---:|
| <img src="docs/screenshots/web-portfolio.png" width="450" /> | <img src="docs/screenshots/web-analysis-redacted.png" width="450" /> |

</details>

### Streamlit MVP 已下线

Streamlit 已经不再迭代维护，主分支已全面移除 Streamlit 运行代码。相关代码仍保留在 `release/streamlit` 分支；Streamlit MVP 时期的产品架构和效果图见 [docs/STREAMLIT_MVP_ARCHITECTURE.md](docs/STREAMLIT_MVP_ARCHITECTURE.md)。

### 本地可视化面板（Dashboard）

```bash
quantevolens dashboard
```

<p align="center">
  <img src="attach/demo/dashboard-overview-new.png" alt="Dashboard 总览" width="900" />
</p>

<details>
<summary><strong>展开更多 Dashboard 截图</strong></summary>

| 形态复盘 | 信号池 | 尾盘记录 |
|:---:|:---:|:---:|
| <img src="attach/demo/dashboard-recommendations.png" width="300" /> | <img src="attach/demo/dashboard-signals.png" width="300" /> | <img src="attach/demo/dashboard-tail-buy.png" width="300" /> |

| 持仓 | Agent 记忆 | 后台任务 |
|:---:|:---:|:---:|
| <img src="attach/demo/dashboard-portfolio.png" width="300" /> | <img src="attach/demo/dashboard-memory.png" width="300" /> | <img src="attach/demo/dashboard-bgtasks.png" width="300" /> |

| 对话日志 | 同步状态 | 对话日志详情（Trace） |
|:---:|:---:|:---:|
| <img src="attach/demo/dashboard-chatlog-new.png" width="300" /> | <img src="attach/demo/dashboard-sync.png" width="300" /> | <img src="attach/demo/dashboard-chatlog-detail-content.png" width="300" /> |

</details>

### 回测网格

<p align="center">
  <img src="attach/backtest-grid-1.png" alt="回测网格最优参数与梯队表" width="900" />
</p>

<details>
<summary><strong>展开更多回测截图</strong></summary>

| 参数矩阵 |
|:---:|
| <img src="attach/backtest-grid-2.png" width="450" /> |

</details>

---

## 功能亮点

- **对话式 Agent** — 用自然语言触发诊断、筛选、研报，LLM 自主编排 15 个工具
- **五层漏斗筛选** — A 股全市场约 4500 股保留完整 AI 审判链路，港股 / 美股独立 universe 扫描并写入跟踪复盘表
- **跨市场** — A 股 / 港股 / 美股漏斗独立 workflow
- **AI 三阵营研报** — 逻辑破产 / 储备营地 / 起跳板，LLM 独立审判
- **信号反馈闭环** — 漏斗记录 observations，盘后 feedback 聚合 health / registry，支持 shadow 动态策略验证
- **持仓诊断 & 私人决断** — 批量体检 + EXIT/TRIM/HOLD/PROBE/ATTACK 指令
- **Agent 分层记忆** — L1 原子记忆 + L2 场景 + L3 画像，FTS5/代码/关键词混合召回并保留来源追溯
- **Skills 扩展** — 内置 `/screen`、`/checkup`、`/report`、`/backtest`，用户可自定义
- **Prompt 模板** — 内置 `/daily`、`/review-l4`、`/step3-audit` 等高频投研模板，也支持 `~/.quantevolens/prompts/*.md`
- **模型元数据与成本可见性** — `quantevolens model list/usage/cost` 展示上下文窗口、reasoning 能力和本地 token 成本估算
- **会话分叉与导出** — `quantevolens session export/fork` 或 TUI `/fork` 把历史对话变成可复盘、可继续的新分支
- **标准事件流** — `quantevolens trace --events <scratchpad.jsonl>` / `quantevolens diag` 产出统一 JSONL，方便复盘工具调用时间线
- **依赖卫生检查** — CI 运行 `scripts/check_dependency_hygiene.py`，提示 Python/Web 依赖锁定和 lockfile 风险
- **MCP Server** — 10 个工具通过 MCP 协议对外暴露，Claude Code / Cursor 即插即用
- **多通道推送** — 飞书 / 企微 / 钉钉 / Telegram
- **本地面板** — `quantevolens dashboard` 一条命令启动可视化

---

## 演示视频

<details>
<summary><strong>「从0到1读盘」Web 全流程（读盘室→设置）</strong></summary>

<img src="attach/demo/web-demo.gif" width="900" />

</details>

<details>
<summary><strong>「终端党最爱」CLI 流程（启动→执行→结果）</strong></summary>

<img src="attach/demo/cli-demo.gif" width="900" />

</details>

---

## 文档导航

| 想了解 | 去哪里看 |
|--------|----------|
| 架构、Actions、数据表、缓存 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| **A 股主漏斗执行流程（上下游 + 流程图）** | [docs/A_SHARE_FUNNEL_FLOW.md](docs/A_SHARE_FUNNEL_FLOW.md) |
| 信号反馈闭环、shadow/on 动态策略 | [docs/SIGNAL_FEEDBACK_LOOP.md](docs/SIGNAL_FEEDBACK_LOOP.md) |
| 系统迭代策略与落地状态 | [docs/ITERATION_STRATEGY.md](docs/ITERATION_STRATEGY.md) |
| 漏斗、AI 研报、OMS、回测 | [README_STRATEGY.md](README_STRATEGY.md) |
| 术语速查 | [GLOSSARY.md](GLOSSARY.md) |
| MCP Server 配置 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#mcp-server) |
| 密钥与本地配置安全 | [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) |

> **Wiki 深度阅读**：[交易方法论 Wiki](https://github.com/crystallatsyrc/QuantEvoLens/wiki/01_Finance_QuantEvoLens_Method) ｜ [技术架构 Wiki](https://github.com/crystallatsyrc/QuantEvoLens/wiki/03_Tech_Architecture)

---

## 配置

**零配置即可使用** — 启动后 `/model` 添加 LLM API Key 即可对话。

进阶配置见 [架构文档](docs/ARCHITECTURE.md)。

> 数据源购买：[TickFlow →](https://tickflow.org/auth/register?ref=5N4NKTCPL4) ｜ 大模型购买：[1Route →](https://www.1route.dev/register?aff=359904261)

---
