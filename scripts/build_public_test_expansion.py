from __future__ import annotations

import argparse
import json
from pathlib import Path

CANDIDATES = [
    {
        "id": "public-search-019",
        "query": "In the pancake heuristic diagram, which h(x) value is assigned to the sorted goal, and which nonzero values appear on the other illustrated states?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [18],
        "question_type": "table_chart",
        "answer_hint": "The sorted goal has h(x)=0; the other illustrated states are labeled 2, 3, or 4 according to the largest misplaced pancake.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-020",
        "query": "How do the illustrated expansion contours of uniform-cost search and A* differ around the start and goal?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [38],
        "question_type": "visual_only",
        "answer_hint": "Uniform-cost expands roughly equally in all directions, while A* stretches its contours toward the goal but still hedges enough to preserve optimality.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-021",
        "query": "Across the illustrated DFS, BFS, and UCS searches, which priority determines the next expanded node for each strategy?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [11, 12, 13],
        "question_type": "cross_page",
        "answer_hint": "DFS expands a deepest node, BFS a shallowest node, and UCS the node with the lowest cumulative path cost.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-022",
        "query": "Why should BFS graph search avoid expanding the circled nodes in the illustrated search tree?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [52],
        "question_type": "visual_only",
        "answer_hint": "The circled tree nodes repeat states already reached and expanded at shallower positions, so expanding them would duplicate work.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-019",
        "query": "In the four optimal-policy grids, how does the bottom-right nonterminal action change between living rewards -0.01 and -2.0?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [13],
        "question_type": "table_chart",
        "answer_hint": "It points down when R(s)=-0.01, but points up when R(s)=-2.0.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-020",
        "query": "Which car states appear at the leaves of the Racing search tree, and where does the gray Overheated outcome occur?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [16],
        "question_type": "visual_only",
        "answer_hint": "The leaves show Cool, Warm, and Overheated cars; the gray Overheated car is the far-right leaf reached through the rightmost red branch sequence.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-021",
        "query": "What changes in the Gridworld display from k=0 to k=100 under noise 0.2, discount 0.9, and zero living reward?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [35, 48],
        "question_type": "cross_page",
        "answer_hint": "At k=0 every non-wall value is zero; by k=100 the values have converged to nonzero utilities and arrows form a policy favoring the +1 terminal while avoiding the -1 terminal.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-022",
        "query": "What values does the Racing value-iteration table assign to Cool, Warm, and Overheated at V0, V1, and V2?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [52],
        "question_type": "table_chart",
        "answer_hint": "For Cool/Warm/Overheated, V0=(0,0,0), V1=(2,1,0), and V2=(3.5,2.5,0).",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-023",
        "query": "For the bottom-right nonterminal Gridworld cell, how does its V* value relate to the four Q* action values?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [5, 6],
        "question_type": "cross_page",
        "answer_hint": "V*=0.28 equals the maximum Q* action value in that cell, attained by moving left; the other displayed action values are lower.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-024",
        "query": "Which fixed policy gives higher values along the safe central corridor, Always Go Right or Always Go Forward, and what values are shown?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [24, 25],
        "question_type": "cross_page",
        "answer_hint": "Always Go Forward is much better, with corridor values 33.30, 48.74, and 70.20; Always Go Right shows -8.69, -7.88, and 1.09.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-025",
        "query": "From the Double Bandits payoff chart, which machine has the larger expected reward per play and by how much?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [51],
        "question_type": "table_chart",
        "answer_hint": "Red has expected reward 0.75*2+0.25*0=1.50, which is 0.50 higher than Blue's certain reward of 1.00.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-026",
        "query": "In the Double-Bandit MDP diagram, how do the Blue and Red actions differ in transition probabilities and rewards from Win or Lose?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [52],
        "question_type": "visual_only",
        "answer_hint": "Blue gives $1 with probability 1 and transitions to Win from either state; Red gives $2 and reaches Win with probability 0.75, or $0 and reaches/stays in Lose with probability 0.25.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build independent public test expansion candidates")
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
                "split": "test",
                "annotation_status": "candidate",
                "answer_hint": candidate["answer_hint"],
                "pair_id": candidate["id"].split("-")[1],
                "courseware_source": candidate["source_name"],
                "review_sources": candidate["review_sources"],
                "expansion_round": "test-expansion-v1",
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
                    question_type: sum(
                        row["question_type"] == question_type for row in records
                    )
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
