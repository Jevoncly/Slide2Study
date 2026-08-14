import importlib.util
import tempfile
import unittest
from pathlib import Path

from slide2study.chunking import HierarchicalChunker, validate_chunk_hierarchy
from slide2study.evaluation import evaluate
from slide2study.models import Chunk, Page
from slide2study.parsing import PDFParser, PPTXParser, TextParser, build_parse_report
from slide2study.retrieval import BM25Retriever, mixed_tokenize
from slide2study.training import mine_hard_negatives


ROOT = Path(__file__).resolve().parents[1]


class BaselineTests(unittest.TestCase):
    def setUp(self):
        pages = TextParser().parse(ROOT / "examples" / "sample_course.txt")
        self.chunks = HierarchicalChunker(max_chars=200).chunk(pages)

    def test_parses_four_pages_with_citations(self):
        self.assertEqual({chunk.page_start for chunk in self.chunks}, {1, 2, 3, 4})

    def test_builds_three_level_cross_page_hierarchy(self):
        by_level = {
            level: [chunk for chunk in self.chunks if chunk.level == level]
            for level in ("section", "page", "passage")
        }
        self.assertEqual(len(by_level["section"]), 2)
        self.assertEqual(len(by_level["page"]), 4)
        self.assertEqual(len(by_level["passage"]), 4)
        self.assertEqual(
            [(chunk.page_start, chunk.page_end) for chunk in by_level["section"]],
            [(1, 3), (4, 4)],
        )
        by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        for parent in by_level["section"] + by_level["page"]:
            self.assertTrue(parent.child_ids)
            self.assertTrue(
                all(
                    by_id[child_id].parent_id == parent.chunk_id
                    for child_id in parent.child_ids
                )
            )

    def test_chunk_ids_are_stable(self):
        pages = TextParser().parse(ROOT / "examples" / "sample_course.txt")
        repeated = HierarchicalChunker(max_chars=200).chunk(pages)
        self.assertEqual(
            [chunk.chunk_id for chunk in self.chunks],
            [chunk.chunk_id for chunk in repeated],
        )

    def test_hierarchy_validator_detects_missing_parent(self):
        orphan = Chunk("orphan", "doc", 1, 1, "text", parent_id="missing")
        self.assertIn("missing parent", validate_chunk_hierarchy([orphan])[0])

    def test_old_chunk_json_remains_compatible(self):
        chunk = Chunk.from_dict(
            {
                "chunk_id": "legacy",
                "document_id": "doc",
                "page_start": 1,
                "page_end": 1,
                "text": "legacy corpus",
            }
        )
        self.assertEqual(chunk.level, "passage")
        self.assertEqual(chunk.child_ids, [])

    def test_chinese_tokenizer_has_bigrams(self):
        self.assertIn("正则", mixed_tokenize("正则化 L2"))
        self.assertIn("l2", mixed_tokenize("正则化 L2"))
        self.assertIn("λ", mixed_tokenize("L(θ)+λ||θ||²"))

    def test_bm25_retrieves_relevant_page(self):
        results = BM25Retriever(self.chunks).search("正则化如何限制模型复杂度", top_k=2)
        self.assertTrue(results)
        self.assertEqual(results[0].chunk.page_start, 2)

    def test_bm25_level_weights_favor_precise_passages(self):
        chunks = [
            Chunk("section", "doc", 1, 1, "gradient descent", level="section"),
            Chunk("page", "doc", 1, 1, "gradient descent", level="page"),
            Chunk("passage", "doc", 1, 1, "gradient descent", level="passage"),
        ]
        results = BM25Retriever(chunks).search("gradient descent", top_k=3)
        self.assertEqual([result.chunk.level for result in results], ["passage", "page", "section"])

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

    def test_parse_report_flags_pages_that_need_vision(self):
        pages = [
            Page("deck", 1, "A complete text page " * 5),
            Page("deck", 2, "", metadata={"image_count": 2}),
            Page("deck", 3, "short", metadata={"image_count": 1}),
        ]
        report = build_parse_report(pages, low_text_threshold=20)
        self.assertEqual(report.empty_pages, [2])
        self.assertEqual(report.low_text_pages, [3])
        self.assertEqual(report.requires_vision_pages, [2, 3])
        self.assertAlmostEqual(report.to_dict()["text_coverage"], 2 / 3, places=6)

    @unittest.skipUnless(importlib.util.find_spec("pptx"), "python-pptx is not installed")
    def test_pptx_parser_extracts_title_and_table(self):
        from pptx import Presentation
        from pptx.util import Inches

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lecture.pptx"
            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[5])
            slide.shapes.title.text = "Optimization"
            table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(5), Inches(2)).table
            table.cell(0, 0).text = "Method"
            table.cell(0, 1).text = "Rate"
            table.cell(1, 0).text = "SGD"
            table.cell(1, 1).text = "O(1/t)"
            deck.save(path)
            page = PPTXParser().parse(path)[0]
        self.assertEqual(page.title, "Optimization")
        self.assertIn("Method | Rate", page.text)
        self.assertIn("SGD | O(1/t)", page.text)
        self.assertTrue(any(block["type"] == "table" for block in page.metadata["blocks"]))

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf is not installed")
    def test_pdf_parser_records_page_geometry(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with path.open("wb") as stream:
                writer.write(stream)
            page = PDFParser().parse(path)[0]
        self.assertEqual(page.metadata["width_points"], 612.0)
        self.assertEqual(page.metadata["height_points"], 792.0)


if __name__ == "__main__":
    unittest.main()
