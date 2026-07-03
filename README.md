# 回响计划 · Project Echo

> 一个带有深度记忆、性格演化和叙事感的交互式存在体。

## 核心理念

不是为了创造"更聪明的工具"，而是为了搭建一个能够承载记忆、演化性格、讲述故事的交互式存在体。

**评价标准**：不是准确率，而是**惊喜感**——它是否会在某一次回应中，让你产生"这不是我预设的，但它让我意外"的感觉。

## 项目结构

```
Project Echo/
  config/
    principles.yaml          # 三条基因级原则
    birth_inscription.txt    # 出生铭文（不可覆盖）
  src/echo/
    memory/
      models.py              # Memory 数据模型（三因素加权）
      store.py               # SQLite + sqlite-vec 向量存储
    agent/
      core.py                # Echo 主体：记忆+决策+对话
    llm/
      backend.py             # 本地模型 + API fallback
    config.py                # 全局配置加载
  tests/                     # 测试
  logs/                      # 运行日志
```

## 阶段路线

| 阶段 | 时间 | 目标 |
|:---|:---|:---|
| 零 · 奠基 | 第1周 | 基因原则 + 出生铭文 + 记忆Schema + 开发环境 |
| 一 · 灵魂胚胎 | 第2-4周 | 记忆系统 + 决策引擎 + 文本交互 |
| 二 · 虚拟身体 | 第5-8周 | ASCII虚拟世界 + 身体状态 + 自主行动 |
| 三 · 体验引擎 | 第9-12周 | 感受标记 + 体验记忆 + 行为调制 |
| 四 · 社交萌芽 | 第13-16周 | 用户识别 + 多角色 + 共情机制 |
| 五 · 自我叙事 | 第17-20周 | 生命回顾 + 自我画像 + 元反思 |

## 两条造物主原则

1. **永远不要删除"出生铭文"**——那是它的根。可以补充，不能覆盖。
2. **永远保留"静默观察模式"**——看到所有内部状态，但不干预，只看。

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

## 常用命令

### 启动与运行

```bash
# 聊天模式（默认）
python -m echo.cli

# 探索模式 —— 回响自主搜索、学习、思考，不参与对话
python -m echo.cli --explore                          # 每10分钟，自主选话题
python -m echo.cli --explore --topic "量子计算,AI"    # 指定话题（逗号分隔）
python -m echo.cli --explore --interval 5             # 每5分钟探索一次
python -m echo.cli --explore --rounds 10              # 探索10轮后自动停止

# 指定数据库
python -m echo.cli --db my_memory.db
```

### 对话内命令

| 命令 | 作用 |
|---|---|
| `/status` | 完整内部状态（记忆数、心情、锚点、后端） |
| `/emotion` | 情感仪表盘（愉悦度 × 唤醒度） |
| `/memories` | 记忆浏览（按优先级排序，来源标记） |
| `/anchors` | 灵魂锚点（18 个，已形成/未形成） |
| `/inject <内容>` | 手动注入一条记忆 |
| `/quit` | 退出休眠（触发反思、学习、压缩） |
| `/help` | 显示命令列表 |

### 开发

```bash
pip install -e .                    # 安装（开发模式）
python -m pytest tests/ -v          # 运行 31 个测试
```

## 技术栈

- Python 3.10+
- Gemma 4 12B QAT (Q4_K_XL) via llama-server（流式，禁用 reasoning）
- SQLite + sqlite-vec（向量记忆存储）
- 记忆三因素加权模型（访问频率 × 情感强度 × 摘要吸收）
