import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from slide2study.cli import main as cli_main
from slide2study.models import Chunk
from slide2study.study import build_chapter_study_guide, build_course_study_guides


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


def page_chunk(
    chunk_id: str,
    page: int,
    text: str,
    section: str,
    **metadata,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="deck-1",
        page_start=page,
        page_end=page,
        text=text,
        section=section,
        level="page",
        metadata={"source_name": "Lecture 3.pdf", **metadata},
    )


class OfflineStudyGuideTests(unittest.TestCase):
    def test_summary_and_flashcards_are_exactly_grounded(self):
        chunks = [
            passage("c1", 3, "Validation data: evidence used to select model hyperparameters."),
            passage("c2", 4, "Test data: evidence used for final generalization estimates."),
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
            self.assertTrue(card.front.startswith("What is "))
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

    def test_summary_excludes_ellipsis_and_truncated_content(self):
        chunks = [
            passage("c1", 3, "A complete definition includes all required conditions."),
            passage("c2", 4, "The optimal path has…"),
            passage("c3", 5, "A recurrence may reference f(x,...) in truncated source text."),
        ]

        guide = build_chapter_study_guide(chunks, summary_bullets=3, flashcard_count=1)

        self.assertEqual([item.text for item in guide.summary], [chunks[0].text])

    def test_summary_preserves_periods_and_rejects_dangling_sentences(self):
        chunks = [
            passage("c1", 3, "A complete sentence already has a period."),
            passage("c2", 4, "A complete slide bullet without punctuation"),
            passage("c3", 5, "The missing continuation is"),
            passage("c4", 6, "The number of answers we're trying"),
            passage("c5", 7, "When will this method converge"),
            passage("c6", 8, "S a b d p a c e p h f r q"),
            passage("c7", 9, "Gdb pq ceh a frfde r"),
        ]

        guide = build_chapter_study_guide(chunks, summary_bullets=4, flashcard_count=1)

        self.assertEqual(
            [item.text for item in guide.summary],
            [
                "A complete sentence already has a period.",
                "A complete slide bullet without punctuation.",
                "When will this method converge?",
            ],
        )

    def test_extracts_concepts_and_formula_evidence(self):
        chunks = [
            passage(
                "c1",
                3,
                "Value iteration: repeated Bellman updates until convergence. "
                "V(s) = max_a Q(s,a).",
            )
        ]
        guide = build_chapter_study_guide(chunks, summary_bullets=1, flashcard_count=2)

        self.assertTrue(guide.concepts)
        self.assertEqual(len(guide.formulas), 1)
        self.assertIn("V(s) =", guide.formulas[0].formula_text)
        self.assertEqual(guide.formulas[0].citation.page_start, 3)

    def test_builds_all_viable_sections_for_course_ui(self):
        chunks = [
            passage("c1", 1, "Validation data selects model hyperparameters.", "Validation"),
            passage("c2", 2, "Test data estimates final generalization.", "Testing"),
        ]

        guides = build_course_study_guides(chunks, summary_bullets=1, flashcard_count=1)

        self.assertEqual([guide.section for guide in guides], ["Validation", "Testing"])

    def test_uses_page_text_and_rejects_broken_urls_and_layout_phrases(self):
        section = "Introduction to Algorithms: 6.006"
        chunks = [
            passage(
                "damaged",
                1,
                "All CS188 materials are available at http://ai. Conquer Dynamic.",
                section,
            ),
            page_chunk(
                "page-1",
                1,
                "Introduction to Algorithms: 6.006\n"
                "All CS188 materials are available at http://ai.berkeley.edu.\n"
                "Decrease & Conquer\nDivide & Conquer\nDynamic Programming\n"
                "Dynamic programming: reuse overlapping subproblem solutions.",
                section,
            ),
        ]

        guide = build_chapter_study_guide(chunks, summary_bullets=2, flashcard_count=2)
        material_text = json.dumps(guide.to_dict())

        self.assertNotIn("http://ai", material_text)
        self.assertNotIn("Conquer Dynamic", material_text)
        self.assertIn("Dynamic programming", material_text)
        self.assertTrue(all(item.citation.chunk_id == "page-1" for item in guide.summary))

    def test_excludes_sparse_visual_captions_and_natural_language_equals(self):
        section = "MDPs"
        chunks = [
            passage("p1", 1, "Damaged fallback passage for section discovery.", section),
            page_chunk(
                "logo",
                1,
                "Reinforcement learning\nPhysical Intelligence, 2024",
                section,
                requires_vision=True,
            ),
            page_chunk(
                "content",
                2,
                "Policy = map of states to actions\n"
                "Utility = sum of discounted rewards a s s, a s,a,s’\n"
                "Value iteration: repeated Bellman updates until convergence.\n"
                "V(s) = max_a Q(s,a)",
                section,
            ),
        ]

        guide = build_chapter_study_guide(chunks, summary_bullets=2, flashcard_count=3)

        self.assertNotIn("Physical Intelligence", json.dumps(guide.to_dict()))
        self.assertEqual([item.formula_text for item in guide.formulas], ["V(s) = max_a Q(s,a)"])
        utility = next(item for item in guide.flashcards if item.front == "What is Utility?")
        self.assertEqual(utility.back, "sum of discounted rewards")

    def test_rejects_layout_labels_and_malformed_flashcard_terms(self):
        section = "Search"
        chunks = [
            passage("p1", 1, "Fallback passage for section discovery.", section),
            page_chunk(
                "content",
                2,
                "Problem 1: choose a path through the graph.\n"
                "Strategy: expand a node that you think is promising.\n"
                "This is a slide transition label.\n"
                "Heuristic: an estimate of the remaining cost to a goal.",
                section,
            ),
        ]

        guide = build_chapter_study_guide(chunks, summary_bullets=2, flashcard_count=4)

        self.assertEqual([item.term for item in guide.concepts], ["Heuristic"])
        self.assertEqual([item.front for item in guide.flashcards], ["What is Heuristic?"])

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
