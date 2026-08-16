from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from slide2study.models import Chunk

REVIEW_DECISIONS = {"valid_negative", "false_negative", "uncertain", "pending"}
TRIPLET_FIELDS = (
    "query",
    "positive_chunk_id",
    "negative_chunk_id",
    "negative_rank",
    "miner",
    "difficulty",
)


def apply_negative_reviews(
    rows: list[dict], *, require_complete: bool = True
) -> tuple[list[dict], dict]:
    """Keep reviewed valid negatives and return canonical training triplets."""
    decisions = Counter()
    review_ids = set()
    query_count = set()
    retained_queries = set()
    triplets = []
    for line_number, row in enumerate(rows, 1):
        review_id = str(row.get("review_id", "")).strip()
        if review_id:
            if review_id in review_ids:
                raise ValueError(f"Duplicate review_id: {review_id}")
            review_ids.add(review_id)
        decision = str(row.get("review_decision", "pending") or "pending")
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"Unsupported review_decision on row {line_number}: {decision}")
        decisions[decision] += 1
        query = str(row.get("query", "")).strip()
        if query:
            query_count.add(query)
        if decision != "valid_negative":
            continue
        missing = [field for field in TRIPLET_FIELDS if row.get(field) in (None, "")]
        if missing:
            raise ValueError(
                f"Valid negative on row {line_number} is missing: {', '.join(missing)}"
            )
        triplets.append({field: row[field] for field in TRIPLET_FIELDS})
        retained_queries.add(query)
    incomplete = decisions["pending"] + decisions["uncertain"]
    if require_complete and incomplete:
        raise ValueError(
            "Negative review is incomplete: "
            f"{decisions['pending']} pending and {decisions['uncertain']} uncertain"
        )
    difficulty_counts = Counter(row["difficulty"] for row in triplets)
    summary = {
        "rows": len(rows),
        "decisions": {name: decisions[name] for name in sorted(REVIEW_DECISIONS)},
        "retained_triplets": len(triplets),
        "rejected_triplets": len(rows) - len(triplets),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "queries": len(query_count),
        "queries_retained": len(retained_queries),
    }
    return triplets, summary


def build_negative_review_pack(
    triplets: list[dict], chunks: list[Chunk], output: str | Path
) -> dict:
    """Build a private local HTML workflow for reviewing mined negatives."""
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    rows = []
    missing_chunks = set()
    for index, triplet in enumerate(triplets):
        positive = by_id.get(triplet.get("positive_chunk_id"))
        negative = by_id.get(triplet.get("negative_chunk_id"))
        if positive is None:
            missing_chunks.add(str(triplet.get("positive_chunk_id")))
        if negative is None:
            missing_chunks.add(str(triplet.get("negative_chunk_id")))
        if positive is None or negative is None:
            continue
        rows.append(
            {
                "review_id": f"negative-{index + 1:04d}",
                **triplet,
                "positive": _chunk_preview(positive),
                "negative": _chunk_preview(negative),
            }
        )
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    target.write_text(_review_html(payload, fingerprint), encoding="utf-8")
    return {
        "triplets": len(triplets),
        "reviewable": len(rows),
        "missing_chunks": sorted(missing_chunks),
        "difficulties": dict(Counter(row.get("difficulty", "unlabeled") for row in rows)),
        "fingerprint": fingerprint,
        "output": str(target),
    }


def _chunk_preview(chunk: Chunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "section": chunk.section,
        "text": chunk.text,
    }


def _review_html(payload: str, fingerprint: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Slide2Study 困难负例复核</title><style>
body{{font-family:Segoe UI,sans-serif;margin:0;background:#f5f7fb;color:#172033}}
header{{position:sticky;top:0;background:#172033;color:white;padding:14px 20px;z-index:2}}
button,select,textarea{{font:inherit}} button{{padding:8px 12px;margin-right:8px}}
#summary{{margin-left:12px}} main{{max-width:1100px;margin:auto;padding:18px}}
.card{{background:white;border:1px solid #d9deea;border-radius:10px;padding:16px;margin-bottom:14px}}
.meta{{color:#59647a;font-size:13px}} .pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.chunk{{background:#f7f9fc;border-radius:8px;padding:12px;white-space:pre-wrap}}
.negative{{border-left:4px solid #d85c5c}} .positive{{border-left:4px solid #4a8f65}}
textarea{{width:100%;min-height:52px;box-sizing:border-box;margin-top:8px}}
@media(max-width:760px){{.pair{{grid-template-columns:1fr}}}}
</style></head><body><header><button id="export">导出复核 JSONL</button>
<button id="show-pending">仅看未复核</button><span id="summary"></span></header><main id="cards"></main>
<script>const rows={payload}; const key='slide2study-negative-review-v1-{fingerprint}';
const saved=JSON.parse(localStorage.getItem(key)||'{{}}'); const cards=document.getElementById('cards');
function persist(){{localStorage.setItem(key,JSON.stringify(saved)); update();}}
function update(){{const done=Object.values(saved).filter(x=>x.decision).length;
document.getElementById('summary').textContent=`已复核 ${{done}} / ${{rows.length}}`;}}
for(const row of rows){{const state=saved[row.review_id]||{{}}; const card=document.createElement('section');
card.className='card'; card.dataset.id=row.review_id;
card.innerHTML=`<h3>${{row.review_id}} · ${{row.difficulty}} · rank ${{row.negative_rank}}</h3>
<div class="meta">${{row.miner}}</div><p><b>Query:</b> ${{escapeHtml(row.query)}}</p>
<div class="pair"><div class="chunk positive"><b>正例 · p.${{row.positive.page_start}}</b>\n${{escapeHtml(row.positive.text)}}</div>
<div class="chunk negative"><b>候选负例 · p.${{row.negative.page_start}}</b>\n${{escapeHtml(row.negative.text)}}</div></div>
<p><select><option value="">未复核</option><option value="valid_negative">有效负例</option>
<option value="false_negative">假负例</option><option value="uncertain">不确定</option></select></p>
<textarea placeholder="复核备注"></textarea>`;
const select=card.querySelector('select'), note=card.querySelector('textarea');
select.value=state.decision||''; note.value=state.note||'';
select.onchange=()=>{{saved[row.review_id]={{decision:select.value,note:note.value}};persist();}};
note.oninput=()=>{{saved[row.review_id]={{decision:select.value,note:note.value}};persist();}}; cards.appendChild(card);}}
function escapeHtml(value){{return String(value).replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]));}}
document.getElementById('show-pending').onclick=()=>{{for(const card of cards.children){{
card.hidden=Boolean((saved[card.dataset.id]||{{}}).decision);}}}};
document.getElementById('export').onclick=()=>{{const content=rows.map(row=>JSON.stringify({{...row,
review_decision:(saved[row.review_id]||{{}}).decision||'pending',review_note:(saved[row.review_id]||{{}}).note||''}})).join('\\n')+'\\n';
const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([content],{{type:'application/jsonl'}}));
link.download='reviewed-negative-triplets.jsonl';link.click();URL.revokeObjectURL(link.href);}}; update();</script></body></html>"""
