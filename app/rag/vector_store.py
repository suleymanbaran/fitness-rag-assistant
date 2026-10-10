import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import Settings
from app.data_access.protocols import Protocol


def connect_qdrant(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url)
    return QdrantClient(path=settings.qdrant_path)


@dataclass(frozen=True)
class RetrievedChunk:
    protocol_id: str
    title: str
    category: str
    text: str
    score: float


def point_id(protocol_id: str) -> str:
    # Qdrant IDs must be integers or UUIDs. A UUID derived from the protocol ID is stable,
    # so re-ingesting overwrites the same point instead of creating duplicates.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, protocol_id))


class ProtocolStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self.client = client
        self.collection = collection

    def is_ready(self) -> bool:
        return self.client.collection_exists(self.collection) and self.count() > 0

    def count(self) -> int:
        return self.client.count(self.collection).count

    def recreate(self, vector_size: int) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert(self, protocols: list[Protocol], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(id=point_id(p.id), vector=vector, payload=p.model_dump())
            for p, vector in zip(protocols, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        category: str | None = None,
    ) -> list[RetrievedChunk]:
        query_filter = None
        if category is not None:
            query_filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])

        hits = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        ).points

        return [
            RetrievedChunk(
                protocol_id=hit.payload["id"],
                title=hit.payload["title"],
                category=hit.payload["category"],
                text=hit.payload["text"],
                score=hit.score,
            )
            for hit in hits
        ]
