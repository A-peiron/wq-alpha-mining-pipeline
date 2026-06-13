<div align="center">

# 🧠 WorldQuant Alpha Mining Pipeline

**面向 [WorldQuant BRAIN](https://platform.worldquantbrain.com) 的分阶段、人工可控因子挖掘流水线 · 配 Web 控制台**

纯脚本驱动 · 五阶段挖掘 · 质量门控 · 相关性剪枝 · 实时日志 · 人工复核提交

<br/>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white) ![React](https://img.shields.io/badge/React-61DAFB?logo=react&logoColor=black) ![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white) ![License](https://img.shields.io/badge/License-Personal%20Use%20Only-red)

[快速开始](#-快速开始) · [挖掘流程](#-挖掘流程) · [工作原理](#-工作原理) · [Web 控制台](#-web-控制台) · [FAQ](#-常见问题)

</div>

---

## 📖 简介

把 WorldQuant BRAIN 上「字段 → 因子 → 回测 → 去重 → 提交」这条重复劳动，做成一条**可观测、可控、可复跑**的流水线。

它不替你做投资决策——每一步由你启动、看质量信号、再决定下一步，最终只产出一份**人工复核清单**，提交与否始终在你手里。适合需要规模化批量挖矿、又不想把提交权交给黑盒的研究者。

> ⚠️ 仅供个人学习研究使用，未经授权不得复制、修改或用于商业用途。详见 [LICENSE](LICENSE)。

## ✨ 特性

| | |
|---|---|
| 🪜 **五阶段流水线** | Order 1 广撒网 → 2 分组增强 → 3 参数增强 → 4 变体扩展 → 5 相关性剪枝，逐级精炼 |
| 🚦 **质量门控** | 回测后即按 Sharpe / Fitness / Turnover / Margin + 官方 checks 打信号灯（🟢🟡🔴⚫） |
| ✂️ **智能剪枝** | 按综合质量贪心去重，相关簇内保留综合最优代表，而非单纯 Sharpe 最高 |
| 🔍 **双模检查** | FAST 快速粗筛 / OFFICIAL 官方精筛，提交前质量门拦截不可提交因子 |
| 🖥️ **Web 控制台** | 脚本启停、实时日志流、候选流转统计、本地与平台数据总览 |
| ✋ **人工把关** | check 只产出 `submitable_alpha.csv`，人工复核后提交，绝不自动提交 |
| 🔄 **断点续跑** | 表达式去重 + 已检查记录持久化，重启不重复消耗回测额度 |
| 🌐 **多数据集隔离** | tag 按 `dataset/region/delay` 自动生成，切数据集记录互不污染 |

## 📑 目录

- [挖掘流程](#-挖掘流程)
- [快速开始](#-快速开始)
- [配置说明](#-配置说明)
- [Web 控制台](#-web-控制台)
- [工作原理](#-工作原理)
- [技术栈](#-技术栈)
- [目录结构](#-目录结构)
- [安全须知](#-安全须知)
- [部署](#-部署)
- [常见问题](#-常见问题)

## 🪜 挖掘流程

```
 Order 1   字段 × 基础/时序算子，广撒网生成一阶因子并回测
    │       └─ 取高分 (Sharpe≥0.6 / Fitness≥0.35)
    ▼
 Order 2   套 group 中性化 / 分组算子
    │       └─ 取高分 (Sharpe≥1.2 / Fitness≥0.75)
    ▼
 Order 3   套 ts_decay_linear / rank / zscore 等参数增强
    ▼
 Order 4   rank / zscore / normalize / ts_decay_linear 变体扩展
    │       └─ 取高分
    ▼
 Order 5   PnL 相关性剪枝（综合质量排序贪心去重）→ 人工复核队列
    ▼
 check     self-corr 检查 + 质量门 → submitable_alpha.csv
    ▼
 人工复核 → 手动提交
```

> Order 1~4 都是「生成表达式 + Brain 回测」；Order 5 不回测，只做相关性剪枝产出复核队列。

| 阶段 | 脚本 | 输入 | 产出 |
|------|------|------|------|
| Order 1 | `digging_1step.py` | 数据字段 | 一阶因子回测 |
| Order 2 | `digging_2step.py` | 1step 高分 | group 增强因子 |
| Order 3 | `digging_3step.py` | 2step 高分 | 参数增强因子 |
| Order 4 | `digging_4step.py` | 3step 高分 | 变体扩展因子 |
| Order 5 | `digging_5step.py` | 4step 高分 | 复核队列（剪枝） |
| Check | `check.py` | 终态候选 | `submitable_alpha.csv` |

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/A-peiron/wq-alpha-mining-pipeline.git alpha && cd alpha

# 2. 配置凭证（不会被提交）
cp credentials.json.template credentials.json
#    编辑 credentials.json 填入 BRAIN 的 email / password

# 3. 安装（editable，使 alpha 包可导入）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .

# 4. 构建前端（产物直接输出到 src/alpha/web/static）
cd frontend && npm install && npm run build && cd ..

# 5. 启动 Web 控制台
uvicorn alpha.web.app:app --host 0.0.0.0 --port 8000
#    打开 http://localhost:8000
```

**或命令行直接跑**（不经 Web）：

```bash
python -m alpha.pipeline.digging_1step    # Order 1
python -m alpha.pipeline.digging_2step    # Order 2
python -m alpha.pipeline.digging_3step    # Order 3
python -m alpha.pipeline.digging_4step    # Order 4
python -m alpha.pipeline.digging_5step    # Order 5（相关性剪枝）
python -m alpha.pipeline.check            # 提交前检查
```

## ⚙️ 配置说明

- **数据集** `dataset_id`（如 `analyst4`）：可在 BRAIN 平台 data 页 URL 中找到
- **tag 命名**：`{dataset}_{region}_{step}step_delay{delay}`，由 `config.get_stage_tags()` 按参数自动生成，切数据集自动隔离记录
- **check 模式** `records/check_mode.txt`：
  - `FAST` — 只用 xin_plus 近似粗筛，不调官方接口，速度快
  - `OFFICIAL` — xin_plus 粗筛 → 质量门 → 本地 PnL 剪枝 → 官方 self-corr 精筛（默认）

挖掘参数在 Web 设置页或 `records/digging_config.json` 中调整。

## 🖥 Web 控制台

| 页面 | 功能 |
|------|------|
| Dashboard | 总览：今日模拟 / 成功率 / 可提交数 / 质量分布 |
| Control | 各阶段脚本启停、实时日志、候选流转统计、check 模式切换 |
| Alphas | 本地可提交因子列表、人工复核、官方检查、手动提交 |
| Platform | 平台真实 OS/IS、未提交数等 |
| Settings | 凭证与挖掘参数配置 |

## 🔬 工作原理

三个核心机制，决定了这套流水线和「裸跑脚本」的区别：

**1. 质量门控（信号灯）** — 每个因子回测后立即用 `evaluate_alpha` 综合 Sharpe / Fitness / Turnover / Margin + BRAIN 官方 checks 打分，分成 🟢 GREEN（达标）/ 🟡 YELLOW（可提交底线）/ 🔴 RED（需优化）/ ⚫ DEAD（淘汰）。check 阶段的质量门只放行 GREEN/YELLOW，RED/DEAD 直接拦下，不浪费官方 self-corr 配额。

**2. 综合质量相关性剪枝** — Order 5 对 PnL 序列做贪心相关性去重：按综合质量（信号灯 → fitness → sharpe）排序，相关簇内**保留综合最优代表**，而不是简单留 Sharpe 最高的那个，避免误剪掉 fitness 更好的因子。阈值对齐 BRAIN 探索期 0.7。

**3. 断点续跑 + 去重** — 已模拟表达式写入 `{tag}_simulated_alpha_expression.txt`、已检查写入 `{tag}_checked_alpha_id.txt`。重启任何阶段都会跳过已完成项，不重复消耗 BRAIN 回测额度；终态候选池检查完即退出，不空转。

## 🛠 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ · FastAPI · Uvicorn |
| 挖掘 | requests · aiohttp（异步并发回测） |
| 前端 | React · TypeScript · Vite |
| 数据源 | WorldQuant BRAIN 平台 API |

## 📂 目录结构

```
alpha/                          # 项目根
├── pyproject.toml              # 包定义（pip install -e .）
├── requirements.txt
├── credentials.json            # 账号密码（gitignore）
├── records/                    # 运行时数据（gitignore，自动生成）
├── logs/                       # 运行日志（gitignore）
├── frontend/                   # React 前端源码（产物输出到 src/alpha/web/static）
└── src/alpha/                  # 主包
    ├── __init__.py             #   PROJECT_ROOT 定位
    ├── core/                   #   核心库
    │   ├── config.py           #     配置、tag 生成、凭证读写
    │   ├── machine_lib.py      #     登录 / 回测 / 字段 / 因子工厂
    │   └── fields.py           #     数据字段定义
    ├── pipeline/               #   入口脚本（python -m alpha.pipeline.xxx）
    │   ├── digging_1step.py ~ digging_5step.py
    │   ├── check.py            #     提交前 self-corr 检查 + 质量门
    │   └── submit_alpha.py     #     手动提交
    ├── mining/                 #   质量评估、校验、阶段注册
    │   ├── quality.py          #     evaluate_alpha / 相关性剪枝 / 排序
    │   ├── validators.py       #     表达式预检与去重
    │   ├── factories.py        #     高阶因子生成
    │   └── stage_registry.py   #     阶段定义
    └── web/                    #   FastAPI 后端
        ├── app.py              #     应用入口（uvicorn alpha.web.app:app）
        ├── routers/            #     control / alphas / status / platform …
        └── static/             #     前端构建产物
```

## 🔐 安全须知

- **绝不提交** `credentials.json`、`user_info.txt` 等含账号密码的文件 — 已在 `.gitignore`
- `records/`、`logs/` 为运行时数据，已忽略，首次运行自动创建
- Web 服务若暴露公网，建议加反向代理 + HTTPS + 基础认证 / 防火墙白名单

## ☁️ 部署

云端部署（Ubuntu + supervisor + nginx）见 **[DEPLOY.md](DEPLOY.md)**。

## ❓ 常见问题

<details>
<summary><b>挖掘提示 "没有因子可以跑了 / known_expression"？</b></summary>

当前数据集 + 算子组合已被本地记录跑空。换数据集（`dataset_id`）、启用更多字段，或扩展算子组合。tag 会随数据集自动隔离。
</details>

<details>
<summary><b>check 一直跑不停 / 重复检查同一批？</b></summary>

终态候选池（Order5/Order4）已改为单遍检查后退出，已检查的会写入 `{tag}_checked_alpha_id.txt` 并自动跳过。重启 check 只会检查新增候选。
</details>

<details>
<summary><b>Order5 PnL 一直 "暂未就绪/限流"？</b></summary>

正常现象。BRAIN 的 PnL 接口首次请求常返回 `Retry-After` 空响应，脚本会自动等待重试，第二次即成功。只要最终 "失败/无PnL" 计数为 0 即正常。
</details>

<details>
<summary><b>日志中文乱码？</b></summary>

确保以 UTF-8 启动（supervisor 配置已设 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`）。日志文件与前端 SSE 均已统一 UTF-8。
</details>

## 🙏 致谢

- [WorldQuant BRAIN](https://platform.worldquantbrain.com) — Alpha 回测与提交平台

## 📄 许可

知识产权归原作者所有。**仅供个人学习研究，禁止商业售卖，禁止未经授权转载传播**。详见 [LICENSE](LICENSE)。

---

<div align="center">
<sub>⭐ 如果这个项目对你有帮助，欢迎 Star · 仅供学习研究 · 禁止商用</sub>
</div>

