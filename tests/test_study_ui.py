import json
import tempfile
import unittest
from pathlib import Path

from slide2study.models import Chunk, RenderedPage
from slide2study.study import build_chapter_study_guide
from slide2study.study_ui import build_study_ui


class StudyUiTests(unittest.TestCase):
    def test_builds_clickable_offline_ui_and_copies_only_cited_pages(self):
        chunks = [
            Chunk(
                chunk_id="c1",
                document_id="deck-1",
                page_start=2,
                page_end=2,
                text="Validation data selects model hyperparameters and thresholds.",
                section="Model Selection",
                level="passage",
                metadata={"source_name": "ML.pdf"},
            )
        ]
        guide = build_chapter_study_guide(chunks, summary_bullets=1, flashcard_count=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "page.png"
            image.write_bytes(b"fake-png")
            page = RenderedPage(
                document_id="deck-1",
                page_number=2,
                image_path=str(image),
                source_path="ML.pdf",
                width=1600,
                height=900,
                sha256="abc",
            )
            output = build_study_ui(guide, [page], root / "ui")
            html = output.read_text(encoding="utf-8")
            payload_text = html.split('id="study-data">', 1)[1].split("</script>", 1)[0]
            payload = json.loads(payload_text)

            self.assertIn("章节摘要", html)
            self.assertIn("闪卡练习", html)
            self.assertIn("page_assets", payload)
            copied = root / "ui" / payload["page_assets"]["2"]
            self.assertEqual(copied.read_bytes(), b"fake-png")
            self.assertNotIn(str(image), html)

    def test_rejects_missing_cited_page_preview(self):
        chunk = Chunk(
            "c1",
            "deck-1",
            2,
            2,
            "Validation data selects model hyperparameters and thresholds.",
            section="Model Selection",
            level="passage",
        )
        guide = build_chapter_study_guide([chunk], summary_bullets=1, flashcard_count=1)
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "Missing rendered page images"),
        ):
            build_study_ui(guide, [], Path(directory) / "ui")


if __name__ == "__main__":
    unittest.main()
