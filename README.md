# DevMate

## Demo Runbook

Use this flow when you want one repeatable end-to-end demo:

1. Start the MCP server in Terminal 1:

```powershell
cd D:\DevMate
$env:UV_CACHE_DIR = ".uv-cache"
uv run devmate --serve-mcp
```

2. Validate the local configuration in Terminal 2:

```powershell
cd D:\DevMate
$env:UV_CACHE_DIR = ".uv-cache"
uv run devmate --config-check
```

Expected checkpoints:

- `MiniMax model configured: True`
- `Embedding configured: True`
- `Tavily configured: True`
- `LangSmith configured: True`

3. Run one planning demo:

```powershell
cd D:\DevMate
$env:UV_CACHE_DIR = ".uv-cache"
uv run devmate --prompt "build a responsive map website with map sdk best practices" --print-trace-url
```

4. Run one generation demo:

```powershell
cd D:\DevMate
$env:UV_CACHE_DIR = ".uv-cache"
uv run devmate --prompt "build a responsive map website with map sdk best practices" --generate --output-dir generated-output --print-trace-url
```

Expected output highlights:

- `Planning mode: llm`
- `Local knowledge sources: ...`
- `Matched skills: ...`
- `LangSmith trace URL: ...`
- `Generated output dir: generated-output`

`generated-output/` is ignored by Git and can be recreated for each demo run.

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
- MiniMax API Key

当前机器实际环境仍有缺口：

- 系统 Python 仍是 `3.10.9`
- 项目已经通过 `uv sync` 建好 `.venv`
- 当前项目虚拟环境使用的是 Python `3.13.9`

因此，这个仓库已经具备继续开发和联调的基础环境，但如果你要做系统级 Python 切换，仍然建议把本机默认 Python 也升级到 3.13。

## 建议启动顺序

1. 安装 Python 3.13
2. 安装 `uv`
3. 使用 `uv sync` 安装依赖
4. 填写 [config.toml](/D:/DevMate/config.toml)
5. 运行 `uv run devmate --prompt "帮我规划一个 FastAPI 服务"`

建议把真实密钥写到未跟踪的 `config.local.toml`，仓库内的 [config.toml](/D:/DevMate/config.toml) 保持占位模板即可。加载顺序是：先读 `config.toml`，如果存在 `config.local.toml`，再用本地配置覆盖同名字段。

当前默认模型配置已经切到 `MiniMax-M2`，并按 MiniMax 官方的 OpenAI 兼容接口模板设置了基础地址。国际站默认地址是 `https://api.minimax.io/v1`；如果你使用的是中国大陆站点，可以改成 `https://api.minimaxi.com/v1`。

## MCP 最小联调

MCP 搜索链路当前已经有最小实现，默认走 `Streamable HTTP + Tavily`。

1. 在 [config.toml](/D:/DevMate/config.toml) 里填好 `tavily_api_key`
2. 开一个终端启动 MCP server
3. 再开一个终端通过 MCP client 发起一次搜索

可调参数：

- `[search].default_max_results`
- `[search].request_timeout_seconds`
- `[mcp].tool_timeout_seconds`
- `[mcp].healthcheck_timeout_seconds`

启动 server：

```powershell
uv run devmate --serve-mcp
```

如果提示端口已占用，先关闭旧的 8001 端口进程，再重新启动 MCP server。

测试 client：

```powershell
uv run devmate --mcp-query "latest FastAPI release notes"
```

现在 `uv run devmate --prompt "..."` 这条路径也会尝试先走 MCP 搜索，再结合本地 RAG 结果生成摘要；如果 MCP server 不可用，它会记录 warning 并优雅降级，不会直接把 CLI 弄崩。

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
3. 当前默认技术路线为 `LangChain + MiniMax-M2 + Tavily + ChromaDB + LangSmith`

## 骨架说明

当前源码采用“平铺启动模块 + 预留目录”的方式：

- `src/devmate/*.py` 是当前可直接继续开发的骨架模块
- `src/devmate/agent`、`src/devmate/config`、`src/devmate/mcp`、`src/devmate/rag`、`src/devmate/skills` 是后续可以迁入正式实现的预留目录
