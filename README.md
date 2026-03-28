# DevMate

DevMate 是一个基于 LangChain 的 AI 编程助手 demo，支持：

- MCP + Tavily 联网搜索
- 本地 RAG 文档检索
- Skills 保存、检索和复用
- 多文件项目规划、生成与修改
- LangSmith 可观测性
- React Web GUI
- Docker 一键启动

## 技术栈

- Python 3.13
- `uv`
- LangChain
- MCP (`Streamable HTTP`)
- Tavily
- Chroma / Embedding RAG
- FastAPI
- React 18 + TypeScript + Vite
- Docker Compose

## 本地启动

### 1. 同步 Python 依赖

```powershell
cd D:\DevMate
$env:UV_CACHE_DIR = ".uv-cache"
uv sync
```

### 2. 启动完整本地栈

```powershell
cd D:\DevMate
$env:UV_CACHE_DIR = ".uv-cache"
uv run devmate --serve-stack
```

这会同时启动：

- MCP: `http://localhost:8001/health`
- Web API: `http://127.0.0.1:8765`
- Frontend: `http://127.0.0.1:5173`

## Docker 启动

### 1. 准备环境变量

```powershell
cd D:\DevMate
Copy-Item compose.env.example .env
```

把 `.env` 里的这些值填好：

- `MINIMAX_API_KEY`
- `DASHSCOPE_API_KEY`
- `TAVILY_API_KEY`
- `LANGSMITH_API_KEY`（可选但推荐）

### 2. 启动

```powershell
cd D:\DevMate
docker compose up --build
```

启动后可访问：

- Frontend: `http://127.0.0.1:5173`
- Web API: `http://127.0.0.1:8765`

说明：

- `devmate-web` 和 `devmate-mcp` 使用 [config.docker.toml](/D:/DevMate/config.docker.toml)
- Docker 持久化目录包含：
  - `.skills`
  - `.sessions`
  - `.chroma`
  - `generated-output`
  - `docs`
  - `.runtime`

## 前端可用能力

当前 GUI 已支持：

- 会话管理与多轮上下文
- 实时流式规划 / 搜索 / 文件生成进度
- 文件树与文件内容预览
- Skills 浏览与导入
- 本地文档上传
- 前端界面填写 API Key
- 前端界面切换模型

设置页：

- [http://127.0.0.1:5173/settings](http://127.0.0.1:5173/settings)

Skills 页：

- [http://127.0.0.1:5173/skills](http://127.0.0.1:5173/skills)

## 演示流程

推荐用这条 prompt 演示完整链路：

```text
build a responsive map website with map sdk best practices
```

推荐验证点：

1. 右侧 `Context Panel` 出现规划步骤
2. 搜索结果中能看到本地文档 / web results / skills
3. 生成后文件树中出现多个文件
4. 文件预览能读到真实内容
5. 会话详情里能看到 LangSmith trace 链接

## 生成结果如何打开

如果生成了一个静态项目目录，例如：

- [generated-output](/D:/DevMate/generated-output)

最稳的查看方式是进入该目录后启动本地静态服务器：

```powershell
cd D:\DevMate\generated-output\<session-id>
python -m http.server 9001
```

然后浏览器打开：

- [http://127.0.0.1:9001](http://127.0.0.1:9001)

## LangSmith Trace

最近一次验证拿到的公开 trace 链接：

- [Shared Trace](https://smith.langchain.com/public/6f00f954-8343-4c22-a98e-6e86606d0fc1/r)

说明：

- 这条 trace 对应一次成功的端到端运行
- 运行中包含模型规划、本地 RAG、MCP web search 和最终响应写回

## 当前交付判断

按 [requirements.md](/D:/DevMate/requirements.md) 对照，当前已基本满足：

- `uv` 管理
- Python 3.13
- `config.toml` 配置化
- LangChain
- MCP + Tavily + Streamable HTTP
- RAG
- Skills
- Docker
- Web UI
- LangSmith

交付前最后建议：

1. 再跑一条成功 trace，替换 README 里的 trace 链接
2. 提交并推送最新代码

## 开发验证

后端测试：

```powershell
cd D:\DevMate
.\.venv\Scripts\python.exe -m pytest -q
```

前端构建：

```powershell
cd D:\DevMate\frontend
pnpm build
```
