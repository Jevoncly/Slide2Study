import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from slide2study.cli import main as cli_main
from slide2study.dense import write_chunk_embedding_cache
from slide2study.generation import GeneratedDraft, GroundedAnswerGenerator
from slide2study.models import Chunk, SearchResult


def result(chunk_id: str, page: int, text: str, rank: int = 1) -> SearchResult:
    chunk = Chunk(
        chunk_id=chunk_id,
        document_id="deck-1",
        page_start=page,
        page_end=page,
        text=text,
        metadata={"source_name": "Lecture 2.pdf"},
    )
    return SearchResult(chunk=chunk, score=1.0 / rank, rank=rank)


class GroundedGenerationTests(unittest.TestCase):
    def test_extractive_answer_has_retrieved_page_citation(self):
        material = GroundedAnswerGenerator().generate(
            "What controls regularization strength?",
            [result("chunk-1", 7, "Lambda controls regularization strength.")],
        )
        self.assertFalse(material.refused)
        self.assertEqual(material.cited_pages, [7])
        self.assertIn("[Lecture 2.pdf, p.7]", material.content)
        self.assertEqual(material.citations[0].chunk_id, "chunk-1")

    def test_empty_retrieval_refuses_without_citations(self):
        material = GroundedAnswerGenerator().generate("unknown topic", [])
        self.assertTrue(material.refused)
        self.assertEqual(material.refusal_reason, "insufficient_evidence")
        self.assertEqual(material.citations, [])

    def test_single_generic_word_overlap_is_not_enough(self):
        material = GroundedAnswerGenerator().generate(
            "How long should sourdough bake?",
            [result("chunk-1", 9, "Long paths may have greater search cost.")],
        )
        self.assertTrue(material.refused)

    def test_unretrieved_citation_fails_closed(self):
        class UnsafeBackend:
            def generate(self, query, evidence):
                return GeneratedDraft("Unsupported answer", ("E999",))

        material = GroundedAnswerGenerator(UnsafeBackend()).generate(
            "question", [result("chunk-1", 2, "Evidence")]
        )
        self.assertTrue(material.refused)
        self.assertEqual(material.refusal_reason, "generator_cited_unretrieved_evidence")
        self.assertEqual(material.citations, [])

    def test_backend_cannot_embed_its_own_page_citation(self):
        class UnsafeBackend:
            def generate(self, query, evidence):
                return GeneratedDraft("Claim [Other.pdf, p.99]", ("E1",))

        material = GroundedAnswerGenerator(UnsafeBackend()).generate(
            "question", [result("chunk-1", 2, "Evidence for the question")]
        )
        self.assertTrue(material.refused)
        self.assertEqual(material.refusal_reason, "generator_embedded_unverified_citation")
        self.assertEqual(material.citations, [])

    def test_cli_answer_runs_retrieval_generation_loop(self):
        rows = [
            {
                "chunk_id": "chunk-1",
                "document_id": "deck-1",
                "page_start": 3,
                "page_end": 3,
                "text": "Validation data is used to select hyperparameters.",
                "metadata": {"source_name": "ML.pdf"},
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "chunks.jsonl"
            corpus.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_main(
                    ["answer", str(corpus), "What selects hyperparameters?", "--top-k", "1"]
                )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(payload["refused"])
        self.assertEqual(payload["cited_pages"], [3])
        self.assertEqual(payload["retrieved_chunk_ids"], ["chunk-1"])

    def test_cli_answer_can_use_cached_dense_retrieval(self):
        chunks = [
            Chunk("c1", "deck", 1, 1, "Unrelated search material."),
            Chunk("c2", "deck", 2, 2, "Lambda controls regularization strength."),
        ]

        class FakeEncoder:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode_queries(self, _queries):
                return [[0.0, 1.0]]

        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "chunks.jsonl"
            cache = Path(directory) / "dense.json"
            corpus.write_text(
                "\n".join(json.dumps(chunk.to_dict()) for chunk in chunks), encoding="utf-8"
            )
            write_chunk_embedding_cache(
                chunks,
                [[1.0, 0.0], [0.0, 1.0]],
                cache,
                "fake-model",
                "query: ",
                "passage: ",
            )
            stdout = io.StringIO()
            with (
                patch("slide2study.cli.SentenceTransformersTextEncoder", FakeEncoder),
                redirect_stdout(stdout),
            ):
                exit_code = cli_main(
                    [
                        "answer",
                        str(corpus),
                        "What controls regularization strength?",
                        "--retriever",
                        "dense",
                        "--dense-cache",
                        str(cache),
                        "--top-k",
                        "1",
                    ]
                )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["retriever"], "dense")
        self.assertEqual(payload["retrieved_chunk_ids"], ["c2"])
        self.assertEqual(payload["cited_pages"], [2])

if __name__ == "__main__":
    unittest.main()
