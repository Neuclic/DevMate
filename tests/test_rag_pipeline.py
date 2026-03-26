"""Tests for the LangChain-based RAG pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from langchain_core.embeddings import Embeddings

from devmate.config_loader import ModelSection, RagSection
from devmate.rag_pipeline import KnowledgeBasePipeline


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class KeywordEmbeddings(Embeddings):
    """Simple deterministic embeddings for local RAG tests."""

    KEYWORDS = ("trail", "map", "frontend", "fastapi", "docker")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(keyword)) for keyword in self.KEYWORDS]


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_rag_pipeline_uses_chroma_vector_search() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        docs_dir.mkdir()
        (docs_dir / "hiking.md").write_text(
            "Trail maps and route filters help users find nearby hiking paths.",
            encoding="utf-8",
        )
        (docs_dir / "backend.md").write_text(
            "FastAPI services expose health checks and deployment settings.",
            encoding="utf-8",
        )
        rag_settings = RagSection(
            provider="chromadb",
            collection_name="test-rag",
            persist_directory=".chroma/test-rag",
            chunk_size=120,
            chunk_overlap=20,
            top_k=2,
        )
        pipeline = KnowledgeBasePipeline(
            docs_dir=docs_dir,
            rag_settings=rag_settings,
            embeddings=KeywordEmbeddings(),
        )

        results = pipeline.search("trail map", limit=2)
        manifest_path = root / ".chroma" / "test-rag" / "manifest.json"
        manifest_exists = manifest_path.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert results
    assert results[0].source_name == "hiking.md"
    assert manifest_exists is True


def test_rag_pipeline_falls_back_when_embeddings_are_not_configured() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        docs_dir.mkdir()
        (docs_dir / "guide.md").write_text(
            "Frontend guidelines explain layout, map blocks, and trail cards.",
            encoding="utf-8",
        )
        rag_settings = RagSection(
            provider="chromadb",
            collection_name="test-rag-fallback",
            persist_directory=".chroma/test-rag-fallback",
            chunk_size=120,
            chunk_overlap=20,
            top_k=2,
        )
        model_settings = ModelSection(
            ai_base_url="https://api.minimax.io/v1",
            api_key="your_minimax_api_key_here",
            model_name="MiniMax-M2",
            embedding_base_url="",
            embedding_api_key="",
            embedding_model_name="",
        )
        pipeline = KnowledgeBasePipeline(
            docs_dir=docs_dir,
            rag_settings=rag_settings,
            model_settings=model_settings,
        )

        results = pipeline.search("trail map", limit=2)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert results
    assert results[0].source_name == "guide.md"
