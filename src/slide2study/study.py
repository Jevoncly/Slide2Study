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

    def to_dict(self) -> dict[str, object]:
        return {
            "formula_text": self.formula_text,
            "symbols": list(self.symbols),
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
    source_chunk_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "section": self.section,
            "summary": [item.to_dict() for item in self.summary],
            "flashcards": [item.to_dict() for item in self.flashcards],
            "concepts": [item.to_dict() for item in self.concepts],
            "formulas": [item.to_dict() for item in self.formulas],
            "source_chunk_ids": list(self.source_chunk_ids),
            "cited_pages": sorted(
                {
                    page
                    for item in (*self.summary, *self.flashcards, *self.concepts, *self.formulas)
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
) -> ChapterStudyGuide:
    """Create an exact-extractive chapter summary and cloze flashcards."""
    if summary_bullets <= 0 or flashcard_count <= 0:
        raise ValueError("summary_bullets and flashcard_count must be positive")
    if concept_count < 0 or formula_count < 0:
        raise ValueError("concept_count and formula_count cannot be negative")

    passages = [chunk for chunk in chunks if chunk.level == "passage" and chunk.text.strip()]
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

    candidates = _build_candidates(passages)
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
            text=item.text,
            citation=_citation(item.chunk, f"S{index}"),
        )
        for index, item in enumerate(summary_candidates, 1)
    )

    flashcards = []
    used_terms: set[str] = set()
    for item in _select_diverse(candidates, term_frequency, len(candidates)):
        term = _flashcard_term(item, term_frequency, used_terms)
        if term is None:
            continue
        front = re.sub(re.escape(term), "_____", item.text, count=1, flags=re.IGNORECASE)
        if front == item.text:
            continue
        used_terms.add(term.casefold())
        flashcards.append(
            Flashcard(
                front=front,
                back=term,
                evidence_text=item.text,
                citation=_citation(item.chunk, f"F{len(flashcards) + 1}"),
            )
        )
        if len(flashcards) >= flashcard_count:
            break

    concepts = tuple(
        KeyConcept(
            term=card.back,
            evidence_text=card.evidence_text,
            citation=_citation(
                next(item.chunk for item in candidates if item.text == card.evidence_text),
                f"C{index}",
            ),
        )
        for index, card in enumerate(flashcards[:concept_count], 1)
    )
    formulas = tuple(
        FormulaEvidence(
            formula_text=text,
            symbols=symbols,
            citation=_citation(chunk, f"M{index}"),
        )
        for index, (text, symbols, chunk) in enumerate(
            _formula_evidence(passages)[:formula_count], 1
        )
    )

    return ChapterStudyGuide(
        document_id=document_id,
        section=selected_section,
        summary=summary,
        flashcards=tuple(flashcards),
        concepts=concepts,
        formulas=formulas,
        source_chunk_ids=tuple(
            dict.fromkeys(
                [item.chunk.chunk_id for item in candidates]
                + [item.citation.chunk_id for item in formulas]
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
                    passages,
                    document_id=selected_document,
                    section=selected_section,
                    summary_bullets=summary_bullets,
                    flashcard_count=flashcard_count,
                    concept_count=concept_count,
                    formula_count=formula_count,
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
    )
    candidates = []
    seen = set()
    order = 0
    for chunk in chunks:
        raw_text = chunk.text.replace("§", "\n")
        for part in re.split(r"(?:\n+|(?<=[.!?。！？])(?=\s|[A-Z]))", raw_text):
            text = re.sub(r"\s+", " ", part).strip()
            text = re.sub(r"^[\s•▪■\-–—]+", "", text).strip()
            text = re.sub(r"\s+[A-Z][A-Za-z-]{1,20}\?$", "", text).strip()
            terms = frozenset(meaningful_tokens(text))
            key = text.casefold()
            if (
                len(text) < 20
                or len(terms) < 3
                or key in seen
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


def _flashcard_term(
    candidate: _Candidate,
    frequencies: Counter[str],
    used_terms: set[str],
) -> str | None:
    phrase_stopwords = {"and", "are", "for", "from", "into", "that", "the", "this", "with"}
    phrases = []
    for match in re.finditer(
        r"\b[A-Z][A-Za-z0-9_-]{3,}\s+[A-Za-z][A-Za-z0-9_-]{3,}\b",
        candidate.text,
    ):
        phrase = match.group(0)
        words = phrase.casefold().split()
        if words[1] in phrase_stopwords or phrase.casefold() in used_terms:
            continue
        phrase_terms = meaningful_tokens(phrase)
        if phrase_terms and set(phrase_terms) <= candidate.terms:
            phrases.append(phrase)
    if phrases:
        return max(
            phrases,
            key=lambda phrase: (
                sum(frequencies[term] for term in meaningful_tokens(phrase)),
                len(phrase),
                -candidate.text.find(phrase),
            ),
        )
    visible_terms = []
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_-]{3,}|[\u3400-\u9fff]{2,6}", candidate.text):
        term = match.group(0)
        normalized = term.casefold()
        if normalized in used_terms or normalized not in candidate.terms:
            continue
        visible_terms.append(term)
    if not visible_terms:
        return None
    return max(
        visible_terms,
        key=lambda term: (frequencies[term.casefold()], len(term), -candidate.text.find(term)),
    )


def _citation(chunk: Chunk, evidence_id: str) -> EvidenceCitation:
    return citation_from_search_result(SearchResult(chunk=chunk, score=1.0, rank=1), evidence_id)


def _formula_evidence(chunks: list[Chunk]) -> list[tuple[str, tuple[str, ...], Chunk]]:
    results = []
    seen = set()
    math_pattern = re.compile(r"(?:=|≤|≥|≈|→|∑|Σ|Π|λ|γ|θ|α|β|\^|√)")
    for chunk in chunks:
        for raw in re.split(r"[§\n▪•■]+", chunk.text):
            text = re.sub(r"\s+", " ", raw).strip()
            if not (3 <= len(text) <= 240 and math_pattern.search(text)):
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
