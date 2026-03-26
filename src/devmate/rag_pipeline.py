"""LangChain-based local document retrieval pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from devmate.config_loader import ModelSection, RagSection

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeSnippet:
    """A locally retrieved document snippet."""

    source_name: str
    excerpt: str
    score: float


class KnowledgeBasePipeline:
    """Retrieve local project knowledge with LangChain and Chroma."""

    def __init__(
        self,
        docs_dir: Path,
        rag_settings: RagSection | None = None,
        model_settings: ModelSection | None = None,
        embeddings: Embeddings | None = None,
    ) -> None:
        self.docs_dir = docs_dir
        self.rag_settings = rag_settings
        self.model_settings = model_settings
        self._embeddings = embeddings
        self._vector_store: Chroma | None = None
        self._vector_store_signature: str | None = None

    def search(self, query: str, limit: int = 3) -> list[KnowledgeSnippet]:
        """Search local documents with vector retrieval, then fallback to keywords."""
        if not query.strip() or not self.docs_dir.exists():
            return []

        if self._can_use_vector_retrieval():
            try:
                vector_store = self._get_vector_store()
                if vector_store is not None:
                    matches = vector_store.similarity_search_with_score(
                        query,
                        k=limit,
                    )
                    if matches:
                        return [
                            KnowledgeSnippet(
                                source_name=self._source_name(document),
                                excerpt=self._excerpt(document.page_content),
                                score=self._distance_to_score(score),
                            )
                            for document, score in matches
                        ]
            except Exception as exc:
                LOGGER.warning("Vector RAG lookup failed. Falling back to keyword search: %s", exc)

        return self._keyword_search(query, limit)

    def _can_use_vector_retrieval(self) -> bool:
        if self.rag_settings is None:
            return False
        if self._embeddings is not None:
            return True
        if self.model_settings is None:
            return False
        return self._embedding_model_is_configured()

    def _embedding_model_is_configured(self) -> bool:
        if self.model_settings is None:
            return False
        model_name = self.model_settings.embedding_model_name.strip()
        api_key = self._embedding_api_key().strip()
        base_url = self._embedding_base_url().strip()
        if not model_name or not api_key or not base_url:
            return False
        return not model_name.lower().startswith("your_")

    def _embedding_api_key(self) -> str:
        if self.model_settings is None:
            return ""
        return self.model_settings.embedding_api_key or self.model_settings.api_key

    def _embedding_base_url(self) -> str:
        if self.model_settings is None:
            return ""
        return self.model_settings.embedding_base_url or self.model_settings.ai_base_url

    def _get_embeddings(self) -> Embeddings:
        if self._embeddings is None:
            if self.model_settings is None:
                raise RuntimeError("Model settings are required for embedding-based retrieval.")
            self._embeddings = OpenAIEmbeddings(
                model=self.model_settings.embedding_model_name,
                api_key=self._embedding_api_key(),
                base_url=self._embedding_base_url(),
                timeout=30.0,
                max_retries=1,
                check_embedding_ctx_length=False,
            )
        return self._embeddings

    def _get_vector_store(self) -> Chroma | None:
        if self.rag_settings is None:
            return None

        persist_directory = self._persist_directory()
        manifest_path = persist_directory / "manifest.json"
        signature = self._document_signature()

        if self._vector_store is not None and self._vector_store_signature == signature:
            return self._vector_store

        if manifest_path.exists():
            manifest = self._read_manifest(manifest_path)
            if manifest.get("signature") == signature:
                self._vector_store = Chroma(
                    collection_name=self.rag_settings.collection_name,
                    embedding_function=self._get_embeddings(),
                    persist_directory=str(persist_directory),
                )
                self._vector_store_signature = signature
                return self._vector_store

        return self._rebuild_vector_store(
            persist_directory=persist_directory,
            manifest_path=manifest_path,
            signature=signature,
        )

    def _rebuild_vector_store(
        self,
        *,
        persist_directory: Path,
        manifest_path: Path,
        signature: str,
    ) -> Chroma | None:
        documents = self._load_documents()
        if not documents:
            LOGGER.info("No local documents found for RAG indexing in %s", self.docs_dir)
            return None

        chunks = self._split_documents(documents)
        if not chunks:
            LOGGER.info("No document chunks produced for RAG indexing in %s", self.docs_dir)
            return None

        shutil.rmtree(persist_directory, ignore_errors=True)
        persist_directory.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Rebuilding local RAG index collection='%s' docs=%d chunks=%d",
            self.rag_settings.collection_name,
            len(documents),
            len(chunks),
        )
        self._vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self._get_embeddings(),
            collection_name=self.rag_settings.collection_name,
            persist_directory=str(persist_directory),
        )

        manifest_path.write_text(
            json.dumps(
                {
                    "signature": signature,
                    "document_count": len(documents),
                    "chunk_count": len(chunks),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self._vector_store_signature = signature
        return self._vector_store

    def _persist_directory(self) -> Path:
        if self.rag_settings is None:
            raise RuntimeError("RAG settings are required for vector retrieval.")
        persist_directory = Path(self.rag_settings.persist_directory)
        if persist_directory.is_absolute():
            return persist_directory
        return self.docs_dir.parent / persist_directory

    def _read_manifest(self, manifest_path: Path) -> dict[str, object]:
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Unable to read RAG manifest at %s: %s", manifest_path, exc)
            return {}

    def _load_documents(self) -> list[Document]:
        documents: list[Document] = []
        for path in self._iter_document_paths():
            content = path.read_text(encoding="utf-8")
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "source_name": path.name,
                        "source_path": str(path.resolve()),
                    },
                )
            )
        return documents

    def _iter_document_paths(self) -> list[Path]:
        candidates = {
            path
            for pattern in ("*.md", "*.txt")
            for path in self.docs_dir.rglob(pattern)
            if path.is_file()
        }
        return sorted(candidates)

    def _split_documents(self, documents: list[Document]) -> list[Document]:
        if self.rag_settings is None:
            return documents
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.rag_settings.chunk_size,
            chunk_overlap=self.rag_settings.chunk_overlap,
        )
        return splitter.split_documents(documents)

    def _document_signature(self) -> str:
        if self.rag_settings is None:
            return "keyword-only"
        payload = [
            {
                "path": str(path.relative_to(self.docs_dir)) if path.is_relative_to(self.docs_dir) else path.name,
                "mtime_ns": path.stat().st_mtime_ns,
                "size": path.stat().st_size,
            }
            for path in self._iter_document_paths()
        ]
        raw = json.dumps(
            {
                "collection_name": self.rag_settings.collection_name,
                "chunk_size": self.rag_settings.chunk_size,
                "chunk_overlap": self.rag_settings.chunk_overlap,
                "documents": payload,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_name(document: Document) -> str:
        source_name = document.metadata.get("source_name")
        if isinstance(source_name, str) and source_name:
            return source_name
        source_path = document.metadata.get("source_path")
        if isinstance(source_path, str) and source_path:
            return Path(source_path).name
        return "unknown"

    @staticmethod
    def _excerpt(content: str) -> str:
        return " ".join(content.split())[:280]

    @staticmethod
    def _distance_to_score(distance: float) -> float:
        return max(0.0, 1.0 / (1.0 + float(distance)))

    def _keyword_search(self, query: str, limit: int = 3) -> list[KnowledgeSnippet]:
        terms = [term.lower() for term in query.split() if term.strip()]
        matches: list[KnowledgeSnippet] = []

        for path in self._iter_document_paths():
            content = path.read_text(encoding="utf-8")
            lowered = content.lower()
            score = float(sum(lowered.count(term) for term in terms))
            if score <= 0:
                continue
            matches.append(
                KnowledgeSnippet(
                    source_name=path.name,
                    excerpt=self._excerpt(content),
                    score=score,
                )
            )

        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]
