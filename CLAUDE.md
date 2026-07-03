# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

回响计划（Project Echo）——一个带有深度记忆、性格演化和叙事感的交互式 AI 存在体。不是工具，而是"存在体"的模拟。评价标准是"惊喜感"而非准确率。

## 常用命令

```bash
# 安装（开发模式）
pip install -e .

# 运行测试（20个）
python -m pytest tests/ -v

# 启动 llama-server（必须先启动，端口 8080）
llama-server -m <模型.gguf> --host 127.0.0.1 --port 8080 -c 8192 -ngl 99 --reasoning off

# 启动 CLI 对话
python -m echo.cli
```

## 架构

```
src/echo/
  agent/core.py      # Echo 主体：对话流程、记忆检索、情感状态、系统提示构建
  memory/
    models.py        # Memory 数据模型（三因素加权：访问频率+0.01 × 高唤醒度衰减减半 × 摘要吸收归档）
    store.py         # SQLite 持久化，sqlite-vec 可选，numpy 可选
  llm/backend.py     # OpenAI 兼容 API 调用（本地 llama-server 优先，云端 API fallback）
  config.py          # YAML 原则 + TXT 铭文加载
  cli.py             # 命令行交互（流式输出），/status /emotion /memories /inject 命令
config/
  principles.yaml    # 三条基因级原则（不可改写）
  birth_inscription.txt  # 出生铭文（19字，不可覆盖）
```

**数据流**: 用户输入 → `Echo.respond_stream()` → 记忆衰减/情感回归 → 关键词检索记忆 → 构建系统提示（原则+记忆+状态） → 动态 temperature → LLM 流式生成 → 存储新记忆 → 更新情感状态

**关键设计决策**:
- Memory 的 `source='birth'` 永不衰减、永不归档（SQL 层有 WHERE 防护）
- 情感状态是二维向量：valence [-1,1] × arousal [0,1]，每次交互后启发式更新、自然回归
- Temperature 动态计算：base 0.8 + arousal×0.1 - 记忆多时-0.05 + 随机抖动±0.03
- 每条记忆 `archived=True` 后权重降为 0.1（被摘要吸收），但原始数据不删除
- LLM 后端 `stream()` 返回 `(Iterator[str], str)` ——（token 迭代器, 模型名）
- `_NUMPY_AVAILABLE` 和 `_vec_available` 标志位控制可选依赖的优雅降级

**Gemma 4 QAT 注意事项**: 此模型默认开启 thinking mode，必须用 `--reasoning off` 启动 llama-server，否则每次回应前会先做 400+ token 内部推理（18秒延迟）。流式输出时 `enable_thinking: False` extra_body 也对 llama-server 无效，必须在服务端禁用。

## 开发环境约束

**网络环境**: 开发者位于中国内地，国外资源（PyPI、GitHub、DuckDuckGo 等）可能不可达或极慢。开发时必须：
- pip install 优先使用清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`
- 国外 API/服务只尝试一次，失败后立即切换到国内可用替代方案（Bing 搜索、百度搜索、国内 pip 镜像等）
- 新增依赖尽量零依赖或纯 Python 内置库，避免需要从国外下载大文件
- 搜索功能使用 `urllib` 内置库 + Bing/百度，不使用需要代理的 DuckDuckGo/Google
- 模型下载优先使用 hf-mirror.com 或 modelscope
