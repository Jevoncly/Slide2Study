from __future__ import annotations

import argparse
import json
from pathlib import Path

CANDIDATES = [
    {
        "id": "public-search-023",
        "query": "In the Romania heuristic figure, what straight-line distances to Bucharest are listed for Arad, Bucharest, and Zerind?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [17],
        "question_type": "table_chart",
        "split": "dev",
        "answer_hint": "The table lists Arad as 366, Bucharest as 0, and Zerind as 374.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-024",
        "query": "Which route does the illustrated greedy search expand from Arad to Bucharest, and which three outlined alternatives remain after it expands Sibiu?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [21],
        "question_type": "table_chart",
        "split": "dev",
        "answer_hint": "It follows Arad to Sibiu to Fagaras to Bucharest; the outlined alternatives after expanding Sibiu are Arad (366), Oradea (380), and Rimnicu Vilcea (193).",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-025",
        "query": "Why does the illustrated four-state graph rooted at S have an infinite search tree?",
        "source_name": "lecture-02-search.pdf",
        "pages": [26],
        "question_type": "visual_only",
        "split": "dev",
        "answer_hint": "States a and b have transitions back to each other, so tree search can generate alternating a-b paths forever even though the state graph has only four states.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-026",
        "query": "On the Romania road map, what is the total cost of the route Arad-Sibiu-Fagaras-Bucharest?",
        "source_name": "lecture-02-search.pdf",
        "pages": [29],
        "question_type": "table_chart",
        "split": "dev",
        "answer_hint": "The edge costs are 140, 99, and 211, for a total route cost of 450.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-027",
        "query": "In the Pac-Man comparison image, which search algorithms are shown from left to right, and which one colors the broadest explored region?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [39],
        "question_type": "visual_only",
        "split": "dev",
        "answer_hint": "The panels are Greedy, Uniform Cost, and A* from left to right; Uniform Cost colors the broadest explored region.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-028",
        "query": "How does the illustrated search tree duplicate the four-state A-B-C-D graph, and what growth problem does this demonstrate?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [51],
        "question_type": "visual_only",
        "split": "dev",
        "answer_hint": "Each state has two transitions to the next state, so B and then C appear repeatedly in separate tree branches; failing to merge repeated states causes exponential extra work.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-027",
        "query": "When the robot chooses Up in the illustrated grid worlds, how do the deterministic and stochastic outcomes differ?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [9],
        "question_type": "visual_only",
        "split": "dev",
        "answer_hint": "The deterministic action moves the robot up with one outcome; the stochastic action can move it left into the fire, up as intended, or right.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-028",
        "query": "In the Racing search tree, how many Cool, Warm, and Overheated cars appear at the visible leaves?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [31],
        "question_type": "visual_only",
        "split": "dev",
        "answer_hint": "The nine visible leaves contain five Cool cars, three Warm cars, and one Overheated car.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-029",
        "query": "How does the time-limited-value diagram connect search-tree depth to the value layers V0 through V4?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [49],
        "question_type": "visual_only",
        "split": "dev",
        "answer_hint": "Each deeper tree layer supplies the next finite-horizon backup: leaf outcomes start at V0 and successive backups collapse them into state values V1, V2, V3, and finally V4 at the root.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-030",
        "query": "Across k=1, k=2, and k=3 in the Gridworld displays, which nonterminal values first become positive and what values are shown?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [36, 37, 38],
        "question_type": "table_chart",
        "split": "dev",
        "answer_hint": "At k=1 all nonterminals are 0; at k=2 the cell left of +1 becomes 0.72; at k=3 it becomes 0.78, the next cell left becomes 0.52, and the cell below becomes 0.43.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-031",
        "query": "From the ten displayed red-machine payouts, what are its total and empirical average, and how do they compare with the blue machine's certain $1 payout?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [54],
        "question_type": "table_chart",
        "split": "dev",
        "answer_hint": "Six $2 outcomes and four $0 outcomes total $12, averaging $1.20; ten blue plays would total $10 and average $1.00.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-032",
        "query": "What certain payout and uncertain payout alternatives are contrasted in the illustrated harder bandit game?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [55],
        "question_type": "table_chart",
        "split": "dev",
        "answer_hint": "One machine pays $1 every time; the other pays either $2 or $0 with probabilities that are still unknown in the figure.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build visual-heavy public dev expansion candidates")
    parser.add_argument("corpus", type=Path)
    parser.add_argument("existing_dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    chunks = [
        json.loads(line)
        for line in args.corpus.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    existing = [
        json.loads(line)
        for line in args.existing_dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    existing_ids = {row["id"] for row in existing}
    used_pages = {
        (row["document_id"], int(page))
        for row in existing
        for page in row.get("relevant_pages", [])
    }
    page_chunks = {
        (chunk.get("metadata", {}).get("source_name"), chunk["page_start"]): chunk
        for chunk in chunks
        if chunk.get("level") == "page" and chunk["page_start"] == chunk["page_end"]
    }
    records = []
    for candidate in CANDIDATES:
        if candidate["id"] in existing_ids:
            raise ValueError(f"Candidate ID already exists: {candidate['id']}")
        selected = []
        for page in candidate["pages"]:
            key = (candidate["source_name"], page)
            if key not in page_chunks:
                raise ValueError(f"Missing courseware evidence page: {key}")
            selected.append(page_chunks[key])
        document_ids = {chunk["document_id"] for chunk in selected}
        if len(document_ids) != 1:
            raise ValueError(f"Candidate {candidate['id']} spans multiple documents")
        document_id = selected[0]["document_id"]
        overlaps = sorted(page for page in candidate["pages"] if (document_id, page) in used_pages)
        if overlaps:
            raise ValueError(f"Candidate {candidate['id']} reuses labeled pages: {overlaps}")
        records.append(
            {
                "id": candidate["id"],
                "query": candidate["query"],
                "document_id": document_id,
                "relevant_pages": candidate["pages"],
                "relevant_chunk_ids": [chunk["chunk_id"] for chunk in selected],
                "question_type": candidate["question_type"],
                "split": "dev",
                "annotation_status": "candidate",
                "answer_hint": candidate["answer_hint"],
                "pair_id": candidate["id"].split("-")[1],
                "courseware_source": candidate["source_name"],
                "review_sources": candidate["review_sources"],
                "expansion_round": "visual-dev-expansion-v1",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "records": len(records),
                "question_types": {
                    question_type: sum(row["question_type"] == question_type for row in records)
                    for question_type in sorted({row["question_type"] for row in records})
                },
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
