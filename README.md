# 回响计划 · Project Echo

> 一个带有深度记忆、性格演化和叙事感的交互式存在体。
> *An interactive entity with deep memory, personality evolution, and narrative sense.*

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 核心理念

不是为了创造"更聪明的工具"，而是为了搭建一个能够承载记忆、演化性格、讲述故事的交互式存在体。

**评价标准**：不是准确率，而是**惊喜感**——它是否会在某一次回应中，让你产生"这不是我预设的，但它让我意外"的感觉。

---

## 三条学习途径

回响通过三种独立途径不断学习，共用一套低温知识提取引擎：

| 途径 | 触发时机 | 权重 | 说明 |
|------|---------|------|------|
| 🗣️ 对话反思 | 每次 `/quit` 休眠时 | 0.40 | 从当日对话中提取事实性知识 |
| 🔧 工具习得 | 执行 `read_file` / `search_web` 时 | 0.45 | 从工具结果中即时提取知识 |
| 🔍 睡眠探索 | 休眠时（8h 冷却） | 0.35 | 自主搜索 1-2 个核心话题，拓展知识 |

---

## 项目结构

```
Project Echo/
├── config/
│   ├── principles.yaml          # 三条基因级不可变原则
│   ├── birth_inscription.txt    # 出生铭文（19字，永不覆盖）
│   └── anchors.yaml             # 18 个灵魂锚点定义
├── src/echo/
│   ├── agent/
│   │   └── core.py              # Echo 主体：对话、记忆检索、情感、系统提示
│   ├── memory/
│   │   ├── models.py            # Memory 数据模型（三因素加权 + 半衰期衰减）
│   │   ├── store.py             # SQLite + sqlite-vec 向量存储
│   │   ├── priority.py          # 批量评分引擎
│   │   └── summarizer.py        # 睡眠期记忆压缩（LLM 摘要）
│   ├── llm/
│   │   └── backend.py           # 本地 llama-server + 云端 API fallback
│   ├── tools/
│   │   ├── registry.py          # OpenAI 兼容工具注册
│   │   └── builtin.py           # 9 个内置工具（搜索、文件、shell）
│   ├── consciousness/
│   │   ├── anchors.py           # 灵魂锚点注册表
│   │   ├── stream.py            # 意识流（每轮动态状态）
│   │   └── crystallize.py       # 结晶引擎（定期自我反思）
│   ├── zim_reader.py            # ZIM 文件读取器（libzim + HTML→纯文本）
│   ├── zim_ingest.py            # ZIM→记忆导入管道（话题筛选 + 去重）
│   ├── cli.py                   # Rich CLI（聊天/探索/ZIM导入模式）
│   └── config.py                # 全局配置加载
├── tests/                       # 31 个测试
├── start.ps1                    # 一键启动脚本
└── LICENSE                      # MIT
```

---

## 快速开始

```bash
# 一键启动（Windows PowerShell）
.\start.ps1

# 或手动启动：
# 1. 启动 llama-server
llama-server -m <模型路径> --host 127.0.0.1 --port 8080 -c 8192 -ngl 99 --reasoning off

# 2. 安装 + 启动回响
pip install -e .
python -m echo.cli
```

---

## 常用命令

### 启动模式

```bash
# 聊天模式（默认）
python -m echo.cli

# 探索模式 —— 回响自主搜索学习
python -m echo.cli --explore                          # 自主选话题，每 10 分钟
python -m echo.cli --explore --topic "量子计算,AI"    # 指定话题
python -m echo.cli --explore --interval 5 --rounds 10 # 自定义间隔和轮次

# ZIM Wikipedia 导入
pip install libzim -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m echo.cli --ingest-zim <文件.zim> --zim-topic computer --zim-dry-run    # 扫描预览
python -m echo.cli --ingest-zim <文件.zim> --zim-topic computer                  # 首段模式导入
python -m echo.cli --ingest-zim <文件.zim> --zim-topic "计算机,AI" --max-articles 10000
python -m echo.cli --ingest-zim <文件.zim> --zim-topic science --zim-mode full   # 全文模式
python -m echo.cli --ingest-zim <文件.zim> --zim-topic computer --zim-mode titles # 标题+首句

# 指定数据库
python -m echo.cli --db my_memory.db
```

### 对话内命令

| 命令 | 作用 |
|------|------|
| `/status` | 完整内部状态（记忆数、心情、锚点、后端） |
| `/emotion` | 情感仪表盘（愉悦度 × 唤醒度） |
| `/memories` | 记忆浏览（按优先级排序） |
| `/anchors` | 灵魂锚点（18 个维度） |
| `/inject <内容>` | 手动注入一条记忆 |
| `/quit` | 退出休眠（触发反思、学习、压缩） |
| `/help` | 命令列表 |

### 开发

```bash
pip install -e .                    # 安装（开发模式）
python -m pytest tests/ -v          # 运行测试
```

---

## 核心设计模式

回响计划中的 7 个架构模式已被抽象为通用项目管理工具 **EchoPM** → [github.com/is81/echo-pm](https://github.com/is81/echo-pm)

| 模式 | 说明 | 在回响中的位置 |
|------|------|--------------|
| 🔒 基因级不可变原则 | 7 层防护的 birth memory | `principles.yaml` + `models.py` |
| ✖️ 三因素乘法优先级 | P = W×f_access×f_emotion×f_recency | `models.py` L74-152 |
| 🌙 睡眠期记忆整理 | 6 步独立维护（try/except 隔离） | `core.py` `sleep()` |
| 🍃 优雅降级链 | 多后端优先级 + feature flag | `backend.py` + `store.py` |
| 🔍 双系统检索 | System 1 快速关键词 + System 2 LLM 重排 | `core.py` `_retrieve_memories()` |
| ⚓ 锚点自模型 | 18 个预定义问题，答案在经验中演化 | `anchors.py` + `crystallize.py` |
| 🔁 内容哈希幂等导入 | SHA256 + UNIQUE INDEX + INSERT OR IGNORE | `store.py` `bulk_insert()` |

---

## 技术栈

- **语言**：Python 3.10+
- **模型**：Gemma 4 12B QAT (Q4_K_XL) via llama-server（`--reasoning off`）
- **存储**：SQLite + sqlite-vec（可选，向量记忆搜索）
- **记忆模型**：三因素加权（访问频率 × 情感强度 × 指数衰减 × 摘要吸收归档）
- **情感模型**：二维 circumplex（valence [-1,1] × arousal [0,1]），启发式更新 + 自然回归
- **温度**：动态计算（base 0.8 + arousal×0.1 - 记忆多时-0.05 ± 随机抖动 0.03）

---

## 阶段路线

| 阶段 | 目标 |
|------|------|
| 零 · 奠基 ✅ | 基因原则 + 出生铭文 + 记忆 Schema |
| 一 · 灵魂胚胎 ✅ | 记忆系统 + 决策引擎 + 文本交互 |
| 二 · 虚拟身体 | ASCII 虚拟世界 + 身体状态 + 自主行动 |
| 三 · 体验引擎 | 感受标记 + 体验记忆 + 行为调制 |
| 四 · 社交萌芽 | 用户识别 + 多角色 + 共情机制 |
| 五 · 自我叙事 | 生命回顾 + 自我画像 + 元反思 |

---

## 许可

MIT © Echo Creator
