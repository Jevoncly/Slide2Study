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
    """Dependency-free grounded baseline that selects the best evidence sentence."""

    def generate(self, query: str, evidence: list[GroundedEvidence]) -> GeneratedDraft:
        query_terms = set(_tokens(query))
        candidates: list[tuple[int, int, int, str, str]] = []
        for evidence_index, item in enumerate(evidence):
            for sentence_index, sentence in enumerate(_sentences(item.text)):
                sentence_terms = set(_tokens(sentence))
                overlap = len(query_terms & sentence_terms)
                candidates.append(
                    (-overlap, evidence_index, sentence_index, sentence, item.evidence_id)
                )
        if not candidates:
            return GeneratedDraft("", ())
        negative_overlap, _, _, sentence, evidence_id = min(candidates)
        if negative_overlap == 0:
            return GeneratedDraft("", ())
        return GeneratedDraft(sentence, (evidence_id,))


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
        cited_ids = tuple(dict.fromkeys(draft.cited_evidence_ids))
        if not draft.content.strip() or not cited_ids:
            return _refusal(kind, "generator_returned_no_citation")
        if re.search(r"\[(?:E\d+|[^\]]+,\s*pp?\.\d+[^\]]*)\]", draft.content, re.IGNORECASE):
            return _refusal(kind, "generator_embedded_unverified_citation")
        if any(evidence_id not in allowed for evidence_id in cited_ids):
            return _refusal(kind, "generator_cited_unretrieved_evidence")

        citations = [_citation_from_evidence(allowed[evidence_id]) for evidence_id in cited_ids]
        labels = " ".join(citation.label for citation in citations)
        return CitedStudyMaterial(
            content=f"{draft.content.strip()} {labels}",
            citations=citations,
            kind=kind,
        )


def _citation_from_evidence(evidence: GroundedEvidence) -> EvidenceCitation:
    chunk = evidence.result.chunk
    source_name = str(
        chunk.metadata.get("source_name")
        or chunk.metadata.get("source_title")
        or chunk.document_id
    )
    source_name = re.sub(r"[\[\]\r\n]+", " ", source_name).strip() or chunk.document_id
    source_name = re.sub(r"^#+\s*", "", source_name) or chunk.document_id
    return EvidenceCitation(
        evidence_id=evidence.evidence_id,
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


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    stopwords = {
        "and",
        "are",
        "does",
        "for",
        "from",
        "how",
        "the",
        "this",
        "use",
        "used",
        "what",
        "when",
        "where",
        "which",
        "why",
        "with",
    }
    latin = [
        token
        for token in re.findall(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", lowered)
        if token not in stopwords
    ]
    greek = re.findall(r"[\u0370-\u03ff]+", lowered)
    cjk = []
    for run in re.findall(r"[\u3400-\u9fff]+", lowered):
        cjk.extend([run] if len(run) == 1 else [run[index : index + 2] for index in range(len(run) - 1)])
    return latin + greek + cjk


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", normalized) if part.strip()]
