"""Offline retrieval evaluation: does search return the protocols a question should get?

Hit rate@k: share of questions with at least one relevant protocol in the top k.
Recall@k:   share of each question's relevant protocols found in the top k, averaged.
MRR:        mean of 1 / rank of the first relevant protocol (0 if none is in the top k).
"""

import json
from dataclasses import dataclass
from pathlib import Path

from app.rag.embeddings import Embedder
from app.rag.vector_store import ProtocolStore

EVAL_PATH = Path(__file__).resolve().parents[2] / "data" / "eval_questions.json"


@dataclass(frozen=True)
class EvalCase:
    question: str
    relevant: list[str]


@dataclass(frozen=True)
class CaseResult:
    case: EvalCase
    retrieved: list[str]

    @property
    def hit(self) -> bool:
        return any(pid in self.case.relevant for pid in self.retrieved)

    @property
    def recall(self) -> float:
        return len(set(self.retrieved) & set(self.case.relevant)) / len(self.case.relevant)

    @property
    def reciprocal_rank(self) -> float:
        for rank, pid in enumerate(self.retrieved, start=1):
            if pid in self.case.relevant:
                return 1 / rank
        return 0.0


@dataclass(frozen=True)
class EvalReport:
    k: int
    results: list[CaseResult]

    @property
    def hit_rate(self) -> float:
        return sum(r.hit for r in self.results) / len(self.results)

    @property
    def recall(self) -> float:
        return sum(r.recall for r in self.results) / len(self.results)

    @property
    def mrr(self) -> float:
        return sum(r.reciprocal_rank for r in self.results) / len(self.results)

    def at(self, k: int) -> "EvalReport":
        """The same run cut to a smaller k, so one search at the largest k scores every k."""
        if k > self.k:
            raise ValueError(f"Report was retrieved with k={self.k}; cannot score k={k}")
        return EvalReport(k=k, results=[CaseResult(r.case, r.retrieved[:k]) for r in self.results])


def load_eval_cases(path: Path = EVAL_PATH) -> list[EvalCase]:
    return [EvalCase(**item) for item in json.loads(path.read_text())]


def evaluate_retrieval(embedder: Embedder, store: ProtocolStore, cases: list[EvalCase], k: int) -> EvalReport:
    query_vectors = embedder.embed([c.question for c in cases])
    results = [
        CaseResult(case=case, retrieved=[hit.protocol_id for hit in store.search(vector, top_k=k)])
        for case, vector in zip(cases, query_vectors, strict=True)
    ]
    return EvalReport(k=k, results=results)
