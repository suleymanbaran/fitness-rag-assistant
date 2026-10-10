import pytest
from qdrant_client import QdrantClient

from app.data_access.protocols import load_protocols
from app.rag.evaluation import CaseResult, EvalCase, EvalReport, evaluate_retrieval, load_eval_cases
from app.rag.ingestion import ingest_protocols
from app.rag.vector_store import ProtocolStore
from tests.fakes import FakeEmbedder


def result(relevant: list[str], retrieved: list[str]) -> CaseResult:
    return CaseResult(EvalCase("q", relevant), retrieved)


def test_case_metrics():
    r = result(["a", "b"], ["x", "b", "a"])
    assert r.hit
    assert r.recall == 1.0
    assert r.reciprocal_rank == 0.5

    miss = result(["a"], ["x", "y"])
    assert (miss.hit, miss.recall, miss.reciprocal_rank) == (False, 0.0, 0.0)


def test_report_averages_and_cuts_to_smaller_k():
    report = EvalReport(k=3, results=[result(["a"], ["a", "x", "y"]), result(["b"], ["x", "y", "b"])])
    assert report.hit_rate == 1.0
    assert report.mrr == pytest.approx((1 + 1 / 3) / 2)

    top1 = report.at(1)
    assert top1.hit_rate == 0.5
    assert top1.results[1].retrieved == ["x"]
    with pytest.raises(ValueError):
        report.at(5)


def test_eval_set_only_references_real_protocols():
    protocol_ids = {p.id for p in load_protocols()}
    cases = load_eval_cases()
    assert len(cases) >= 20
    for case in cases:
        assert case.relevant, case.question
        assert set(case.relevant) <= protocol_ids, case.question


def test_evaluate_retrieval_end_to_end_offline():
    embedder = FakeEmbedder()
    store = ProtocolStore(QdrantClient(":memory:"), "eval")
    ingest_protocols(embedder, store)

    report = evaluate_retrieval(embedder, store, load_eval_cases(), k=5)

    assert all(len(r.retrieved) == 5 for r in report.results)
    assert 0 < report.at(3).hit_rate <= report.hit_rate
