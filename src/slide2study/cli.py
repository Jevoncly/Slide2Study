from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from slide2study.chunking import CHUNK_LEVELS, HierarchicalChunker
from slide2study.evaluation import evaluate
from slide2study.io import load_chunks, read_jsonl, write_jsonl
from slide2study.parsing import build_parse_report, get_parser
from slide2study.retrieval import BM25Retriever
from slide2study.training import mine_hard_negatives


def _print_json(value: object, *, indent: int | None = None) -> None:
    """Keep Chinese output reliable on Windows terminals with a legacy code page."""
    payload = json.dumps(value, ensure_ascii=False, indent=indent)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(payload)


def _parse_levels(value: str) -> set[str]:
    levels = {level.strip() for level in value.split(",") if level.strip()}
    unknown = levels - CHUNK_LEVELS
    if not levels or unknown:
        expected = ",".join(sorted(CHUNK_LEVELS))
        raise argparse.ArgumentTypeError(f"levels must be a comma-separated subset of: {expected}")
    return levels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slide2study", description="Slide2Study retrieval baseline"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Parse and chunk a PDF, PPTX, TXT or Markdown file")
    ingest.add_argument("document", type=Path)
    ingest.add_argument("--output", type=Path, required=True)
    ingest.add_argument("--max-chars", type=int, default=500)
    ingest.add_argument("--overlap", type=int, default=1)

    inspect = commands.add_parser("inspect", help="Diagnose document extraction quality")
    inspect.add_argument("document", type=Path)
    inspect.add_argument("--pages-output", type=Path)
    inspect.add_argument("--low-text-threshold", type=int, default=40)

    search = commands.add_parser("search", help="Search a chunk corpus with BM25")
    search.add_argument("corpus", type=Path)
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--levels", type=_parse_levels, default=set(CHUNK_LEVELS))

    evaluation = commands.add_parser("evaluate", help="Evaluate BM25 on a JSONL QA set")
    evaluation.add_argument("corpus", type=Path)
    evaluation.add_argument("dataset", type=Path)
    evaluation.add_argument("--top-k", type=int, default=5)
    evaluation.add_argument("--levels", type=_parse_levels, default=set(CHUNK_LEVELS))

    mining = commands.add_parser("mine-negatives", help="Mine BM25 hard negatives for training")
    mining.add_argument("corpus", type=Path)
    mining.add_argument("dataset", type=Path)
    mining.add_argument("--output", type=Path, required=True)
    mining.add_argument("--top-k", type=int, default=20)
    mining.add_argument("--levels", type=_parse_levels, default=set(CHUNK_LEVELS))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        pages = get_parser(args.document).parse(args.document)
        if args.pages_output:
            write_jsonl((page.to_dict() for page in pages), args.pages_output)
        report = build_parse_report(pages, args.low_text_threshold).to_dict()
        if args.pages_output:
            report["pages_output"] = str(args.pages_output)
        _print_json(report, indent=2)
        return 0
    if args.command == "ingest":
        pages = get_parser(args.document).parse(args.document)
        chunks = HierarchicalChunker(args.max_chars, args.overlap).chunk(pages)
        write_jsonl((chunk.to_dict() for chunk in chunks), args.output)
        report = build_parse_report(pages).to_dict()
        level_counts = {
            level: sum(chunk.level == level for chunk in chunks) for level in sorted(CHUNK_LEVELS)
        }
        report.update(
            {"chunks": len(chunks), "chunk_levels": level_counts, "output": str(args.output)}
        )
        _print_json(report)
        return 0
    chunks = [chunk for chunk in load_chunks(args.corpus) if chunk.level in args.levels]
    retriever = BM25Retriever(chunks)
    if args.command == "search":
        results = retriever.search(args.query, args.top_k)
        _print_json([result.to_dict() for result in results], indent=2)
        return 0
    examples = list(read_jsonl(args.dataset))
    if args.command == "mine-negatives":
        triplets = mine_hard_negatives(retriever, examples, chunks, args.top_k)
        write_jsonl((triplet.to_dict() for triplet in triplets), args.output)
        _print_json({"triplets": len(triplets), "output": str(args.output)})
        return 0
    _print_json(evaluate(retriever, examples, args.top_k).to_dict(), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
