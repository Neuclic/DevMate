"""Shared heuristics for deciding when the agent should search the web."""

from __future__ import annotations


CURRENT_MARKERS = (
    "latest",
    "today",
    "recent",
    "current version",
    "current pricing",
    "current status",
    "new release",
    "release note",
    "release notes",
    "changelog",
    "version",
    "announcement",
    "pricing",
    "status",
    "security",
    "最新",
    "今天",
    "最近",
    "近期",
    "当前版本",
    "当前价格",
    "当前状态",
    "发布",
    "版本",
    "更新",
    "变更日志",
    "公告",
    "价格",
    "状态",
    "安全",
)

RECOMMENDATION_MARKERS = (
    "best practice",
    "best practices",
    "recommended",
    "recommendation",
    "compare",
    "comparison",
    "choose",
    "tradeoff",
    "tutorial",
    "example",
    "examples",
    "guide",
    "pattern",
    "patterns",
    "vs",
    "最佳实践",
    "推荐",
    "对比",
    "比较",
    "选型",
    "教程",
    "示例",
    "指南",
    "方案",
    "模式",
)

EXTERNAL_TECH_MARKERS = (
    "sdk",
    "api",
    "framework",
    "library",
    "package",
    "dependency",
    "integration",
    "deploy",
    "deployment",
    "hosting",
    "auth",
    "oauth",
    "payment",
    "map",
    "leaflet",
    "mapbox",
    "google maps",
    "browser game",
    "web game",
    "canvas",
    "react",
    "vue",
    "svelte",
    "next.js",
    "fastapi",
    "flask",
    "docker",
    "mcp",
    "rag",
    "接口",
    "框架",
    "库",
    "依赖",
    "集成",
    "接入",
    "部署",
    "托管",
    "鉴权",
    "认证",
    "支付",
    "地图",
    "网页游戏",
    "浏览器游戏",
    "游戏",
    "canvas",
    "前端",
    "后端",
    "react",
    "vue",
    "fastapi",
    "docker",
)

BUILD_MARKERS = (
    "build",
    "create",
    "generate",
    "make",
    "implement",
    "develop",
    "design",
    "prototype",
    "构建",
    "创建",
    "生成",
    "实现",
    "开发",
    "设计",
    "原型",
    "做一个",
    "写一个",
    "搭一个",
)

ARTIFACT_MARKERS = (
    "website",
    "web app",
    "site",
    "landing page",
    "dashboard",
    "game",
    "service",
    "agent",
    "tool",
    "plugin",
    "extension",
    "html",
    "css",
    "javascript",
    "frontend",
    "backend",
    "网页",
    "网站",
    "应用",
    "服务",
    "游戏",
    "工具",
    "插件",
    "扩展",
    "html",
    "css",
    "javascript",
    "js",
)


def should_search_web(prompt: str) -> bool:
    """Return whether a prompt should trigger a web lookup."""
    lowered = prompt.lower()
    if not lowered.strip():
        return False

    if any(marker in lowered for marker in CURRENT_MARKERS):
        return True

    if any(marker in lowered for marker in RECOMMENDATION_MARKERS):
        return True

    if any(marker in lowered for marker in EXTERNAL_TECH_MARKERS):
        return True

    if any(marker in lowered for marker in BUILD_MARKERS) and any(
        marker in lowered for marker in ARTIFACT_MARKERS
    ):
        return True

    return False
