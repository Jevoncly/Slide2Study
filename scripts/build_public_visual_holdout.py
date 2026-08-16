from __future__ import annotations

import argparse
import json
from pathlib import Path

CANDIDATES = [
    {
        "id": "public-search-029",
        "query": "What makes an agent rational, and which characteristics determine the techniques it should use to select actions?",
        "source_name": "lecture-02-search.pdf",
        "pages": [4],
        "question_type": "text",
        "answer_hint": "A rational agent selects actions that maximize expected utility; the percepts, environment, and action space determine suitable action-selection techniques.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-030",
        "query": "How does graph search use a closed set to avoid expanding a state twice, and why should that collection be a set rather than a list?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [53],
        "question_type": "text",
        "answer_hint": "Before expansion it checks whether the state is already closed, skips repeats, and adds new states; a set provides efficient membership checks.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-033",
        "query": "Which MDP algorithm should be used to compute optimal values, evaluate a fixed policy, and extract a policy from values?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [50],
        "question_type": "text",
        "answer_hint": "Use value or policy iteration for optimal values, policy evaluation for a fixed policy, and one-step-lookahead policy extraction to turn values into a policy.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-search-031",
        "query": "What inequality defines heuristic consistency on an arc A to C, and what does it imply about f-values along a path?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [57],
        "question_type": "formula",
        "answer_hint": "Consistency requires h(A)-h(C) <= cost(A,C), equivalently h(A) <= cost(A,C)+h(C); therefore f-values never decrease along a path.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-034",
        "query": "How is the value of state s under a fixed policy pi defined, and what one-step Bellman backup computes it?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [23],
        "question_type": "formula",
        "answer_hint": "V^pi(s) is expected total discounted reward when following pi; its backup sums T(s,pi(s),s') times [R(s,pi(s),s') + gamma V^pi(s')] over successor states.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-035",
        "query": "How does value iteration advance from V0 to later value vectors, and what is the stated complexity of each iteration?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [17],
        "question_type": "formula",
        "answer_hint": "Start with V0(s)=0, perform one Bellman/expectimax backup from every state to obtain the next vector, and repeat; each iteration costs O(S^2 A).",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-search-032",
        "query": "How do reflex and planning agents differ in their treatment of future consequences, models, and goals?",
        "source_name": "lecture-02-search.pdf",
        "pages": [6, 10],
        "question_type": "cross_page",
        "answer_hint": "Reflex agents act from the current percept or remembered state without considering future consequences; planning agents ask what-if, predict consequences with a world model, and formulate a goal test.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-033",
        "query": "What inequality chain in the A* blocking proof ensures an ancestor n of the optimal goal is expanded before a suboptimal goal B?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [32, 33, 34, 35],
        "question_type": "cross_page",
        "answer_hint": "Admissibility gives f(n) <= f(A), suboptimality gives f(A) < f(B), so f(n) <= f(A) < f(B) and n is expanded before B.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-036",
        "query": "Why does extracting an action from V* require one-step lookahead while extracting it from Q* is immediate?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [28, 29],
        "question_type": "cross_page",
        "answer_hint": "V* values states but not individual first actions, so each action needs a one-step expectimax comparison; Q*(s,a) already values each action, so choose its argmax.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-search-034",
        "query": "In the illustrated pancake tree-search example, what are the two shown flip costs and the total cost of the displayed route to the goal?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [8],
        "question_type": "table_chart",
        "answer_hint": "Flipping the top two costs 2, flipping all four costs 4, and the displayed route flip-four then flip-three has total cost 7.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-035",
        "query": "Where is the blank tile in the illustrated 8-puzzle start and goal states, and how many legal blank moves does each position allow?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [44],
        "question_type": "table_chart",
        "answer_hint": "The start blank is in the center and permits four moves; the goal blank is in the top-left corner and permits two moves.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-037",
        "query": "For the noisy Gridworld North action, what probabilities apply to moving north, west, or east, and what happens if the sampled direction is blocked?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [2],
        "question_type": "table_chart",
        "answer_hint": "North occurs with probability 0.8, west and east with 0.1 each; if a wall blocks the sampled direction, the agent stays put.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-search-036",
        "query": "Where is the robot located in the left and right panels of the illustrated DFS-versus-BFS quiz?",
        "source_name": "lecture-02-search.pdf",
        "pages": [41],
        "question_type": "visual_only",
        "answer_hint": "In the left panel the robot is falling into the central shaft; in the right panel it is on the upper ridge beside the yellow character.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-038",
        "query": "How are the four colored gems arranged on the left and right branches of the illustrated utility-sequence tree?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [18],
        "question_type": "visual_only",
        "answer_hint": "The left branch places orange, magenta, green, and blue gems sequentially on separate nodes; the right branch ends with all four gems clustered together.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-039",
        "query": "Which goal, hazard, and obstacle symbols appear in the illustrated policy-extraction grids?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [27],
        "question_type": "visual_only",
        "answer_hint": "The grids show a positive goal as +1 or a blue diamond, a negative hazard as -1 or a skull, and a blocked cell as a gray or hatched wall.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an independent visual-routing holdout")
    parser.add_argument("corpus", type=Path)
    parser.add_argument("existing_dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reviewed",
        action="store_true",
        help="Record the candidates as human-verified after review",
    )
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
    selected_pages: set[tuple[str, int]] = set()
    for candidate in CANDIDATES:
        if candidate["id"] in existing_ids:
            raise ValueError(f"Candidate ID already exists: {candidate['id']}")
        selected = []
        for page in candidate["pages"]:
            key = (candidate["source_name"], page)
            if key not in page_chunks:
                raise ValueError(f"Missing courseware evidence page: {key}")
            if key in selected_pages:
                raise ValueError(f"Holdout evidence page reused internally: {key}")
            selected_pages.add(key)
            selected.append(page_chunks[key])
        document_ids = {chunk["document_id"] for chunk in selected}
        if len(document_ids) != 1:
            raise ValueError(f"Candidate {candidate['id']} spans multiple documents")
        document_id = selected[0]["document_id"]
        overlaps = sorted(page for page in candidate["pages"] if (document_id, page) in used_pages)
        if overlaps:
            raise ValueError(f"Candidate {candidate['id']} reuses labeled pages: {overlaps}")
        record = {
                "id": candidate["id"],
                "query": candidate["query"],
                "document_id": document_id,
                "relevant_pages": candidate["pages"],
                "relevant_chunk_ids": [chunk["chunk_id"] for chunk in selected],
                "question_type": candidate["question_type"],
                "split": "test",
                "annotation_status": "verified" if args.reviewed else "candidate",
                "answer_hint": candidate["answer_hint"],
                "pair_id": candidate["id"].split("-")[1],
                "courseware_source": candidate["source_name"],
                "review_sources": candidate["review_sources"],
                "expansion_round": "visual-routing-holdout-v1",
            }
        if args.reviewed:
            record.update({"review_decision": "verified", "reviewer_type": "human"})
        records.append(record)

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
                "evidence_pages": len(selected_pages),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
