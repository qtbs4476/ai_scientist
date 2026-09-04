"""
Chroma 向量数据库服务
用于本地知识库检索
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from langchain_chroma import Chroma
# 百炼的 OpenAI 兼容模式对 embedding 接口不完全兼容（期望 input.contents 而非 input），
# 因此改用 dashscope 原生 SDK 的 LangChain 封装
from langchain_community.embeddings import DashScopeEmbeddings

# 加载项目根目录的 .env
import sys
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(_PROJECT_ROOT / ".env", override=True)

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "text-embedding-v1"


class ChromaService:
    """Chroma 向量库服务"""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        # 允许相对路径，但以项目根为基准
        default_path = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
        if not os.path.isabs(default_path):
            default_path = str(_PROJECT_ROOT / default_path)
        self.persist_directory = persist_directory or default_path

        # collection_name 解析优先级：
        #   1) 调用方显式传非空字符串（兼容旧代码 ChromaService(collection_name="xxx") 直接指定）
        #   2) 环境变量 CHROMA_COLLECTION_NAME（README 规范名，推荐）
        #   3) 环境变量 CHROMA_COLLECTION（向后兼容历史 .env）
        #   4) 兜底：knowledge_base
        if collection_name:
            resolved = collection_name
        else:
            resolved = (
                os.getenv("CHROMA_COLLECTION_NAME")
                or os.getenv("CHROMA_COLLECTION")
                or "knowledge_base"
            )
        self.collection_name = str(resolved).strip() or "knowledge_base"

        # 使用百炼 DashScope 原生 Embedding（避免 OpenAI 兼容模式的 input.contents 问题）
        api_key = (
            os.getenv("DASHSCOPE_API_KEY_EMBEDDING")
            or os.getenv("DASHSCOPE_API_KEY")
        )
        model = (
            os.getenv("QWEN_MODEL_EMBEDDING")
            or _DEFAULT_EMBEDDING_MODEL
        )
        self.embeddings = DashScopeEmbeddings(
            model=model,
            dashscope_api_key=api_key,
        )

        self.vector_store = None

    def load_or_create(self) -> Chroma:
        """加载或创建向量库"""
        if self.vector_store is None:
            os.makedirs(self.persist_directory, exist_ok=True)
            self.vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory,
            )
        return self.vector_store

    def similarity_search(
        self,
        query: str,
        k: int = 5
    ) -> List[Dict[str, Any]]:
        """相似度检索"""
        store = self.load_or_create()
        results = store.similarity_search_with_score(query, k=k)

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            }
            for doc, score in results
        ]

    def add_documents(self, texts: List[str], metadatas: List[Dict], batch_size: int = 20) -> None:
        """添加文档到向量库。

        按 batch_size（默认 20）分批写入，适配 DashScope embedding 批量上限
        （如 qwen3.7-text-embedding 单次最大 20 条 inputs）。超大文档也能安全入库。
        """
        store = self.load_or_create()
        for i in range(0, max(len(texts), 1), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size]
            if not batch_texts:
                continue
            store.add_texts(batch_texts, metadatas=batch_metas)
        # chromadb>=1.3.5 持久化由 PersistentClient 内部处理，无需手动 persist()

    def count_documents(self) -> int:
        """当前集合中的文档数（首次启动自动初始化知识库的判断依据）"""
        try:
            store = self.load_or_create()
            return int(store._collection.count())
        except Exception:
            return -1  # 无法判断时返回 -1，由调用方决定是否初始化

    def delete_collection(self) -> None:
        """删除集合"""
        if self.vector_store is not None:
            self.vector_store.delete_collection()
            self.vector_store = None