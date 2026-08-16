import unittest

from slide2study.generation import GroundedAnswerGenerator
from slide2study.generation_evaluation import evaluate_generation
from slide2study.models import Chunk, SearchResult


class StaticRetriever:
    def __init__(self, results):
        self.results = results

    def search(self, query, top_k=5):
        return self.results[:top_k]


class GenerationEvaluationTests(unittest.TestCase):
    def test_measures_valid_and_accurate_citations(self):
        chunk = Chunk("c1", "deck", 2, 2, "Lambda controls regularization strength.")
        metrics, diagnostics = evaluate_generation(
            GroundedAnswerGenerator(),
            StaticRetriever([SearchResult(chunk, 1.0, 1)]),
            [
                {
                    "id": "q1",
                    "query": "What controls regularization strength?",
                    "document_id": "deck",
                    "relevant_pages": [2],
                }
            ],
        )
        self.assertEqual(metrics.citation_validity, 1.0)
        self.assertEqual(metrics.citation_accuracy, 1.0)
        self.assertEqual(metrics.citation_coverage, 1.0)
        self.assertTrue(diagnostics[0]["has_accurate_citation"])

    def test_measures_correct_refusal_for_unanswerable_query(self):
        metrics, _ = evaluate_generation(
            GroundedAnswerGenerator(),
            StaticRetriever([]),
            [{"id": "n1", "query": "Unanswerable", "answerable": False}],
        )
        self.assertEqual(metrics.refusal_accuracy, 1.0)
        self.assertEqual(metrics.unanswerable_queries, 1)
        self.assertEqual(metrics.citation_validity, 1.0)


if __name__ == "__main__":
    unittest.main()
