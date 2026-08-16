import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from slide2study.cli import main as cli_main
from slide2study.models import Chunk
from slide2study.study import build_chapter_study_guide


def passage(chunk_id: str, page: int, text: str, section: str = "Model Selection") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="deck-1",
        page_start=page,
        page_end=page,
        text=text,
        section=section,
        level="passage",
        metadata={"source_name": "Lecture 3.pdf"},
    )


class OfflineStudyGuideTests(unittest.TestCase):
    def test_summary_and_flashcards_are_exactly_grounded(self):
        chunks = [
            passage("c1", 3, "Validation data selects model hyperparameters and thresholds."),
            passage("c2", 4, "Test data estimates final generalization after selection."),
        ]
        guide = build_chapter_study_guide(
            chunks, summary_bullets=2, flashcard_count=2
        )

        self.assertEqual(len(guide.summary), 2)
        self.assertEqual({item.citation.page_start for item in guide.summary}, {3, 4})
        self.assertTrue(all(item.text in chunks[index].text for index, item in enumerate(guide.summary)))
        self.assertEqual(len(guide.flashcards), 2)
        for card in guide.flashcards:
            self.assertIn(card.back.casefold(), card.evidence_text.casefold())
            self.assertIn("_____", card.front)
            self.assertEqual(card.citation.source_name, "Lecture 3.pdf")

    def test_multiple_sections_require_an_explicit_selection(self):
        chunks = [
            passage("c1", 1, "Validation data selects model hyperparameters.", "Validation"),
            passage("c2", 2, "Test data estimates final generalization.", "Testing"),
        ]
        with self.assertRaisesRegex(ValueError, "--section is required"):
            build_chapter_study_guide(chunks)

    def test_summary_excludes_legal_boilerplate(self):
        chunks = [
            passage("c1", 3, "A rational agent maximizes expected utility."),
            passage(
                "c2",
                4,
                "Pac-Man is a registered trademark, used here for educational purposes.",
            ),
        ]
        guide = build_chapter_study_guide(chunks, summary_bullets=2, flashcard_count=1)

        self.assertEqual([item.text for item in guide.summary], [chunks[0].text])

    def test_cli_writes_guide_and_end_to_end_latency(self):
        chunks = [
            passage("c1", 3, "Validation data selects model hyperparameters and thresholds."),
            passage("c2", 4, "Test data estimates final generalization after selection."),
        ]
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "chunks.jsonl"
            output = Path(directory) / "guide.json"
            corpus.write_text(
                "\n".join(json.dumps(chunk.to_dict()) for chunk in chunks), encoding="utf-8"
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "study-guide",
                        str(corpus),
                        "--summary-bullets",
                        "2",
                        "--flashcards",
                        "2",
                        "--output",
                        str(output),
                    ]
                )
            self.assertTrue(output.exists())

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "offline-extractive")
        self.assertGreaterEqual(payload["latency_ms"]["end_to_end"], 0)
        self.assertEqual(len(payload["summary"]), 2)


if __name__ == "__main__":
    unittest.main()
