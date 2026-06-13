<div align="center">

# 🧠 WorldQuant Alpha Mining Pipeline

**面向 WorldQuant BRAIN 的分阶段、人工可控因子挖掘流水线 · 配 Web 控制台**

纯脚本驱动（无 AI 自动决策）· 五阶段挖掘 · 质量门控 · 相关性剪枝 · 实时日志 · 人工复核提交

<br/>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white) ![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black) ![Vite](https://img.shields.io/badge/Vite-Build-646CFF?logo=vite&logoColor=white) ![License](https://img.shields.io/badge/License-Personal%20Use%20Only-red)

</div>

---

## 📖 简介

本项目是面向 [WorldQuant BRAIN](https://platform.worldquantbrain.com) 平台的**规模化分阶段人工控制**因子挖掘系统。每一步由人工启动批量挖掘，观察质量信号后再决定下一步，最终产出**人工复核 + 手动提交**清单——既保留自动化效率，又把提交决策权留在你手里。

> ⚠️ 本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。详见 [LICENSE](LICENSE)。

## ✨ 特性

- 🪜 **五阶段挖掘流水线** — Order 1 广撒网 → 2 分组增强 → 3 参数增强 → 4 变体扩展 → 5 相关性剪枝
- 🚦 **质量门控** — 回测后即按 Sharpe / Fitness / Turnover / Margin + 官方 checks 打信号灯（🟢🟡🔴⚫）
- ✂️ **相关性剪枝** — 按综合质量贪心去重，相关簇内保留综合最优代表，而非单纯 Sharpe 最高
- 🔍 **双模检查** — FAST 快速粗筛 / OFFICIAL 官方精筛，提交前质量门拦截不可提交因子
- 🖥️ **Web 控制台** — 脚本启停、实时日志流、候选流转统计、本地与平台数据总览
- ✋ **手动提交** — check 只产出 `submitable_alpha.csv`，人工复核后提交，不自动提交
- 🔄 **断点续跑** — 表达式去重 + 已检查记录，重启不重复消耗回测额度

<!-- PLACEHOLDER -->

## 📑 目录

- [挖掘流程](#-挖掘流程)
- [技术栈](#-技术栈)
- [快速开始](#-快速开始)
- [配置说明](#-配置说明)
- [Web 控制台](#-web-控制台)
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

## 🛠 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ · FastAPI · Uvicorn |
| 挖掘 | requests · aiohttp（异步回测） |
| 前端 | React · TypeScript · Vite |
| 数据源 | WorldQuant BRAIN 平台 API |

## 🚀 快速开始

```bash
# 1. 克隆
git clone <your-repo-url> alpha && cd alpha

# 2. 配置凭证（不会被提交）
cp credentials.json.template credentials.json
#    编辑 credentials.json 填入 BRAIN 的 email / password

# 3. 安装后端依赖
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. 构建前端（使用 Web 控制台时）
cd frontend && npm install && npm run build && cd ..

# 5. 启动 Web 控制台
uvicorn web.app:app --host 0.0.0.0 --port 8000
#    打开 http://localhost:8000
```

**或命令行直接跑**（不经 Web）：

```bash
python digging_1step.py    # Order 1
python digging_2step.py    # Order 2
python digging_3step.py    # Order 3
python digging_4step.py    # Order 4
python digging_5step.py    # Order 5（相关性剪枝）
python check.py            # 提交前检查
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

## 📂 目录结构

```
├── digging_1step.py ~ digging_5step.py   # 五阶段挖掘脚本
├── check.py                # 提交前 self-corr 检查 + 质量门
├── machine_lib.py          # 核心库：登录 / 回测 / 字段 / 因子工厂
├── config.py               # 配置、tag 生成、凭证读写
├── fields.py               # 数据字段定义
├── mining/                 # 质量评估、校验、阶段注册
│   ├── quality.py          #   evaluate_alpha / 相关性剪枝 / 排序
│   ├── validators.py       #   表达式预检与去重
│   └── stage_registry.py   #   阶段定义
├── web/                    # FastAPI 后端
│   ├── app.py              #   应用入口
│   └── routers/            #   control / alphas / status / platform …
├── frontend/               # React 前端源码（构建产物入 web/static）
├── records/                # 运行时数据（gitignore，自动生成）
└── credentials.json        # 账号密码（gitignore）
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

---

<div align="center">
<sub>仅供个人学习研究 · 禁止商用</sub>
</div>

