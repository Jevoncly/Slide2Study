from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from slide2study.generation import citation_from_search_result, meaningful_tokens
from slide2study.interfaces import EvidenceCitation
from slide2study.models import Chunk, SearchResult


@dataclass(frozen=True, slots=True)
class SummaryBullet:
    text: str
    citation: EvidenceCitation

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text, "citation": self.citation.to_dict()}


@dataclass(frozen=True, slots=True)
class Flashcard:
    front: str
    back: str
    evidence_text: str
    citation: EvidenceCitation

    def to_dict(self) -> dict[str, object]:
        return {
            "front": self.front,
            "back": self.back,
            "evidence_text": self.evidence_text,
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class KeyConcept:
    term: str
    evidence_text: str
    citation: EvidenceCitation

    def to_dict(self) -> dict[str, object]:
        return {
            "term": self.term,
            "evidence_text": self.evidence_text,
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FormulaEvidence:
    formula_text: str
    symbols: tuple[str, ...]
    citation: EvidenceCitation
    explanation_text: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_text": self.formula_text,
            "symbols": list(self.symbols),
            "explanation_text": self.explanation_text,
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StudyQuestion:
    level: str
    question_type: str
    prompt: str
    answer: str
    evidence_text: str
    citation: EvidenceCitation

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "question_type": self.question_type,
            "prompt": self.prompt,
            "answer": self.answer,
            "evidence_text": self.evidence_text,
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ChapterStudyGuide:
    document_id: str
    section: str
    summary: tuple[SummaryBullet, ...]
    flashcards: tuple[Flashcard, ...]
    concepts: tuple[KeyConcept, ...]
    formulas: tuple[FormulaEvidence, ...]
    questions: tuple[StudyQuestion, ...]
    source_chunk_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "section": self.section,
            "summary": [item.to_dict() for item in self.summary],
            "flashcards": [item.to_dict() for item in self.flashcards],
            "concepts": [item.to_dict() for item in self.concepts],
            "formulas": [item.to_dict() for item in self.formulas],
            "questions": [item.to_dict() for item in self.questions],
            "source_chunk_ids": list(self.source_chunk_ids),
            "cited_pages": sorted(
                {
                    page
                    for item in (
                        *self.summary,
                        *self.flashcards,
                        *self.concepts,
                        *self.formulas,
                        *self.questions,
                    )
                    for page in range(
                        item.citation.page_start,
                        item.citation.page_end + 1,
                    )
                }
            ),
        }


@dataclass(frozen=True, slots=True)
class _Candidate:
    text: str
    chunk: Chunk
    terms: frozenset[str]
    order: int


def build_chapter_study_guide(
    chunks: list[Chunk],
    *,
    document_id: str | None = None,
    section: str | None = None,
    summary_bullets: int = 5,
    flashcard_count: int = 5,
    concept_count: int = 5,
    formula_count: int = 5,
    question_count: int = 5,
) -> ChapterStudyGuide:
    """Create an exact-extractive chapter summary and definition flashcards."""
    if summary_bullets <= 0 or flashcard_count <= 0:
        raise ValueError("summary_bullets and flashcard_count must be positive")
    if concept_count < 0 or formula_count < 0 or question_count < 0:
        raise ValueError("concept_count, formula_count, and question_count cannot be negative")

    all_chunks = chunks
    passages = [chunk for chunk in all_chunks if chunk.level == "passage" and chunk.text.strip()]
    document_ids = sorted({chunk.document_id for chunk in passages})
    if document_id is None:
        if len(document_ids) != 1:
            raise ValueError("--document-id is required when the corpus has multiple documents")
        document_id = document_ids[0]
    passages = [chunk for chunk in passages if chunk.document_id == document_id]
    if not passages:
        raise ValueError(f"No passage chunks found for document {document_id!r}")

    sections = sorted({chunk.section or "Untitled" for chunk in passages})
    if section is None:
        if len(sections) != 1:
            raise ValueError(
                "--section is required when the document has multiple sections; "
                f"available sections: {', '.join(sections)}"
            )
        section = sections[0]
    matching_sections = [name for name in sections if name.casefold() == section.casefold()]
    if not matching_sections:
        raise ValueError(
            f"Section {section!r} was not found; available sections: {', '.join(sections)}"
        )
    selected_section = matching_sections[0]
    passages = sorted(
        [chunk for chunk in passages if (chunk.section or "Untitled") == selected_section],
        key=lambda chunk: (chunk.page_start, chunk.page_end, chunk.chunk_id),
    )
    pages = sorted(
        [
            chunk
            for chunk in all_chunks
            if chunk.level == "page"
            and chunk.document_id == document_id
            and (chunk.section or "Untitled") == selected_section
            and chunk.text.strip()
            and not chunk.metadata.get("text_retrieval_excluded", False)
        ],
        key=lambda chunk: (chunk.page_start, chunk.page_end, chunk.chunk_id),
    )
    evidence_chunks = pages or passages

    candidates = _build_candidates(evidence_chunks)
    if not candidates:
        raise ValueError("The selected section has no sufficiently informative text")
    term_frequency = Counter(term for item in candidates for term in item.terms)
    summary_candidates = _select_diverse(
        candidates,
        term_frequency,
        min(summary_bullets, len(candidates)),
    )
    summary = tuple(
        SummaryBullet(
            text=_summary_text(item.text),
            citation=_citation(item.chunk, f"S{index}"),
        )
        for index, item in enumerate(summary_candidates, 1)
    )

    flashcards = []
    concept_candidates: list[tuple[str, _Candidate]] = []
    used_terms: set[str] = set()
    for item in _select_diverse(candidates, term_frequency, len(candidates)):
        card = _definition_flashcard(item)
        if card is None:
            continue
        term, front, back = card
        if term.casefold() in used_terms:
            continue
        used_terms.add(term.casefold())
        concept_candidates.append((term, item))
        flashcards.append(
            Flashcard(
                front=front,
                back=back,
                evidence_text=item.text,
                citation=_citation(item.chunk, f"F{len(flashcards) + 1}"),
            )
        )
        if len(flashcards) >= flashcard_count:
            break

    concepts = tuple(
        KeyConcept(
            term=term,
            evidence_text=item.text,
            citation=_citation(item.chunk, f"C{index}"),
        )
        for index, (term, item) in enumerate(concept_candidates[:concept_count], 1)
    )
    formulas = tuple(
        FormulaEvidence(
            formula_text=text,
            symbols=symbols,
            citation=_citation(chunk, f"M{index}"),
            explanation_text=_formula_explanation(text, chunk),
        )
        for index, (text, symbols, chunk) in enumerate(
            _formula_evidence(evidence_chunks)[:formula_count], 1
        )
    )
    questions = tuple(
        StudyQuestion(
            level="basic",
            question_type="short_answer",
            prompt=f"What does “{term}” mean?",
            answer=card.back,
            evidence_text=card.evidence_text,
            citation=_citation(item.chunk, f"Q{index}"),
        )
        for index, (card, (term, item)) in enumerate(
            zip(flashcards[:question_count], concept_candidates[:question_count]),
            1,
        )
    )

    return ChapterStudyGuide(
        document_id=document_id,
        section=selected_section,
        summary=summary,
        flashcards=tuple(flashcards),
        concepts=concepts,
        formulas=formulas,
        questions=questions,
        source_chunk_ids=tuple(
            dict.fromkeys(
                [item.chunk.chunk_id for item in candidates]
                + [item.citation.chunk_id for item in formulas]
                + [item.citation.chunk_id for item in questions]
            )
        ),
    )


def build_course_study_guides(
    chunks: list[Chunk],
    *,
    document_id: str | None = None,
    section: str | None = None,
    summary_bullets: int = 5,
    flashcard_count: int = 5,
    concept_count: int = 5,
    formula_count: int = 5,
    question_count: int = 5,
) -> tuple[ChapterStudyGuide, ...]:
    """Build every viable section in document and page order."""
    passages = [chunk for chunk in chunks if chunk.level == "passage" and chunk.text.strip()]
    if document_id is not None:
        passages = [chunk for chunk in passages if chunk.document_id == document_id]
    if not passages:
        raise ValueError("No passage chunks match the requested course selection")
    section_keys = []
    seen = set()
    for chunk in sorted(passages, key=lambda item: (item.document_id, item.page_start, item.chunk_id)):
        key = (chunk.document_id, chunk.section or "Untitled")
        if key in seen or (section and key[1].casefold() != section.casefold()):
            continue
        seen.add(key)
        section_keys.append(key)
    guides = []
    for selected_document, selected_section in section_keys:
        try:
            guides.append(
                build_chapter_study_guide(
                    chunks,
                    document_id=selected_document,
                    section=selected_section,
                    summary_bullets=summary_bullets,
                    flashcard_count=flashcard_count,
                    concept_count=concept_count,
                    formula_count=formula_count,
                    question_count=question_count,
                )
            )
        except ValueError as exc:
            if "no sufficiently informative text" not in str(exc):
                raise
    if not guides:
        raise ValueError("No sections contain sufficiently informative text")
    return tuple(guides)


def _build_candidates(chunks: list[Chunk]) -> list[_Candidate]:
    boilerplate_markers = (
        "all rights reserved",
        "copyright",
        "created by",
        "educational purposes",
        "registered trademark",
        "university of",
        "instructors:",
        "materials are available",
        "terms of use",
        "opencourseware",
        "http://",
        "https://",
    )
    candidates = []
    seen = set()
    order = 0
    for chunk in chunks:
        if chunk.metadata.get("requires_vision") and len(chunk.text.strip()) < 120:
            continue
        for text in _study_units(chunk.text):
            text = _clean_candidate_text(text)
            text = re.sub(r"\s+[A-Z][A-Za-z-]{1,20}\?$", "", text).strip()
            terms = frozenset(meaningful_tokens(text))
            key = text.casefold()
            if (
                len(text) < 20
                or len(text) > 280
                or len(terms) < 3
                or key in seen
                or key == (chunk.section or "").casefold()
                or re.match(r"^\d+\s+(?:def|return|if|for|while)\b", key)
                or re.match(r"^(?:only if|\[?demo\b)", key)
                or text.endswith(":")
                or re.search(r"\.{2,}|[‥…⋯]", text)
                or _looks_incomplete(text)
                or re.search(r"[a-z][A-Z]", text)
                or re.search(r"\s[A-Z]$", text)
                or re.search(r"\b(?:a|an|and|as|been|for|from|if|in|of|on|or|that|the|to|when|which|with)$", key)
                or _looks_like_title(text)
                or any(marker in key for marker in boilerplate_markers)
            ):
                continue
            seen.add(key)
            candidates.append(_Candidate(text, chunk, terms, order))
            order += 1
    return candidates


def _select_diverse(
    candidates: list[_Candidate],
    frequencies: Counter[str],
    count: int,
) -> list[_Candidate]:
    selected = []
    remaining = list(candidates)
    covered_terms: set[str] = set()
    used_pages: set[int] = set()
    while remaining and len(selected) < count:
        best = max(
            remaining,
            key=lambda item: (
                sum(frequencies[term] for term in item.terms - covered_terms)
                + (4 if item.chunk.page_start not in used_pages else 0),
                len(item.terms),
                -item.order,
            ),
        )
        selected.append(best)
        remaining.remove(best)
        covered_terms.update(best.terms)
        used_pages.add(best.chunk.page_start)
    return sorted(selected, key=lambda item: item.order)


def _definition_flashcard(candidate: _Candidate) -> tuple[str, str, str] | None:
    text = candidate.text.strip().rstrip(".")
    rejected_terms = {
        "a solution",
        "action",
        "actions",
        "after the policy",
        "all these search algorithms",
        "another basic operation",
        "base",
        "base cases",
        "basic idea",
        "both",
        "but everything",
        "demo",
        "efficiency",
        "example",
        "examples",
        "exercise",
        "fact",
        "fix",
        "fundamental operation",
        "goal",
        "goal test",
        "hard part",
        "idea",
        "implementation",
        "important",
        "important lesson",
        "improvement",
        "input",
        "key idea",
        "lecture",
        "main idea",
        "main question",
        "natural subproblems",
        "next time",
        "nodes",
        "note",
        "one solution",
        "one way to solve them",
        "optimal",
        "original",
        "output",
        "problem",
        "proof idea",
        "quantities",
        "quiz",
        "recap",
        "recall",
        "relation",
        "remember",
        "reminder",
        "result",
        "review",
        "rewards",
        "roads",
        "sketch",
        "solution",
        "running time",
        "summary",
        "states",
        "start",
        "strategy",
        "subproblems",
        "successor",
        "theorem",
        "then",
        "three states",
        "the bad",
        "the good",
        "these",
        "this",
        "time",
        "two actions",
        "where",
        "worst-case",
    }

    def usable(term: str) -> bool:
        normalized = term.casefold().strip("[] ")
        words = normalized.split()
        return (
            1 <= len(words) <= 6
            and term[0].isupper()
            and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9*' /-]*", term))
            and normalized not in rejected_terms
            and not re.fullmatch(r"(?:case|fact|idea|problem|quiz|step)\s+\d+", normalized)
            and " is " not in normalized
            and " are " not in normalized
            and not normalized.startswith(("demo ", "example ", "lecture "))
            and not any(word in {"can", "if", "should", "will"} for word in words)
            and not normalized.startswith(
                (
                    "a ",
                    "all ",
                    "an ",
                    "another ",
                    "conceptually ",
                    "compute ",
                    "each ",
                    "finding ",
                    "first ",
                    "how ",
                    "if ",
                    "imagine ",
                    "increasing ",
                    "know ",
                    "length of ",
                    "my ",
                    "nice order ",
                    "now ",
                    "often ",
                    "once ",
                    "only if ",
                    "resulting ",
                    "second ",
                    "simplest ",
                    "so ",
                    "some ",
                    "that ",
                    "they ",
                    "the ",
                    "there ",
                    "time to ",
                    "topological order to ",
                    "turn ",
                    "up to ",
                    "very ",
                    "we ",
                    "when ",
                    "with ",
                    "your ",
                )
            )
        )

    def usable_definition(definition: str) -> bool:
        return (
            len(re.findall(r"[A-Za-z]{2,}", definition)) >= 4
            and definition[0].isalnum()
            and not re.search(r"[?!…]", text)
        )

    colon = re.fullmatch(r"([^:]{3,60}):\s+(.{8,180})", text)
    if colon:
        term, definition = (part.strip() for part in colon.groups())
        if usable(term) and usable_definition(definition):
            return term, f"What is {term}?", definition
    copula = re.fullmatch(
        r"(.{3,60}?)\s+(?:is|are|means|refers to|denotes)\s+(.{10,180})",
        text,
        flags=re.IGNORECASE,
    )
    if copula:
        term, definition = (part.strip() for part in copula.groups())
        if usable(term) and usable_definition(definition):
            return term, f"What is {term}?", definition
    definition = re.fullmatch(r"([A-Za-z][A-Za-z -]{2,40})\s*=\s*([A-Za-z].{8,140})", text)
    if definition:
        term, answer = (part.strip() for part in definition.groups())
        if usable(term) and usable_definition(answer):
            return term, f"What is {term}?", answer
    return None


def _citation(chunk: Chunk, evidence_id: str) -> EvidenceCitation:
    return citation_from_search_result(SearchResult(chunk=chunk, score=1.0, rank=1), evidence_id)


def _formula_evidence(chunks: list[Chunk]) -> list[tuple[str, tuple[str, ...], Chunk]]:
    results = []
    seen = set()
    relation_pattern = re.compile(r"(?:=|≤|≥|≈|→|∈)")
    structure_pattern = re.compile(
        r"(?:[A-Za-zͰ-Ͽ][A-Za-z0-9_*'Ͱ-Ͽ]*\s*\([^)]*\)\s*=|"
        r"(?:min|max|sum|argmin|argmax|O|Θ|Ω)\s*\(|∑|Σ|Π|√|\^|\|[^|]+\|)"
    )
    for chunk in chunks:
        for text in _study_units(chunk.text):
            if not (
                3 <= len(text) <= 240
                and relation_pattern.search(text)
                and structure_pattern.search(text)
                and len(relation_pattern.findall(text)) <= 4
                and not (
                    re.match(r"^\d+[.)]\s", text)
                    and len(relation_pattern.findall(text)) > 1
                )
            ):
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            symbols = tuple(
                dict.fromkeys(
                    re.findall(r"[λγθαβΣΠ]|(?<![A-Za-z])(?:[A-Za-z])(?=\s*[=≤≥≈+\-*/^])", text)
                )
            )
            results.append((text, symbols, chunk))
    return results


def _formula_explanation(text: str, chunk: Chunk) -> str | None:
    """Extract a distinct neighboring source label, never duplicate the formula RHS."""
    units = _study_units(chunk.text)
    formula_index = next((index for index, unit in enumerate(units) if unit == text), None)
    if formula_index is None:
        return None
    for candidate in reversed(units[max(0, formula_index - 2) : formula_index]):
        if not candidate.endswith(":"):
            continue
        explanation = _clean_candidate_text(candidate).strip(" .;:")
        words = re.findall(r"[A-Za-z]{2,}", explanation)
        if (
            3 <= len(words) <= 20
            and not re.search(r"(?:=|≤|≥|≈|→|∈|\.{2,}|[‥…⋯])", explanation)
            and explanation.casefold() not in text.casefold()
        ):
            return explanation
    return None


def _study_units(text: str) -> list[str]:
    """Keep bullet boundaries while joining lowercase PDF line wraps."""
    normalized_text = text.replace("§", "\n")
    normalized_text = re.sub(r"(?<=\S)[▪•■]\s+", "\n", normalized_text)
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    units: list[str] = []
    current = ""
    for raw in lines:
        is_bullet = bool(re.match(r"^[▪•■\-–—]|^\d+[.)]\s", raw))
        line = re.sub(r"^[\s•▪■\-–—]+", "", raw).strip()
        if not line:
            continue
        if (
            current
            and not is_bullet
            and len(line) > 1
            and line[0].islower()
            and not re.search(r"[.!?。！？:]$", current)
        ):
            current = f"{current} {line}"
            continue
        if current:
            units.extend(_split_study_sentences(current))
        current = line
    if current:
        units.extend(_split_study_sentences(current))
    return units


def _split_study_sentences(text: str) -> list[str]:
    results = []
    text = re.sub(r"(?<=[.!?])(?=[A-Z])", " ", text)
    for part in re.split(r"(?<=[.!?。！？])(?=\s+[A-Z㐀-鿿])", text):
        normalized = re.sub(r"\s+", " ", part).strip()
        if not normalized:
            continue
        # PDF diagrams often append isolated node labels ("a s s, a s,a,s’")
        # to an otherwise useful text line. They are layout debris, not prose.
        normalized = re.sub(
            r"\s+(?:[A-Za-z](?:\s+|,\s*)){5,}[A-Za-z][’']?$",
            "",
            normalized,
        ).strip()
        if normalized:
            results.append(normalized)
    return results


def _looks_like_title(text: str) -> bool:
    if len(text) > 70 or re.search(r"[:;.!?=。！？]", text):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", text)
    return 1 <= len(words) <= 8 and all(word[0].isupper() or word.isupper() for word in words)


def _looks_incomplete(text: str) -> bool:
    normalized = text.casefold().strip()
    word_tokens = re.findall(r"[A-Za-z]+", text)
    isolated_letters = sum(len(token) == 1 for token in word_tokens)
    return (
        not text[0].isupper()
        or bool(re.search(r"\b(?:are|did|do|does|had|has|have|is|was|were)$", normalized))
        or bool(re.search(r"\b(?:we(?:’|')re|we are|is|are|by)\s+[a-z]+ing$", normalized))
        or bool(re.search(r"\b(?:t|th)\s+e\b", normalized))
        or bool(re.match(r"^(?:only has|where is)\b", normalized))
        or bool(
            re.search(
                r"\b[bcdfghjklmnpqrstvwxyz]{2,}\s+[bcdfghjklmnpqrstvwxyz]{2,}\b",
                normalized,
            )
        )
        or bool(re.search(r"[:;](?=[A-Z])", text))
        or text.count("=") > 2
        or (isolated_letters >= 3 and isolated_letters / max(len(word_tokens), 1) >= 0.3)
        or any(
            text.count(left) != text.count(right)
            for left, right in (("(", ")"), ("[", "]"), ("{", "}"))
        )
    )


def _summary_text(text: str) -> str:
    """Preserve source punctuation and minimally close complete slide bullets."""
    stripped = text.strip()
    if re.search(r"[.!?。！？]$", stripped):
        return stripped
    if re.match(
        r"^(?:how|what|when|where|which|who|why|can|could|do|does|is|are)\b",
        stripped,
        re.IGNORECASE,
    ):
        return f"{stripped}?"
    return f"{stripped}."


def _clean_candidate_text(text: str) -> str:
    text = re.sub(r"\b([A-Za-z]{2,})-\s+([a-z]{2,})\b", r"\1\2", text)
    text = re.sub(r"(?:\s+[A-Za-z]){2,}$", "", text)
    return re.sub(r"\s+", " ", text).strip()
