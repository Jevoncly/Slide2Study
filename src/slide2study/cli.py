from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from slide2study.chunking import CHUNK_LEVELS, HierarchicalChunker
from slide2study.dense import (
    SentenceTransformersTextEncoder,
    load_chunk_embedding_cache,
    write_chunk_embedding_cache,
)
from slide2study.evaluation import (
    DATASET_SPLITS,
    QUESTION_TYPES,
    compare_page_retrievers,
    compare_retrievers,
    evaluate,
    evaluate_page_retrieval,
    evaluate_routed_page_retrieval,
    validate_dataset,
)
from slide2study.fusion import (
    BM25PageRetriever,
    ChunkPageRetriever,
    ReciprocalRankFusionChunkRetriever,
    ReciprocalRankFusionRetriever,
)
from slide2study.io import load_chunks, read_jsonl, write_jsonl
from slide2study.negative_review import apply_negative_reviews, build_negative_review_pack
from slide2study.parsing import build_parse_report, get_parser
from slide2study.reranking import (
    CrossEncoderReranker,
    RerankedRetriever,
    build_reranker_pairs,
    train_cross_encoder,
)
from slide2study.retrieval import BM25Retriever, DenseRetriever
from slide2study.review import build_review_pack
from slide2study.training import mine_hard_negatives
from slide2study.vision import (
    SentenceTransformersCLIPEncoder,
    VisualPageRetriever,
    load_page_embedding_cache,
    load_page_manifest,
    render_document,
    write_page_embedding_cache,
    write_page_manifest,
)


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


def _parse_route(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("route must use QUESTION_TYPE=SYSTEM")
    question_type, system = (part.strip() for part in value.split("=", 1))
    if question_type not in QUESTION_TYPES:
        expected = ",".join(sorted(QUESTION_TYPES))
        raise argparse.ArgumentTypeError(f"route question type must be one of: {expected}")
    systems = {"bm25_page", "dense_page", "clip_page", "dense_clip_rrf"}
    if system not in systems:
        expected = ",".join(sorted(systems))
        raise argparse.ArgumentTypeError(f"route system must be one of: {expected}")
    return question_type, system


def _expand_paths(values: list[Path]) -> list[Path]:
    expanded = []
    for value in values:
        if any(character in value.name for character in "*?["):
            matches = sorted(value.parent.glob(value.name))
            if not matches:
                raise FileNotFoundError(f"No files match: {value}")
            expanded.extend(matches)
        else:
            expanded.append(value)
    return expanded


def _load_rendered_pages(manifests: list[Path]):
    pages = [page for manifest in _expand_paths(manifests) for page in load_page_manifest(manifest)]
    keys = [(page.document_id, page.page_number) for page in pages]
    if len(keys) != len(set(keys)):
        raise ValueError("Rendered page manifests contain duplicate document/page entries")
    return pages


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

    ingest_corpus = commands.add_parser(
        "ingest-corpus", help="Parse multiple documents into one searchable corpus"
    )
    ingest_corpus.add_argument("documents", nargs="+", type=Path)
    ingest_corpus.add_argument("--output", type=Path, required=True)
    ingest_corpus.add_argument("--max-chars", type=int, default=500)
    ingest_corpus.add_argument("--overlap", type=int, default=1)

    inspect = commands.add_parser("inspect", help="Diagnose document extraction quality")
    inspect.add_argument("document", type=Path)
    inspect.add_argument("--pages-output", type=Path)
    inspect.add_argument("--low-text-threshold", type=int, default=40)

    render = commands.add_parser(
        "render-pages", help="Render PDF/PPTX pages and write a page-image manifest"
    )
    render.add_argument("document", type=Path)
    render.add_argument("--output-dir", type=Path, required=True)
    render.add_argument("--manifest", type=Path)
    render.add_argument("--dpi", type=int, default=144)
    render.add_argument("--pdftoppm", type=Path)
    render.add_argument("--soffice", type=Path)

    visual_search = commands.add_parser(
        "visual-search", help="Retrieve rendered pages with a CLIP baseline"
    )
    visual_search.add_argument("manifest", type=Path)
    visual_search.add_argument("query")
    visual_search.add_argument("--top-k", type=int, default=5)
    visual_search.add_argument("--model", default="clip-ViT-B-32")
    visual_search.add_argument("--device")
    visual_search.add_argument("--batch-size", type=int, default=16)
    visual_search.add_argument("--only-vision", action="store_true")

    visual_index = commands.add_parser(
        "visual-index", help="Encode rendered pages once and save a verified CLIP cache"
    )
    visual_index.add_argument("--manifests", nargs="+", type=Path, required=True)
    visual_index.add_argument("--output", type=Path, required=True)
    visual_index.add_argument("--model", default="clip-ViT-B-32")
    visual_index.add_argument("--device")
    visual_index.add_argument("--batch-size", type=int, default=16)

    visual_evaluation = commands.add_parser(
        "visual-evaluate", help="Evaluate cached CLIP query-to-page retrieval"
    )
    visual_evaluation.add_argument("corpus", type=Path)
    visual_evaluation.add_argument("dataset", type=Path)
    visual_evaluation.add_argument("--manifests", nargs="+", type=Path, required=True)
    visual_evaluation.add_argument("--cache", type=Path, required=True)
    visual_evaluation.add_argument("--model")
    visual_evaluation.add_argument("--device")
    visual_evaluation.add_argument("--batch-size", type=int, default=16)
    visual_evaluation.add_argument("--top-k", type=int, default=5)
    visual_evaluation.add_argument("--split", choices=sorted(DATASET_SPLITS))
    visual_evaluation.add_argument("--output", type=Path)

    hybrid_evaluation = commands.add_parser(
        "hybrid-evaluate", help="Compare BM25, cached CLIP and reciprocal-rank fusion"
    )
    hybrid_evaluation.add_argument("corpus", type=Path)
    hybrid_evaluation.add_argument("dataset", type=Path)
    hybrid_evaluation.add_argument("--manifests", nargs="+", type=Path, required=True)
    hybrid_evaluation.add_argument("--cache", type=Path, required=True)
    hybrid_evaluation.add_argument("--model")
    hybrid_evaluation.add_argument("--device")
    hybrid_evaluation.add_argument("--batch-size", type=int, default=16)
    hybrid_evaluation.add_argument("--levels", type=_parse_levels, default={"passage"})
    hybrid_evaluation.add_argument("--top-k", type=int, default=5)
    hybrid_evaluation.add_argument("--candidate-k", type=int, default=50)
    hybrid_evaluation.add_argument("--diagnostic-k", type=int, default=10)
    hybrid_evaluation.add_argument("--rrf-k", type=int, default=60)
    hybrid_evaluation.add_argument("--bm25-weight", type=float, default=1.0)
    hybrid_evaluation.add_argument("--visual-weight", type=float, default=1.0)
    hybrid_evaluation.add_argument("--split", choices=sorted(DATASET_SPLITS))
    hybrid_evaluation.add_argument("--output", type=Path)

    type_aware = commands.add_parser(
        "type-aware-evaluate",
        help="Compare page retrievers and evaluate explicit question-type routing",
    )
    type_aware.add_argument("corpus", type=Path)
    type_aware.add_argument("dataset", type=Path)
    type_aware.add_argument("--manifests", nargs="+", type=Path, required=True)
    type_aware.add_argument("--dense-cache", type=Path, required=True)
    type_aware.add_argument("--visual-cache", type=Path, required=True)
    type_aware.add_argument("--dense-model")
    type_aware.add_argument("--visual-model")
    type_aware.add_argument("--device")
    type_aware.add_argument("--dense-batch-size", type=int, default=32)
    type_aware.add_argument("--visual-batch-size", type=int, default=16)
    type_aware.add_argument("--levels", type=_parse_levels, default={"passage"})
    type_aware.add_argument("--top-k", type=int, default=5)
    type_aware.add_argument("--candidate-k", type=int, default=50)
    type_aware.add_argument("--diagnostic-k", type=int, default=10)
    type_aware.add_argument("--rrf-k", type=int, default=60)
    type_aware.add_argument("--dense-weight", type=float, default=1.0)
    type_aware.add_argument("--visual-weight", type=float, default=1.0)
    type_aware.add_argument(
        "--route",
        action="append",
        type=_parse_route,
        default=[],
        metavar="QUESTION_TYPE=SYSTEM",
        help="Override the default dense_page route for one question type",
    )
    type_aware.add_argument("--split", choices=sorted(DATASET_SPLITS))
    type_aware.add_argument("--output", type=Path)

    dense_index = commands.add_parser(
        "dense-index", help="Encode text chunks once and save a verified vector cache"
    )
    dense_index.add_argument("corpus", type=Path)
    dense_index.add_argument("--output", type=Path, required=True)
    dense_index.add_argument("--model", default="intfloat/multilingual-e5-small")
    dense_index.add_argument("--device")
    dense_index.add_argument("--batch-size", type=int, default=32)
    dense_index.add_argument("--levels", type=_parse_levels, default={"passage"})
    dense_index.add_argument("--query-prefix", default="query: ")
    dense_index.add_argument("--document-prefix", default="passage: ")

    dense_evaluation = commands.add_parser(
        "dense-evaluate", help="Evaluate cached dense text retrieval"
    )
    dense_evaluation.add_argument("corpus", type=Path)
    dense_evaluation.add_argument("dataset", type=Path)
    dense_evaluation.add_argument("--cache", type=Path, required=True)
    dense_evaluation.add_argument("--model")
    dense_evaluation.add_argument("--device")
    dense_evaluation.add_argument("--batch-size", type=int, default=32)
    dense_evaluation.add_argument("--levels", type=_parse_levels, default={"passage"})
    dense_evaluation.add_argument("--top-k", type=int, default=5)
    dense_evaluation.add_argument("--split", choices=sorted(DATASET_SPLITS))
    dense_evaluation.add_argument("--output", type=Path)

    text_hybrid = commands.add_parser(
        "text-hybrid-evaluate", help="Compare BM25, cached Dense and chunk-level RRF"
    )
    text_hybrid.add_argument("corpus", type=Path)
    text_hybrid.add_argument("dataset", type=Path)
    text_hybrid.add_argument("--cache", type=Path, required=True)
    text_hybrid.add_argument("--model")
    text_hybrid.add_argument("--device")
    text_hybrid.add_argument("--batch-size", type=int, default=32)
    text_hybrid.add_argument("--levels", type=_parse_levels, default={"passage"})
    text_hybrid.add_argument("--top-k", type=int, default=5)
    text_hybrid.add_argument("--candidate-k", type=int, default=50)
    text_hybrid.add_argument("--diagnostic-k", type=int, default=10)
    text_hybrid.add_argument("--rrf-k", type=int, default=60)
    text_hybrid.add_argument("--bm25-weight", type=float, default=1.0)
    text_hybrid.add_argument("--dense-weight", type=float, default=1.0)
    text_hybrid.add_argument("--split", choices=sorted(DATASET_SPLITS))
    text_hybrid.add_argument("--output", type=Path)

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
    evaluation.add_argument("--output", type=Path, help="Save config and metrics as JSON")
    evaluation.add_argument(
        "--split", choices=sorted(DATASET_SPLITS), help="Evaluate only one dataset split"
    )
    evaluation.add_argument(
        "--strict-dataset",
        action="store_true",
        help="Require every example to have a supported question_type",
    )

    validation = commands.add_parser(
        "validate-dataset", help="Validate a retrieval evaluation JSONL file"
    )
    validation.add_argument("dataset", type=Path)
    validation.add_argument("--corpus", type=Path, help="Verify labels against a chunk corpus")
    validation.add_argument(
        "--strict",
        action="store_true",
        help="Require every example to have a supported question_type",
    )

    review = commands.add_parser(
        "build-review-pack", help="Build a private HTML workflow for reviewing candidate QA"
    )
    review.add_argument("corpus", type=Path)
    review.add_argument("dataset", type=Path)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument(
        "--manifests", nargs="*", type=Path, default=[], help="Rendered page manifests"
    )

    mining = commands.add_parser("mine-negatives", help="Mine BM25 hard negatives for training")
    mining.add_argument("corpus", type=Path)
    mining.add_argument("dataset", type=Path)
    mining.add_argument("--output", type=Path, required=True)
    mining.add_argument("--top-k", type=int, default=20)
    mining.add_argument("--levels", type=_parse_levels, default=set(CHUNK_LEVELS))

    dense_mining = commands.add_parser(
        "dense-mine-negatives", help="Mine cached Dense hard negatives for training"
    )
    dense_mining.add_argument("corpus", type=Path)
    dense_mining.add_argument("dataset", type=Path)
    dense_mining.add_argument("--cache", type=Path, required=True)
    dense_mining.add_argument("--output", type=Path, required=True)
    dense_mining.add_argument("--model")
    dense_mining.add_argument("--device")
    dense_mining.add_argument("--batch-size", type=int, default=32)
    dense_mining.add_argument("--levels", type=_parse_levels, default={"passage"})
    dense_mining.add_argument("--top-k", type=int, default=20)
    dense_mining.add_argument("--split", choices=sorted(DATASET_SPLITS), default="train")
    dense_mining.add_argument("--hard-per-query", type=int)
    dense_mining.add_argument("--medium-per-query", type=int)
    dense_mining.add_argument("--easy-per-query", type=int)

    negative_review = commands.add_parser(
        "build-negative-review-pack", help="Build a private HTML review workflow for triplets"
    )
    negative_review.add_argument("corpus", type=Path)
    negative_review.add_argument("triplets", type=Path)
    negative_review.add_argument("--output", type=Path, required=True)

    apply_reviews = commands.add_parser(
        "apply-negative-reviews", help="Filter reviewed negatives into training triplets"
    )
    apply_reviews.add_argument("reviews", type=Path)
    apply_reviews.add_argument("--output", type=Path, required=True)
    apply_reviews.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Filter valid negatives even when pending or uncertain rows remain",
    )

    train_reranker = commands.add_parser(
        "train-reranker", help="Fine-tune a cross-encoder from reviewed triplets"
    )
    train_reranker.add_argument("corpus", type=Path)
    train_reranker.add_argument("triplets", type=Path)
    train_reranker.add_argument("--output-dir", type=Path, required=True)
    train_reranker.add_argument("--model", default="intfloat/multilingual-e5-small")
    train_reranker.add_argument("--device")
    train_reranker.add_argument("--batch-size", type=int, default=8)
    train_reranker.add_argument("--epochs", type=int, default=1)
    train_reranker.add_argument("--learning-rate", type=float, default=2e-5)
    train_reranker.add_argument("--seed", type=int, default=42)
    train_reranker.add_argument("--local-files-only", action="store_true")

    reranker_evaluation = commands.add_parser(
        "reranker-evaluate", help="Evaluate Dense candidates reordered by a cross-encoder"
    )
    reranker_evaluation.add_argument("corpus", type=Path)
    reranker_evaluation.add_argument("dataset", type=Path)
    reranker_evaluation.add_argument("--cache", type=Path, required=True)
    reranker_evaluation.add_argument("--reranker", type=Path, required=True)
    reranker_evaluation.add_argument("--model")
    reranker_evaluation.add_argument("--device")
    reranker_evaluation.add_argument("--batch-size", type=int, default=32)
    reranker_evaluation.add_argument("--levels", type=_parse_levels, default={"passage"})
    reranker_evaluation.add_argument("--top-k", type=int, default=5)
    reranker_evaluation.add_argument("--candidate-k", type=int, default=20)
    reranker_evaluation.add_argument("--split", choices=sorted(DATASET_SPLITS), default="dev")
    reranker_evaluation.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "render-pages":
        parsed_pages = get_parser(args.document).parse(args.document)
        rendered_pages = render_document(
            args.document,
            args.output_dir,
            dpi=args.dpi,
            pdftoppm_executable=args.pdftoppm,
            soffice_executable=args.soffice,
            page_metadata={page.page_number: page.metadata for page in parsed_pages},
        )
        manifest = args.manifest or args.output_dir / f"{args.document.stem}.jsonl"
        write_page_manifest(rendered_pages, manifest)
        _print_json(
            {
                "document_id": rendered_pages[0].document_id if rendered_pages else None,
                "rendered_pages": len(rendered_pages),
                "requires_vision_pages": sum(page.requires_vision for page in rendered_pages),
                "output_dir": str(args.output_dir),
                "manifest": str(manifest),
            },
            indent=2,
        )
        return 0
    if args.command == "visual-search":
        rendered_pages = load_page_manifest(args.manifest)
        if args.only_vision:
            rendered_pages = [page for page in rendered_pages if page.requires_vision]
        if not rendered_pages:
            raise ValueError("The page manifest has no eligible pages")
        encoder = SentenceTransformersCLIPEncoder(args.model, args.device, args.batch_size)
        results = VisualPageRetriever(rendered_pages, encoder).search(args.query, args.top_k)
        _print_json([result.to_dict() for result in results], indent=2)
        return 0
    if args.command == "visual-index":
        rendered_pages = _load_rendered_pages(args.manifests)
        if not rendered_pages:
            raise ValueError("The page manifests contain no pages")
        encoder = SentenceTransformersCLIPEncoder(args.model, args.device, args.batch_size)
        embeddings = encoder.encode_pages([page.image_path for page in rendered_pages])
        write_page_embedding_cache(rendered_pages, embeddings, args.output, args.model)
        _print_json(
            {
                "model": args.model,
                "pages": len(rendered_pages),
                "dimensions": len(embeddings[0]) if embeddings else 0,
                "output": str(args.output),
            },
            indent=2,
        )
        return 0
    if args.command == "visual-evaluate":
        rendered_pages = _load_rendered_pages(args.manifests)
        embeddings, cached_model = load_page_embedding_cache(
            rendered_pages, args.cache, args.model
        )
        model_name = args.model or cached_model
        encoder = SentenceTransformersCLIPEncoder(model_name, args.device, args.batch_size)
        retriever = VisualPageRetriever(rendered_pages, encoder, embeddings)
        corpus_chunks = load_chunks(args.corpus)
        examples = list(read_jsonl(args.dataset))
        validation = validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        evaluation_examples = (
            [example for example in examples if example.get("split") == args.split]
            if args.split
            else examples
        )
        if not evaluation_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        report = {
            "experiment": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retriever": "clip-page",
                "model": model_name,
                "top_k": args.top_k,
                "split": args.split or "all",
                "evaluated_queries": len(evaluation_examples),
                "manifests": [str(path.resolve()) for path in _expand_paths(args.manifests)],
                "cache": str(args.cache.resolve()),
                "dataset": str(args.dataset.resolve()),
            },
            "dataset": validation.to_dict(),
            "metrics": evaluate_page_retrieval(
                retriever, evaluation_examples, args.top_k
            ).to_dict(),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["output"] = str(args.output)
        _print_json(report, indent=2)
        return 0
    if args.command == "hybrid-evaluate":
        rendered_pages = _load_rendered_pages(args.manifests)
        embeddings, cached_model = load_page_embedding_cache(
            rendered_pages, args.cache, args.model
        )
        model_name = args.model or cached_model
        encoder = SentenceTransformersCLIPEncoder(model_name, args.device, args.batch_size)
        visual_retriever = VisualPageRetriever(rendered_pages, encoder, embeddings)
        corpus_chunks = load_chunks(args.corpus)
        bm25_chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        bm25_retriever = BM25PageRetriever(bm25_chunks, rendered_pages, args.candidate_k)
        hybrid_retriever = ReciprocalRankFusionRetriever(
            {"bm25": bm25_retriever, "clip": visual_retriever},
            {"bm25": args.bm25_weight, "clip": args.visual_weight},
            args.rrf_k,
            args.candidate_k,
        )
        examples = list(read_jsonl(args.dataset))
        validation = validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        evaluation_examples = (
            [example for example in examples if example.get("split") == args.split]
            if args.split
            else examples
        )
        if not evaluation_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        retrievers = {
            "bm25_page": bm25_retriever,
            "clip_page": visual_retriever,
            "hybrid_rrf": hybrid_retriever,
        }
        report = {
            "experiment": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retriever": "bm25-clip-rrf",
                "model": model_name,
                "top_k": args.top_k,
                "candidate_k": args.candidate_k,
                "diagnostic_k": args.diagnostic_k,
                "rrf_k": args.rrf_k,
                "weights": {"bm25": args.bm25_weight, "clip": args.visual_weight},
                "levels": sorted(args.levels),
                "split": args.split or "all",
                "evaluated_queries": len(evaluation_examples),
                "corpus": str(args.corpus.resolve()),
                "manifests": [str(path.resolve()) for path in _expand_paths(args.manifests)],
                "cache": str(args.cache.resolve()),
                "dataset": str(args.dataset.resolve()),
            },
            "dataset": validation.to_dict(),
            "metrics": {
                name: evaluate_page_retrieval(retriever, evaluation_examples, args.top_k).to_dict()
                for name, retriever in retrievers.items()
            },
            "query_diagnostics": compare_page_retrievers(
                retrievers, evaluation_examples, args.diagnostic_k
            ),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["output"] = str(args.output)
        _print_json(report, indent=2)
        return 0
    if args.command == "type-aware-evaluate":
        rendered_pages = _load_rendered_pages(args.manifests)
        visual_embeddings, cached_visual_model = load_page_embedding_cache(
            rendered_pages, args.visual_cache, args.visual_model
        )
        visual_model = args.visual_model or cached_visual_model
        visual_encoder = SentenceTransformersCLIPEncoder(
            visual_model, args.device, args.visual_batch_size
        )
        clip_page = VisualPageRetriever(rendered_pages, visual_encoder, visual_embeddings)

        corpus_chunks = load_chunks(args.corpus)
        chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        dense_embeddings, dense_metadata = load_chunk_embedding_cache(
            chunks, args.dense_cache, args.dense_model
        )
        dense_model = args.dense_model or dense_metadata["model"]
        dense_encoder = SentenceTransformersTextEncoder(
            dense_model,
            args.device,
            args.dense_batch_size,
            dense_metadata["query_prefix"],
            dense_metadata["document_prefix"],
        )
        dense_page = ChunkPageRetriever(
            DenseRetriever(chunks, dense_encoder, dense_embeddings),
            rendered_pages,
            args.candidate_k,
        )
        bm25_page = BM25PageRetriever(chunks, rendered_pages, args.candidate_k)
        dense_clip_rrf = ReciprocalRankFusionRetriever(
            {"dense": dense_page, "clip": clip_page},
            {"dense": args.dense_weight, "clip": args.visual_weight},
            args.rrf_k,
            args.candidate_k,
        )
        retrievers = {
            "bm25_page": bm25_page,
            "dense_page": dense_page,
            "clip_page": clip_page,
            "dense_clip_rrf": dense_clip_rrf,
        }
        routes = {question_type: "dense_page" for question_type in QUESTION_TYPES}
        routes.update(dict(args.route))

        examples = list(read_jsonl(args.dataset))
        validation = validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        evaluation_examples = (
            [example for example in examples if example.get("split") == args.split]
            if args.split
            else examples
        )
        if not evaluation_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        routed_metrics, route_counts = evaluate_routed_page_retrieval(
            retrievers, routes, evaluation_examples, args.top_k
        )
        diagnostics = compare_page_retrievers(
            retrievers, evaluation_examples, args.diagnostic_k
        )
        for diagnostic in diagnostics:
            diagnostic["selected_system"] = routes[diagnostic["question_type"]]
        report = {
            "experiment": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retriever": "question-type-router",
                "dense_model": dense_model,
                "visual_model": visual_model,
                "top_k": args.top_k,
                "candidate_k": args.candidate_k,
                "diagnostic_k": args.diagnostic_k,
                "rrf_k": args.rrf_k,
                "dense_clip_weights": {
                    "dense": args.dense_weight,
                    "clip": args.visual_weight,
                },
                "routes": dict(sorted(routes.items())),
                "route_counts": route_counts,
                "levels": sorted(args.levels),
                "split": args.split or "all",
                "evaluated_queries": len(evaluation_examples),
                "corpus": str(args.corpus.resolve()),
                "manifests": [str(path.resolve()) for path in _expand_paths(args.manifests)],
                "dense_cache": str(args.dense_cache.resolve()),
                "visual_cache": str(args.visual_cache.resolve()),
                "dataset": str(args.dataset.resolve()),
            },
            "dataset": validation.to_dict(),
            "metrics": {
                **{
                    name: evaluate_page_retrieval(
                        retriever, evaluation_examples, args.top_k
                    ).to_dict()
                    for name, retriever in retrievers.items()
                },
                "routed": routed_metrics.to_dict(),
            },
            "query_diagnostics": diagnostics,
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["output"] = str(args.output)
        _print_json(report, indent=2)
        return 0
    if args.command == "dense-index":
        corpus_chunks = load_chunks(args.corpus)
        chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        encoder = SentenceTransformersTextEncoder(
            args.model,
            args.device,
            args.batch_size,
            args.query_prefix,
            args.document_prefix,
        )
        embeddings = encoder.encode_documents([chunk.text for chunk in chunks])
        write_chunk_embedding_cache(
            chunks,
            embeddings,
            args.output,
            args.model,
            args.query_prefix,
            args.document_prefix,
        )
        _print_json(
            {
                "model": args.model,
                "levels": sorted(args.levels),
                "chunks": len(chunks),
                "dimensions": len(embeddings[0]) if embeddings else 0,
                "output": str(args.output),
            },
            indent=2,
        )
        return 0
    if args.command == "dense-evaluate":
        corpus_chunks = load_chunks(args.corpus)
        chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        embeddings, cache_metadata = load_chunk_embedding_cache(chunks, args.cache, args.model)
        model_name = args.model or cache_metadata["model"]
        encoder = SentenceTransformersTextEncoder(
            model_name,
            args.device,
            args.batch_size,
            cache_metadata["query_prefix"],
            cache_metadata["document_prefix"],
        )
        retriever = DenseRetriever(chunks, encoder, embeddings)
        examples = list(read_jsonl(args.dataset))
        validation = validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        evaluation_examples = (
            [example for example in examples if example.get("split") == args.split]
            if args.split
            else examples
        )
        if not evaluation_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        report = {
            "experiment": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retriever": "dense-text",
                "model": model_name,
                "top_k": args.top_k,
                "levels": sorted(args.levels),
                "split": args.split or "all",
                "evaluated_queries": len(evaluation_examples),
                "corpus": str(args.corpus.resolve()),
                "cache": str(args.cache.resolve()),
                "dataset": str(args.dataset.resolve()),
            },
            "dataset": validation.to_dict(),
            "metrics": evaluate(retriever, evaluation_examples, args.top_k).to_dict(),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["output"] = str(args.output)
        _print_json(report, indent=2)
        return 0
    if args.command == "text-hybrid-evaluate":
        corpus_chunks = load_chunks(args.corpus)
        chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        embeddings, cache_metadata = load_chunk_embedding_cache(chunks, args.cache, args.model)
        model_name = args.model or cache_metadata["model"]
        encoder = SentenceTransformersTextEncoder(
            model_name,
            args.device,
            args.batch_size,
            cache_metadata["query_prefix"],
            cache_metadata["document_prefix"],
        )
        bm25_retriever = BM25Retriever(chunks)
        dense_retriever = DenseRetriever(chunks, encoder, embeddings)
        hybrid_retriever = ReciprocalRankFusionChunkRetriever(
            {"bm25": bm25_retriever, "dense": dense_retriever},
            {"bm25": args.bm25_weight, "dense": args.dense_weight},
            args.rrf_k,
            args.candidate_k,
        )
        examples = list(read_jsonl(args.dataset))
        validation = validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        evaluation_examples = (
            [example for example in examples if example.get("split") == args.split]
            if args.split
            else examples
        )
        if not evaluation_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        retrievers = {
            "bm25": bm25_retriever,
            "dense": dense_retriever,
            "hybrid_rrf": hybrid_retriever,
        }
        report = {
            "experiment": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retriever": "bm25-dense-rrf",
                "model": model_name,
                "top_k": args.top_k,
                "candidate_k": args.candidate_k,
                "diagnostic_k": args.diagnostic_k,
                "rrf_k": args.rrf_k,
                "weights": {"bm25": args.bm25_weight, "dense": args.dense_weight},
                "levels": sorted(args.levels),
                "split": args.split or "all",
                "evaluated_queries": len(evaluation_examples),
                "corpus": str(args.corpus.resolve()),
                "cache": str(args.cache.resolve()),
                "dataset": str(args.dataset.resolve()),
            },
            "dataset": validation.to_dict(),
            "metrics": {
                name: evaluate(retriever, evaluation_examples, args.top_k).to_dict()
                for name, retriever in retrievers.items()
            },
            "query_diagnostics": compare_retrievers(
                retrievers, evaluation_examples, args.diagnostic_k
            ),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["output"] = str(args.output)
        _print_json(report, indent=2)
        return 0
    if args.command == "dense-mine-negatives":
        corpus_chunks = load_chunks(args.corpus)
        chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        embeddings, cache_metadata = load_chunk_embedding_cache(chunks, args.cache, args.model)
        model_name = args.model or cache_metadata["model"]
        encoder = SentenceTransformersTextEncoder(
            model_name,
            args.device,
            args.batch_size,
            cache_metadata["query_prefix"],
            cache_metadata["document_prefix"],
        )
        retriever = DenseRetriever(chunks, encoder, embeddings)
        examples = list(read_jsonl(args.dataset))
        validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        mining_examples = [example for example in examples if example.get("split") == args.split]
        if not mining_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        requested_limits = {
            "hard": args.hard_per_query,
            "medium": args.medium_per_query,
            "easy": args.easy_per_query,
        }
        limits = {name: value for name, value in requested_limits.items() if value is not None}
        triplets = mine_hard_negatives(
            retriever,
            mining_examples,
            chunks,
            args.top_k,
            miner_name=f"dense:{model_name}",
            max_per_query=limits,
        )
        write_jsonl((triplet.to_dict() for triplet in triplets), args.output)
        _print_json(
            {
                "miner": f"dense:{model_name}",
                "split": args.split,
                "examples": len(mining_examples),
                "triplets": len(triplets),
                "difficulty_counts": {
                    difficulty: sum(item.difficulty == difficulty for item in triplets)
                    for difficulty in ("hard", "medium", "easy")
                },
                "max_per_query": limits or None,
                "output": str(args.output),
            },
            indent=2,
        )
        return 0
    if args.command == "build-negative-review-pack":
        chunks = load_chunks(args.corpus)
        triplets = list(read_jsonl(args.triplets))
        _print_json(build_negative_review_pack(triplets, chunks, args.output), indent=2)
        return 0
    if args.command == "apply-negative-reviews":
        reviewed_rows = list(read_jsonl(args.reviews))
        triplets, summary = apply_negative_reviews(
            reviewed_rows, require_complete=not args.allow_incomplete
        )
        write_jsonl(triplets, args.output)
        summary["output"] = str(args.output)
        _print_json(summary, indent=2)
        return 0
    if args.command == "train-reranker":
        chunks = load_chunks(args.corpus)
        triplets = list(read_jsonl(args.triplets))
        pairs, data_summary = build_reranker_pairs(triplets, chunks)
        training_summary = train_cross_encoder(
            pairs,
            args.output_dir,
            model_name=args.model,
            device=args.device,
            batch_size=args.batch_size,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            seed=args.seed,
            local_files_only=args.local_files_only,
        )
        _print_json({"data": data_summary, "training": training_summary}, indent=2)
        return 0
    if args.command == "reranker-evaluate":
        corpus_chunks = load_chunks(args.corpus)
        chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
        embeddings, cache_metadata = load_chunk_embedding_cache(chunks, args.cache, args.model)
        model_name = args.model or cache_metadata["model"]
        encoder = SentenceTransformersTextEncoder(
            model_name,
            args.device,
            args.batch_size,
            cache_metadata["query_prefix"],
            cache_metadata["document_prefix"],
        )
        dense = DenseRetriever(chunks, encoder, embeddings)
        retriever = RerankedRetriever(
            dense, CrossEncoderReranker(args.reranker, args.device), args.candidate_k
        )
        examples = list(read_jsonl(args.dataset))
        validation = validate_dataset(
            examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=corpus_chunks,
        )
        evaluation_examples = [row for row in examples if row.get("split") == args.split]
        if not evaluation_examples:
            raise ValueError(f"The dataset has no examples in split {args.split!r}")
        report = {
            "experiment": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retriever": "dense-cross-encoder",
                "dense_model": model_name,
                "reranker": str(args.reranker.resolve()),
                "top_k": args.top_k,
                "candidate_k": args.candidate_k,
                "levels": sorted(args.levels),
                "split": args.split,
                "evaluated_queries": len(evaluation_examples),
            },
            "dataset": validation.to_dict(),
            "metrics": evaluate(retriever, evaluation_examples, args.top_k).to_dict(),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["output"] = str(args.output)
        _print_json(report, indent=2)
        return 0
    if args.command == "inspect":
        pages = get_parser(args.document).parse(args.document)
        if args.pages_output:
            write_jsonl((page.to_dict() for page in pages), args.pages_output)
        report = build_parse_report(pages, args.low_text_threshold).to_dict()
        if args.pages_output:
            report["pages_output"] = str(args.pages_output)
        _print_json(report, indent=2)
        return 0
    if args.command == "validate-dataset":
        examples = list(read_jsonl(args.dataset))
        validation_chunks = load_chunks(args.corpus) if args.corpus else None
        _print_json(
            validate_dataset(
                examples,
                require_question_types=args.strict,
                require_splits=args.strict,
                require_document_ids=args.strict,
                require_annotation_statuses=args.strict,
                chunks=validation_chunks,
            ).to_dict(),
            indent=2,
        )
        return 0
    if args.command == "build-review-pack":
        review_chunks = load_chunks(args.corpus)
        review_examples = list(read_jsonl(args.dataset))
        validate_dataset(
            review_examples,
            require_question_types=True,
            require_splits=True,
            require_document_ids=True,
            require_annotation_statuses=True,
            chunks=review_chunks,
        )
        rendered_pages = _load_rendered_pages(args.manifests)
        _print_json(
            build_review_pack(review_examples, review_chunks, args.output, rendered_pages),
            indent=2,
        )
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
    if args.command == "ingest-corpus":
        all_chunks = []
        documents = []
        seen_document_ids: set[str] = set()
        for document in args.documents:
            pages = get_parser(document).parse(document)
            chunks = HierarchicalChunker(args.max_chars, args.overlap).chunk(pages)
            document_id = pages[0].document_id if pages else None
            if document_id in seen_document_ids:
                raise ValueError(f"Duplicate document content: {document}")
            if document_id:
                seen_document_ids.add(document_id)
            all_chunks.extend(chunks)
            documents.append(
                {
                    "source_name": document.name,
                    "document_id": document_id,
                    "pages": len(pages),
                    "chunks": len(chunks),
                }
            )
        write_jsonl((chunk.to_dict() for chunk in all_chunks), args.output)
        _print_json(
            {
                "documents": documents,
                "document_count": len(documents),
                "chunks": len(all_chunks),
                "output": str(args.output),
            },
            indent=2,
        )
        return 0
    corpus_chunks = load_chunks(args.corpus)
    chunks = [chunk for chunk in corpus_chunks if chunk.level in args.levels]
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
    validation = validate_dataset(
        examples,
        require_question_types=args.strict_dataset,
        require_splits=args.strict_dataset,
        require_document_ids=args.strict_dataset,
        require_annotation_statuses=args.strict_dataset,
        chunks=corpus_chunks,
    )
    evaluation_examples = (
        [example for example in examples if example.get("split") == args.split]
        if args.split
        else examples
    )
    if not evaluation_examples:
        raise ValueError(f"The dataset has no examples in split {args.split!r}")
    report = {
        "experiment": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "retriever": "bm25",
            "top_k": args.top_k,
            "levels": sorted(args.levels),
            "corpus": str(args.corpus.resolve()),
            "dataset": str(args.dataset.resolve()),
            "split": args.split or "all",
            "evaluated_queries": len(evaluation_examples),
        },
        "dataset": validation.to_dict(),
        "metrics": evaluate(retriever, evaluation_examples, args.top_k).to_dict(),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["output"] = str(args.output)
    _print_json(report, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
