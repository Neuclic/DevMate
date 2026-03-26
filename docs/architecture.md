# DevMate 架构草图

## 目标

DevMate 的目标是把“需求分析、查资料、读本地文档、生成代码、沉淀 Skills”串成一个完整闭环。

## 组件划分

### 1. CLI / Web UI

负责接收用户请求，向 Agent 传递高层意图。

### 2. Agent Runtime

负责：

- 判断当前请求是否需要搜索
- 决定什么时候查本地知识库
- 决定什么时候生成文件
- 决定什么时候记录 Skill

### 3. MCP Client

负责连接外部 MCP Server，并调用 `search_web` 等工具。

### 4. MCP Server

负责把 Tavily 搜索能力包装成一个标准化工具，供 Agent 使用。

### 5. RAG Pipeline

负责：

- 读取 `docs/`
- 切分文档
- 生成嵌入
- 存入向量库
- 按查询返回最相关片段

### 6. Skills Registry

负责记录成功任务模式，让 Agent 下次优先复用。

## 推荐开发顺序

1. 先做主入口和配置加载
2. 再做 MCP 搜索
3. 再做本地文档检索
4. 再把工具接回 Agent
5. 最后做 Docker 和交付包装
