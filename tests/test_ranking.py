from src.app.retrieval.ranking import reciprocal_rank_fusion, tokenize


def test_rrf_rewards_results_present_in_both_rankings() -> None:
    assert reciprocal_rank_fusion([1, 2], [2, 3])[0] == 2
    assert tokenize("FastAPI's RAG-API!") == ["fastapi", "s", "rag", "api"]
