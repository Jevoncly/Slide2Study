import unittest
from pathlib import Path

from slide2study.chunking import HierarchicalChunker
from slide2study.evaluation import evaluate
from slide2study.parsing import TextParser
from slide2study.retrieval import BM25Retriever, mixed_tokenize
from slide2study.training import mine_hard_negatives


ROOT = Path(__file__).resolve().parents[1]


class BaselineTests(unittest.TestCase):
    def setUp(self):
        pages = TextParser().parse(ROOT / "examples" / "sample_course.txt")
        self.chunks = HierarchicalChunker(max_chars=200).chunk(pages)

    def test_parses_four_pages_with_citations(self):
        self.assertEqual({chunk.page_start for chunk in self.chunks}, {1, 2, 3, 4})

    def test_chinese_tokenizer_has_bigrams(self):
        self.assertIn("正则", mixed_tokenize("正则化 L2"))
        self.assertIn("l2", mixed_tokenize("正则化 L2"))
        self.assertIn("λ", mixed_tokenize("L(θ)+λ||θ||²"))

    def test_bm25_retrieves_relevant_page(self):
        results = BM25Retriever(self.chunks).search("正则化如何限制模型复杂度", top_k=2)
        self.assertTrue(results)
        self.assertEqual(results[0].chunk.page_start, 2)

    def test_evaluation_metrics(self):
        examples = [{"query": "验证集选择什么", "relevant_pages": [3]}]
        summary = evaluate(BM25Retriever(self.chunks), examples, top_k=3)
        self.assertEqual(summary.recall_at_k, 1.0)
        self.assertEqual(summary.mrr, 1.0)

    def test_hard_negative_mining_excludes_positive(self):
        retriever = BM25Retriever(self.chunks)
        examples = [{"query": "模型评估 数据", "relevant_pages": [3]}]
        triplets = mine_hard_negatives(retriever, examples, self.chunks, top_k=4)
        positive_ids = {chunk.chunk_id for chunk in self.chunks if chunk.page_start == 3}
        self.assertTrue(triplets)
        self.assertTrue(all(item.negative_chunk_id not in positive_ids for item in triplets))


if __name__ == "__main__":
    unittest.main()
