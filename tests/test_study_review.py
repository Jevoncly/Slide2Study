import json
import tempfile
import unittest
from pathlib import Path

from slide2study.models import Chunk, RenderedPage
from slide2study.study import build_chapter_study_guide
from slide2study.study_review import build_study_review_pack, stratified_section_sample


def guide(document_id: str, section: str, page: int):
    chunk = Chunk(
        f"{document_id}-{page}", document_id, page, page,
        f"{section} contains enough informative material for reliable review.",
        section=section, level="passage", metadata={"source_name": f"{document_id}.pdf"},
    )
    return build_chapter_study_guide([chunk], summary_bullets=1, flashcard_count=1)


class StudyReviewTests(unittest.TestCase):
    def test_stratified_sample_covers_documents_round_robin(self):
        guides = [guide("a", "A1", 1), guide("a", "A2", 2), guide("b", "B1", 1)]
        selected = stratified_section_sample(guides, 2)
        self.assertEqual({item.document_id for item in selected}, {"a", "b"})

    def test_review_pack_embeds_records_and_copies_evidence(self):
        selected = guide("deck", "Selection", 2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "page.png"
            image.write_bytes(b"page")
            page = RenderedPage("deck", 2, str(image), "deck.pdf", 100, 60, "sha")
            output = build_study_review_pack([selected], [page], root / "review")
            html = output.read_text(encoding="utf-8")
            data = json.loads(html.split('id="review-data">', 1)[1].split("</script>", 1)[0])
            self.assertEqual(data["records"][0]["review_id"], "study-review-001")
            self.assertIn("导出 JSONL", html)
            self.assertIn("课件原文解释", html)
            self.assertIn("基础题", html)
            self.assertIn("questions", data["records"][0])
            self.assertTrue((root / "review" / data["page_assets"]["deck:2"]).is_file())


if __name__ == "__main__":
    unittest.main()
