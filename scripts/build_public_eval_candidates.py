from __future__ import annotations

import argparse
import json
from pathlib import Path

CANDIDATES = [
    {
        "id": "public-dp-001",
        "query": "How do top-down memoization and bottom-up dynamic programming avoid repeated Fibonacci subproblems?",
        "source_name": "lecture-15-recursive-algorithms.pdf",
        "pages": [3],
        "question_type": "text",
        "split": "train",
        "answer_hint": "Top down records recursive results in a memo; bottom up evaluates each subproblem once in topological order.",
        "review_sources": ["recitation-15.pdf"],
    },
    {
        "id": "public-dp-002",
        "query": "What are the six SRT BOT steps for specifying and analyzing a dynamic program?",
        "source_name": "lecture-15-recursive-algorithms.pdf",
        "pages": [4],
        "question_type": "text",
        "split": "train",
        "answer_hint": "Define subproblems, relate them, give a topological order, state base cases, recover the original problem, and analyze time.",
        "review_sources": ["recitation-15.pdf"],
    },
    {
        "id": "public-dp-003",
        "query": "What recurrence and evaluation order solve single-source shortest paths in a DAG?",
        "source_name": "lecture-15-recursive-algorithms.pdf",
        "pages": [5],
        "question_type": "formula",
        "split": "train",
        "answer_hint": "For each vertex, minimize predecessor distance plus edge weight and evaluate vertices in topological order.",
        "review_sources": ["recitation-15.pdf"],
    },
    {
        "id": "public-dp-004",
        "query": "For the bowling problem, which three choices define the suffix DP recurrence and what is its running time?",
        "source_name": "lecture-15-recursive-algorithms.pdf",
        "pages": [6],
        "question_type": "formula",
        "split": "train",
        "answer_hint": "Skip the first pin, hit it alone, or hit it with the next pin; the suffix DP has linear time.",
        "review_sources": ["recitation-15.pdf"],
    },
    {
        "id": "public-dp-005",
        "query": "How does the longest-common-subsequence recurrence differ when the two current characters match?",
        "source_name": "lecture-16-dp-subproblems.pdf",
        "pages": [2],
        "question_type": "formula",
        "split": "train",
        "answer_hint": "A match contributes one and advances both strings; otherwise take the better result from advancing either one.",
        "review_sources": ["recitation-16.pdf"],
    },
    {
        "id": "public-dp-006",
        "query": "Why does the LIS dynamic program constrain each subproblem to include its first element?",
        "source_name": "lecture-16-dp-subproblems.pdf",
        "pages": [4],
        "question_type": "text",
        "split": "train",
        "answer_hint": "The constraint preserves enough state to ensure the next chosen element is larger; the original answer then maximizes over possible first elements.",
        "review_sources": ["recitation-16.pdf"],
    },
    {
        "id": "public-dp-007",
        "query": "What state and recurrence model optimal play in the alternating coin game?",
        "source_name": "lecture-16-dp-subproblems.pdf",
        "pages": [6],
        "question_type": "formula",
        "split": "dev",
        "answer_hint": "Use every remaining interval as a state and compare taking its first or last coin, subtracting the opponent's optimal value.",
        "review_sources": ["recitation-16.pdf"],
    },
    {
        "id": "public-dp-008",
        "query": "When a natural dynamic-programming subproblem lacks information needed by its recurrence, what modeling technique should be tried?",
        "source_name": "lecture-16-dp-subproblems.pdf",
        "pages": [8],
        "question_type": "text",
        "split": "dev",
        "answer_hint": "Constrain or expand the subproblem state, trading more states for a simpler workable recurrence.",
        "review_sources": ["recitation-16.pdf"],
    },
    {
        "id": "public-dp-009",
        "query": "How does adding an edge-count parameter make the Bellman-Ford subproblem graph acyclic, and how is a negative cycle detected?",
        "source_name": "lecture-17-dynamic-programming-3.pdf",
        "pages": [2],
        "question_type": "formula",
        "split": "test",
        "answer_hint": "Each state depends on the previous edge limit; improvement from |V|-1 to |V| edges indicates a negative-weight cycle.",
        "review_sources": ["problem-session-8.pdf", "problem-session-8-solutions.pdf"],
    },
    {
        "id": "public-dp-010",
        "query": "What subproblem and recurrence let Floyd-Warshall solve all-pairs shortest paths in cubic time?",
        "source_name": "lecture-17-dynamic-programming-3.pdf",
        "pages": [3],
        "question_type": "formula",
        "split": "test",
        "answer_hint": "Index paths by allowed intermediate vertices and compare using vertex k with not using it, yielding O(|V|^3) constant-work states.",
        "review_sources": ["problem-session-8.pdf", "problem-session-8-solutions.pdf"],
    },
    {
        "id": "public-search-001",
        "query": "Which components must be specified to define a search problem, and what constitutes a solution?",
        "source_name": "lecture-02-search.pdf",
        "pages": [14],
        "question_type": "text",
        "split": "train",
        "answer_hint": "A state space, successor function with actions and costs, start state, and goal test; a solution is an action sequence reaching a goal.",
        "review_sources": ["discussion-01.pdf", "discussion-01-solutions.pdf"],
    },
    {
        "id": "public-search-002",
        "query": "What information belongs in the state for a Pac-Man task that must eat all dots while keeping ghosts scared?",
        "source_name": "lecture-02-search.pdf",
        "pages": [20],
        "question_type": "text",
        "split": "train",
        "answer_hint": "Agent position, remaining-dot indicators, power-pellet indicators, and remaining scared time.",
        "review_sources": ["discussion-01.pdf", "discussion-01-solutions.pdf"],
    },
    {
        "id": "public-search-003",
        "query": "In general tree search, what is the fringe and which decision distinguishes exploration strategies?",
        "source_name": "lecture-02-search.pdf",
        "pages": [30, 31],
        "question_type": "cross_page",
        "split": "train",
        "answer_hint": "The fringe contains generated but unexpanded nodes; strategies differ in which fringe node is expanded next.",
        "review_sources": ["discussion-01.pdf", "discussion-01-solutions.pdf"],
    },
    {
        "id": "public-search-004",
        "query": "Under what assumptions is uniform-cost search complete and optimal, and which nodes can it expand before the cheapest solution?",
        "source_name": "lecture-02-search.pdf",
        "pages": [47],
        "question_type": "text",
        "split": "train",
        "answer_hint": "With finite optimal cost and positive minimum edge cost, UCS is complete and optimal and processes nodes cheaper than the optimal solution.",
        "review_sources": ["discussion-01.pdf", "discussion-01-solutions.pdf"],
    },
    {
        "id": "public-search-005",
        "query": "How can DFS, BFS, and UCS share one search implementation while using different fringe behavior?",
        "source_name": "lecture-02-search.pdf",
        "pages": [46, 49],
        "question_type": "cross_page",
        "split": "train",
        "answer_hint": "Treat the fringe as a priority abstraction: DFS uses a stack, BFS a queue, and UCS orders by path cost.",
        "review_sources": ["discussion-01.pdf", "discussion-01-solutions.pdf"],
    },
    {
        "id": "public-search-006",
        "query": "What does a search heuristic estimate, and why must it be designed for a particular problem?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [16],
        "question_type": "text",
        "split": "train",
        "answer_hint": "It estimates a state's closeness or remaining cost to a goal using problem-specific structure.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-007",
        "query": "Why can greedy best-first search return a suboptimal goal or behave like badly guided DFS?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [22],
        "question_type": "text",
        "split": "dev",
        "answer_hint": "It ranks only estimated goal proximity and ignores accumulated path cost.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-008",
        "query": "How does A* combine the quantities used by uniform-cost and greedy search?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [25],
        "question_type": "formula",
        "split": "dev",
        "answer_hint": "It orders nodes by f(n)=g(n)+h(n), combining path cost so far with estimated remaining cost.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-009",
        "query": "Why must A* wait until a goal is dequeued rather than stopping when that goal is first enqueued?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [26],
        "question_type": "visual_only",
        "split": "test",
        "answer_hint": "A newly enqueued goal may still be more expensive than another frontier path that later reaches a cheaper goal.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-search-010",
        "query": "Which heuristic condition is sufficient for optimal A* tree search versus graph search, and how are the conditions related?",
        "source_name": "lecture-03-informed-search.pdf",
        "pages": [60],
        "question_type": "text",
        "split": "test",
        "answer_hint": "Tree search needs admissibility, graph search needs consistency, and consistency implies admissibility.",
        "review_sources": ["exam-prep-01.pdf", "exam-prep-01-solutions.pdf"],
    },
    {
        "id": "public-mdp-001",
        "query": "What states, actions, dynamics, rewards, and boundary states define a Markov decision process?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [10],
        "question_type": "text",
        "split": "train",
        "answer_hint": "An MDP specifies states, actions, transition probabilities, rewards, a start state, and optionally terminal states.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-002",
        "query": "What conditional-independence assumption does the Markov property impose on action outcomes?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [11],
        "question_type": "text",
        "split": "train",
        "answer_hint": "Given the current state, action outcomes do not depend on the earlier history.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-003",
        "query": "Why is an MDP solution represented as a policy rather than a fixed action sequence?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [12],
        "question_type": "text",
        "split": "train",
        "answer_hint": "Stochastic outcomes require an action choice for every state; the optimal policy maps states to actions maximizing expected utility.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-004",
        "query": "How is a reward sequence discounted, and what utility does discount 0.5 assign to rewards [1,2,3]?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [21],
        "question_type": "formula",
        "split": "train",
        "answer_hint": "Multiply rewards k steps ahead by gamma^k; the example gives 1+0.5*2+0.25*3=2.75.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-005",
        "query": "Which three modeling choices prevent an infinite-horizon MDP from accumulating uncontrolled infinite utility?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [24],
        "question_type": "text",
        "split": "train",
        "answer_hint": "Use a finite horizon, discount future rewards, or guarantee eventual entry into an absorbing terminal state.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-006",
        "query": "How do optimal state value, optimal Q-value, and optimal policy differ?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [27],
        "question_type": "text",
        "split": "train",
        "answer_hint": "V* starts in a state and acts optimally; Q* commits to an initial action then acts optimally; the policy selects the best action.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-007",
        "query": "What does the time-limited value Vk(s) mean, and which search computation is it equivalent to?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [34],
        "question_type": "text",
        "split": "dev",
        "answer_hint": "It is the optimal value with k steps remaining, equivalent to depth-k expectimax from the state.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-008",
        "query": "How is value iteration initialized, what is updated each iteration, and what is the per-iteration complexity?",
        "source_name": "lecture-09-mdp-1.pdf",
        "pages": [51],
        "question_type": "formula",
        "split": "dev",
        "answer_hint": "Start with V0=0, apply one Bellman or expectimax backup to every state, and spend O(S^2 A) per iteration.",
        "review_sources": ["discussion-04.pdf", "discussion-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-009",
        "query": "What two methods can evaluate the values of a fixed policy, and why does the linear-system method omit maximization?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [22, 26],
        "question_type": "cross_page",
        "split": "test",
        "answer_hint": "Iterate fixed-policy Bellman updates or solve their linear equations; the policy already fixes one action per state.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
    {
        "id": "public-mdp-010",
        "query": "What are the evaluation and improvement phases of policy iteration, and when does the algorithm stop?",
        "source_name": "lecture-10-mdp-2.pdf",
        "pages": [47],
        "question_type": "text",
        "split": "test",
        "answer_hint": "Evaluate the current fixed policy, improve it by one-step lookahead, and repeat until the policy no longer changes.",
        "review_sources": ["exam-prep-04.pdf", "exam-prep-04-solutions.pdf"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the public course-pair candidate evaluation set")
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    chunks = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    page_chunks = {
        (chunk.get("metadata", {}).get("source_name"), chunk["page_start"]): chunk
        for chunk in chunks
        if chunk.get("level") == "page" and chunk["page_start"] == chunk["page_end"]
    }
    records = []
    for candidate in CANDIDATES:
        pages = candidate["pages"]
        selected = []
        for page in pages:
            key = (candidate["source_name"], page)
            if key not in page_chunks:
                raise ValueError(f"Missing courseware evidence page: {key}")
            selected.append(page_chunks[key])
        document_ids = {chunk["document_id"] for chunk in selected}
        if len(document_ids) != 1:
            raise ValueError(f"Candidate {candidate['id']} spans multiple documents")
        record = {
            "id": candidate["id"],
            "query": candidate["query"],
            "document_id": selected[0]["document_id"],
            "relevant_pages": pages,
            "relevant_chunk_ids": [chunk["chunk_id"] for chunk in selected],
            "question_type": candidate["question_type"],
            "split": candidate["split"],
            "annotation_status": "candidate",
            "answer_hint": candidate["answer_hint"],
            "pair_id": candidate["id"].split("-")[1],
            "courseware_source": candidate["source_name"],
            "review_sources": candidate["review_sources"],
        }
        records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(json.dumps({"records": len(records), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
