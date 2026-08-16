from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from slide2study.interfaces import CitedStudyMaterial, EvidenceCitation, StudyMaterialGenerator
from slide2study.models import SearchResult


@dataclass(frozen=True, slots=True)
class GroundedEvidence:
    evidence_id: str
    result: SearchResult

    @property
    def text(self) -> str:
        return self.result.chunk.text.strip()


@dataclass(frozen=True, slots=True)
class GeneratedDraft:
    content: str
    cited_evidence_ids: tuple[str, ...]


class AnswerBackend(Protocol):
    """Backend contract: return prose plus IDs from the supplied evidence only."""

    def generate(self, query: str, evidence: list[GroundedEvidence]) -> GeneratedDraft: ...


class ExtractiveAnswerBackend:
    """Dependency-free baseline that selects complementary evidence sentences."""

    def __init__(self, max_sentences: int = 1):
        if max_sentences <= 0:
            raise ValueError("max_sentences must be positive")
        self.max_sentences = max_sentences

    def generate(self, query: str, evidence: list[GroundedEvidence]) -> GeneratedDraft:
        query_terms = set(meaningful_tokens(query))
        candidates: list[tuple[int, int, int, str, str, frozenset[str]]] = []
        for evidence_index, item in enumerate(evidence):
            for sentence_index, sentence in enumerate(_sentences(item.text)):
                sentence_terms = set(meaningful_tokens(sentence))
                overlap_terms = query_terms & sentence_terms
                symbolic_support = any(
                    re.fullmatch(r"[\u0370-\u03ff]+", term) for term in overlap_terms
                )
                if len(overlap_terms) >= 2 or symbolic_support:
                    candidates.append(
                        (
                            -len(overlap_terms),
                            evidence_index,
                            sentence_index,
                            sentence,
                            item.evidence_id,
                            frozenset(overlap_terms),
                        )
                    )
        if not candidates:
            for evidence_index, item in enumerate(evidence):
                sentence = re.sub(r"\s+", " ", item.text).strip()
                overlap_terms = query_terms & set(meaningful_tokens(sentence))
                symbolic_support = any(
                    re.fullmatch(r"[\u0370-\u03ff]+", term) for term in overlap_terms
                )
                if len(overlap_terms) >= 2 or symbolic_support:
                    candidates.append(
                        (
                            -len(overlap_terms),
                            evidence_index,
                            0,
                            sentence,
                            item.evidence_id,
                            frozenset(overlap_terms),
                        )
                    )
        if not candidates:
            return GeneratedDraft("", ())
        candidates.sort(key=lambda item: item[:3])
        selected_sentences = []
        selected_ids = []
        covered_terms: set[str] = set()
        seen_sentences = set()
        selected_document = None
        for _, evidence_index, _, sentence, evidence_id, overlap_terms in candidates:
            normalized = re.sub(r"\s+", " ", sentence).strip()
            document_id = evidence[evidence_index].result.chunk.document_id
            if selected_document is not None and document_id != selected_document:
                continue
            if normalized in seen_sentences or (
                selected_sentences and not overlap_terms - covered_terms
            ):
                continue
            selected_sentences.append(normalized)
            selected_ids.append(evidence_id)
            selected_document = document_id
            seen_sentences.add(normalized)
            covered_terms.update(overlap_terms)
            if len(selected_sentences) >= self.max_sentences:
                break
        return GeneratedDraft("\n".join(selected_sentences), tuple(selected_ids))


class GroundedAnswerGenerator(StudyMaterialGenerator):
    """Generate answers that can cite only the retrieved evidence passed to this object."""

    def __init__(self, backend: AnswerBackend | None = None):
        self.backend = backend or ExtractiveAnswerBackend()

    def generate(
        self, query: str, evidence: list[SearchResult], kind: str = "answer"
    ) -> CitedStudyMaterial:
        usable = [result for result in evidence if result.chunk.text.strip()]
        if not query.strip() or not usable:
            return _refusal(kind, "insufficient_evidence")

        grounded = [
            GroundedEvidence(evidence_id=f"E{index}", result=result)
            for index, result in enumerate(usable, 1)
        ]
        draft = self.backend.generate(query.strip(), grounded)
        allowed = {item.evidence_id: item for item in grounded}
        raw_cited_ids = draft.cited_evidence_ids
        cited_ids = tuple(dict.fromkeys(raw_cited_ids))
        if not draft.content.strip() or not raw_cited_ids:
            return _refusal(kind, "generator_returned_no_citation")
        if re.search(r"\[(?:E\d+|[^\]]+,\s*pp?\.\d+[^\]]*)\]", draft.content, re.IGNORECASE):
            return _refusal(kind, "generator_embedded_unverified_citation")
        if any(evidence_id not in allowed for evidence_id in raw_cited_ids):
            return _refusal(kind, "generator_cited_unretrieved_evidence")

        citations = [
            citation_from_search_result(
                allowed[evidence_id].result,
                evidence_id,
            )
            for evidence_id in cited_ids
        ]
        citation_by_id = {
            citation.evidence_id: citation for citation in citations
        }
        claims = [line.strip() for line in draft.content.splitlines() if line.strip()]
        if len(claims) == len(raw_cited_ids):
            content = "\n".join(
                f"{claim} {citation_by_id[evidence_id].label}"
                for claim, evidence_id in zip(claims, raw_cited_ids)
            )
        else:
            labels = " ".join(citation.label for citation in citations)
            content = f"{draft.content.strip()} {labels}"
        return CitedStudyMaterial(
            content=content,
            citations=citations,
            kind=kind,
        )


def citation_from_search_result(
    result: SearchResult,
    evidence_id: str,
) -> EvidenceCitation:
    """Build a trusted citation from retrieved chunk metadata."""
    chunk = result.chunk
    source_name = str(
        chunk.metadata.get("source_name")
        or chunk.metadata.get("source_title")
        or chunk.document_id
    )
    source_name = re.sub(r"[\[\]\r\n]+", " ", source_name).strip() or chunk.document_id
    source_name = re.sub(r"^#+\s*", "", source_name) or chunk.document_id
    return EvidenceCitation(
        evidence_id=evidence_id,
        document_id=chunk.document_id,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        source_name=source_name,
        chunk_id=chunk.chunk_id,
    )


def _refusal(kind: str, reason: str) -> CitedStudyMaterial:
    return CitedStudyMaterial(
        content="证据不足，无法基于已检索的课件内容可靠回答。",
        citations=[],
        kind=kind,
        refused=True,
        refusal_reason=reason,
    )


def meaningful_tokens(text: str) -> list[str]:
    lowered = text.lower()
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "should",
        "the",
        "this",
        "to",
        "use",
        "used",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
    latin = [
        _normalize_latin(token)
        for token in re.findall(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", lowered)
        if token not in stopwords
    ]
    greek = re.findall(r"[\u0370-\u03ff]+", lowered)
    cjk = []
    for run in re.findall(r"[\u3400-\u9fff]+", lowered):
        cjk.extend([run] if len(run) == 1 else [run[index : index + 2] for index in range(len(run) - 1)])
    return latin + greek + cjk


def _normalize_latin(token: str) -> str:
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+", normalized)
        if part.strip()
    ]
