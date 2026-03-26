# DevMate

DevMate 是一个面向面试题的 AI 编程助手项目骨架。当前仓库已经完成本地 Git 初始化，并补齐了可继续开发的目录结构、配置入口、占位源码、Docker 骨架和中文项目计划。

## 当前目标

项目最终需要交付一个可以完成以下工作的 Agent：

- 接收自然语言需求
- 通过 MCP 调用 Tavily 做联网搜索
- 通过 RAG 检索本地文档
- 生成或修改多文件代码项目
- 记录并复用 Skills
- 通过 Docker 一键启动

## 当前状态

当前仓库是“开发起步版”，主要解决三个问题：

1. 仓库可被 Git 管理
2. 目录结构和入口文件已就位
3. 项目计划和实施顺序已经写清楚，便于继续开发

## 环境要求

- Python 3.13
- `uv`
- Docker Desktop
- Tavily API Key
- LangSmith 或 LangFuse 凭据
- OpenAI 兼容模型或 DeepSeek 兼容模型凭据

当前机器实际环境仍有缺口：

- 本机 Python 版本是 `3.10.9`
- 本机尚未安装 `uv`

因此，这个仓库目前适合继续补代码、补文档和整理结构，但要按题目正式开发，需要先把本机切到题目要求的环境。

## 建议启动顺序

1. 安装 Python 3.13
2. 安装 `uv`
3. 使用 `uv sync` 安装依赖
4. 填写 [config.toml](/D:/DevMate/config.toml)
5. 运行 `uv run devmate --prompt "帮我规划一个 FastAPI 服务"`

如果本机 `uv` 缓存目录权限有问题，可以临时改用项目内缓存目录：

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv run devmate
```

## 目录结构

```text
.
├─ .skills/
├─ docs/
├─ src/
│  └─ devmate/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ agent_runtime.py
│     ├─ config_loader.py
│     ├─ logging_config.py
│     ├─ main.py
│     ├─ mcp_client.py
│     ├─ mcp_server.py
│     ├─ rag_pipeline.py
│     └─ skill_registry.py
├─ tests/
├─ Dockerfile
├─ docker-compose.yml
├─ pyproject.toml
├─ config.toml
└─ 项目计划.md
```

## 关键文件

- [pyproject.toml](/D:/DevMate/pyproject.toml): Python 项目和依赖定义
- [config.toml](/D:/DevMate/config.toml): 项目配置模板
- [项目计划.md](/D:/DevMate/项目计划.md): 适合直接查看的中文计划
- [docs/architecture.md](/D:/DevMate/docs/architecture.md): 架构说明
- [docs/internal_frontend_guidelines.md](/D:/DevMate/docs/internal_frontend_guidelines.md): 用于后续 RAG 演示的样例文档

## 下一步

如果你要继续做这个项目，建议先做这三个动作：

1. 把本机环境升级到 Python 3.13 + `uv`
2. 按 [项目计划.md](/D:/DevMate/项目计划.md) 完成 Day 1 基础工程
3. 先选定技术路线为 `LangChain + Tavily + ChromaDB + LangSmith`

## 骨架说明

当前源码采用“平铺启动模块 + 预留目录”的方式：

- `src/devmate/*.py` 是当前可直接继续开发的骨架模块
- `src/devmate/agent`、`src/devmate/config`、`src/devmate/mcp`、`src/devmate/rag`、`src/devmate/skills` 是后续可以迁入正式实现的预留目录
