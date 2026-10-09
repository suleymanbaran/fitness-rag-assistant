from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.config import Settings, get_settings
from app.data.recovery_protocols import RECOVERY_PROTOCOLS, ProtocolDocument
from app.models.daily_biometrics import DailyBiometrics
from app.schemas.analyze import RetrievedProtocol


@dataclass(frozen=True)
class RAGService:
    settings: Settings
    embeddings: OpenAIEmbeddings
    qdrant_client: QdrantClient

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> RAGService:
        cfg = settings or get_settings()
        embeddings = OpenAIEmbeddings(
            model=cfg.embedding_model,
            api_key=cfg.openai_api_key or None,
        )
        client = QdrantClient(url=cfg.qdrant_url)
        return cls(settings=cfg, embeddings=embeddings, qdrant_client=client)

    def _vector_store(self) -> QdrantVectorStore:
        return QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=self.settings.qdrant_collection,
            embedding=self.embeddings,
        )

    def ensure_collection(self) -> None:
        if self.qdrant_client.collection_exists(self.settings.qdrant_collection):
            return
        vector_size = len(self.embeddings.embed_query("dimension probe"))
        self.qdrant_client.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def ingest_protocols(self, protocols: list[ProtocolDocument] | None = None) -> int:
        """Embed and upsert recovery protocols into Qdrant."""
        self.ensure_collection()
        source = protocols if protocols is not None else RECOVERY_PROTOCOLS
        documents = [
            Document(
                page_content=item["content"],
                metadata={
                    "protocol_id": item["id"],
                    "title": item["title"],
                    "category": item["category"],
                    "tags": ",".join(item["tags"]),
                },
            )
            for item in source
        ]
        QdrantVectorStore.from_documents(
            documents=documents,
            embedding=self.embeddings,
            url=self.settings.qdrant_url,
            collection_name=self.settings.qdrant_collection,
        )
        return len(documents)

    def seed_if_empty(self) -> int:
        """Load MVP corpus when the collection has no points."""
        self.ensure_collection()
        info = self.qdrant_client.get_collection(self.settings.qdrant_collection)
        if info.points_count and info.points_count > 0:
            return 0
        return self.ingest_protocols()

    @staticmethod
    def build_retrieval_query(user_query: str, biometrics: list[DailyBiometrics]) -> str:
        if not biometrics:
            return user_query

        latest = biometrics[0]
        lines = [
            user_query,
            "Recent biometric context:",
            f"- Date: {latest.recorded_on}",
        ]
        if latest.hrv_ms is not None:
            lines.append(f"- HRV: {latest.hrv_ms:.1f} ms")
        if latest.sleep_score is not None:
            lines.append(f"- Sleep score: {latest.sleep_score}/100")
        if latest.resting_heart_rate_bpm is not None:
            lines.append(f"- Resting HR: {latest.resting_heart_rate_bpm} bpm")
        if latest.weight_kg is not None:
            lines.append(f"- Weight: {latest.weight_kg:.1f} kg")
        if latest.calorie_intake_kcal is not None:
            lines.append(f"- Calorie intake: {latest.calorie_intake_kcal} kcal")

        if len(biometrics) > 1:
            prior = biometrics[1]
            if latest.hrv_ms is not None and prior.hrv_ms is not None and prior.hrv_ms > 0:
                delta_pct = ((latest.hrv_ms - prior.hrv_ms) / prior.hrv_ms) * 100
                lines.append(f"- HRV change vs prior day: {delta_pct:+.1f}%")

        return "\n".join(lines)

    def retrieve_protocols(
        self,
        user_query: str,
        biometrics: list[DailyBiometrics],
        top_k: int | None = None,
    ) -> list[RetrievedProtocol]:
        k = top_k or self.settings.rag_top_k
        retrieval_query = self.build_retrieval_query(user_query, biometrics)
        store = self._vector_store()
        hits = store.similarity_search_with_score(retrieval_query, k=k)

        protocols: list[RetrievedProtocol] = []
        for doc, score in hits:
            meta = doc.metadata
            protocols.append(
                RetrievedProtocol(
                    title=str(meta.get("title", "Unknown protocol")),
                    category=str(meta.get("category", "general")),
                    content=doc.page_content,
                    relevance_score=float(score),
                )
            )
        return protocols
