from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

from slide2study.models import RenderedPage
from slide2study.study import ChapterStudyGuide


def stratified_section_sample(
    guides: list[ChapterStudyGuide] | tuple[ChapterStudyGuide, ...],
    sample_size: int,
) -> list[ChapterStudyGuide]:
    """Round-robin documents so a review is not dominated by one deck."""
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    grouped: dict[str, list[ChapterStudyGuide]] = defaultdict(list)
    for guide in guides:
        grouped[guide.document_id].append(guide)
    selected = []
    offset = 0
    document_ids = sorted(grouped)
    while len(selected) < min(sample_size, len(guides)):
        added = False
        for document_id in document_ids:
            group = grouped[document_id]
            if offset < len(group):
                selected.append(group[offset])
                added = True
                if len(selected) >= sample_size:
                    break
        if not added:
            break
        offset += 1
    return selected


def build_study_review_pack(
    guides: list[ChapterStudyGuide] | tuple[ChapterStudyGuide, ...],
    rendered_pages: list[RenderedPage],
    output_dir: str | Path,
) -> Path:
    """Build a private local review page for generated study materials."""
    if not guides:
        raise ValueError("At least one sampled guide is required")
    target = Path(output_dir)
    assets = target / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    page_lookup = {(page.document_id, page.page_number): page for page in rendered_pages}
    page_assets = {}
    missing = []
    for guide in guides:
        for page_number in guide.to_dict()["cited_pages"]:
            key = (guide.document_id, page_number)
            if f"{key[0]}:{key[1]}" in page_assets:
                continue
            page = page_lookup.get(key)
            if page is None or not Path(page.image_path).is_file():
                missing.append(f"{key[0]}:p.{key[1]}")
                continue
            suffix = Path(page.image_path).suffix.lower() or ".png"
            name = f"{key[0]}-page-{key[1]:04d}{suffix}"
            shutil.copy2(page.image_path, assets / name)
            page_assets[f"{key[0]}:{key[1]}"] = f"assets/{name}"
    if missing:
        raise ValueError(f"Missing rendered page images for review evidence: {sorted(set(missing))}")

    records = []
    for index, guide in enumerate(guides, 1):
        value = guide.to_dict()
        citations = [
            item["citation"]
            for field in ("summary", "concepts", "flashcards", "formulas")
            for item in value[field]
        ]
        records.append(
            {
                **value,
                "review_id": f"study-review-{index:03d}",
                "source_name": citations[0]["source_name"] if citations else guide.document_id,
            }
        )
    payload = {"records": records, "page_assets": page_assets}
    serialized = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    html = (
        _HTML.replace("__REVIEW_DATA__", serialized)
        .replace("__FINGERPRINT__", fingerprint)
    )
    output = target / "index.html"
    output.write_text(html, encoding="utf-8")
    return output


_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Slide2Study · 生成质量复核</title>
<style>
:root{--ink:#18232d;--muted:#68737f;--paper:#f3f0e8;--panel:#fffdf8;--line:#d8d1c4;--red:#c84d35;--green:#27705a;--amber:#a66a16}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#f9f6ef,var(--paper));color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}.shell{width:min(1600px,calc(100% - 30px));margin:auto;padding:20px 0}.top{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:16px}h1{margin:0;font:700 clamp(28px,4vw,44px)/1.1 Georgia,serif}.muted{color:var(--muted)}.actions{display:flex;gap:8px;flex-wrap:wrap}button{font:inherit}.btn{border:1px solid var(--line);border-radius:10px;padding:9px 13px;background:white;cursor:pointer;font-weight:700}.btn.primary{color:white;background:var(--ink);border-color:var(--ink)}.layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(380px,.85fr);gap:18px;align-items:start}.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 14px 38px #3d332619}.record-head{padding:18px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:16px}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:800;color:var(--red)}h2{margin:3px 0 0;font:700 25px/1.2 Georgia,serif}.material{padding:18px 20px;border-bottom:1px solid var(--line)}.material h3{margin:0 0 10px;font-size:16px}.items{display:grid;gap:8px}.item{padding:11px 12px;border:1px solid #e5dfd4;border-radius:11px;background:white}.term{font-weight:800;color:#9f3d2a}.citation{border:0;background:transparent;padding:0;color:#a33f2b;text-decoration:underline;text-underline-offset:3px;cursor:pointer;font-size:12px;font-weight:800}.decision{padding:16px 20px}.decision-row{display:grid;grid-template-columns:110px 1fr;gap:10px;align-items:center;margin-bottom:10px}.choices{display:flex;gap:6px;flex-wrap:wrap}.choice{border:1px solid var(--line);border-radius:999px;padding:6px 10px;background:white;cursor:pointer;font-size:13px}.choice.selected[data-value="pass"]{color:white;background:var(--green);border-color:var(--green)}.choice.selected[data-value="needs_fix"]{color:white;background:var(--red);border-color:var(--red)}.choice.selected[data-value="not_applicable"]{color:white;background:var(--amber);border-color:var(--amber)}textarea{width:100%;min-height:80px;border:1px solid var(--line);border-radius:10px;padding:10px;resize:vertical;font:inherit}.preview{position:sticky;top:14px}.preview-head{padding:14px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line)}.page{padding:12px;background:#252a2e;display:grid;place-items:center;min-height:390px}.page img{width:100%;max-height:72vh;object-fit:contain;background:white}.page-strip{display:flex;gap:7px;padding:10px;overflow:auto}.page-chip{border:1px solid var(--line);border-radius:8px;padding:6px 9px;background:white;cursor:pointer}.page-chip.active{color:white;background:var(--red);border-color:var(--red)}.footer-nav{padding:14px 20px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line)}@media(max-width:900px){.layout{grid-template-columns:1fr}.preview{position:static}.top{align-items:flex-start;flex-direction:column}.decision-row{grid-template-columns:1fr}}
</style></head><body><main class="shell"><div class="top"><div><div class="eyebrow">Slide2Study / Human review</div><h1>生成质量复核</h1><div class="muted" id="progress"></div></div><div class="actions"><button class="btn" id="show-pending">跳到未复核</button><button class="btn primary" id="export">导出 JSONL</button></div></div><div class="layout"><section class="panel"><div class="record-head"><div><div class="eyebrow" id="source"></div><h2 id="section"></h2></div><div class="muted" id="record-id"></div></div><div id="materials"></div><div class="decision" id="decisions"></div><div class="decision"><label for="notes"><strong>复核备注</strong></label><textarea id="notes" placeholder="记录误判、过泛概念、不可作答闪卡或引用问题"></textarea></div><div class="footer-nav"><button class="btn" id="previous">← 上一个</button><span class="muted" id="position"></span><button class="btn" id="next">下一个 →</button></div></section><aside class="panel preview"><div class="preview-head"><strong id="page-title">证据页</strong><div><button class="btn" id="page-previous">←</button> <button class="btn" id="page-next">→</button></div></div><div class="page"><img id="page-image" alt="原始课件证据页"></div><div class="page-strip" id="page-strip"></div></aside></div></main><script type="application/json" id="review-data">__REVIEW_DATA__</script><script>
const app=JSON.parse(document.getElementById('review-data').textContent),key='slide2study-review:__FINGERPRINT__';let index=0,pageIndex=0;let reviews={};try{reviews=JSON.parse(localStorage.getItem(key)||'{}')}catch{reviews={}}const categories=[['summary','摘要'],['concepts','概念'],['flashcards','闪卡'],['formulas','公式/参数']];
function save(){localStorage.setItem(key,JSON.stringify(reviews))}function current(){return app.records[index]}function state(){return reviews[current().review_id]||{decisions:{},notes:''}}function cite(c){const b=document.createElement('button');b.className='citation';b.textContent=c.label+' ↗';b.onclick=()=>showPage(c.page_start);return b}
function materialBlock(field,label){const wrap=document.createElement('section');wrap.className='material';const h=document.createElement('h3');h.textContent=`${label} · ${current()[field].length}`;const list=document.createElement('div');list.className='items';current()[field].forEach(x=>{const row=document.createElement('div');row.className='item';const text=document.createElement('div');if(field==='summary')text.textContent=x.text;else if(field==='concepts'){const t=document.createElement('span');t.className='term';t.textContent=x.term+' — ';text.append(t,document.createTextNode(x.evidence_text))}else if(field==='flashcards')text.textContent=`${x.front}  →  ${x.back}`;else text.textContent=x.formula_text;row.append(text,cite(x.citation));list.append(row)});if(!current()[field].length){const empty=document.createElement('div');empty.className='muted';empty.textContent='无可复核内容';list.append(empty)}wrap.append(h,list);return wrap}
function renderDecisions(){const root=document.getElementById('decisions');root.replaceChildren();const s=state();categories.forEach(([field,label])=>{const row=document.createElement('div');row.className='decision-row';const name=document.createElement('strong');name.textContent=label;const choices=document.createElement('div');choices.className='choices';[['pass','通过'],['needs_fix','需修正'],['not_applicable','不适用']].forEach(([value,text])=>{const b=document.createElement('button');b.className='choice'+(s.decisions[field]===value?' selected':'');b.dataset.value=value;b.textContent=text;b.onclick=()=>{const next=state();next.decisions[field]=value;reviews[current().review_id]=next;save();renderDecisions();updateProgress()};choices.append(b)});row.append(name,choices);root.append(row)})}
function showPage(page){const pages=current().cited_pages;const found=pages.indexOf(page);if(found>=0)pageIndex=found;const p=pages[pageIndex];document.getElementById('page-image').src=app.page_assets[`${current().document_id}:${p}`];document.getElementById('page-title').textContent=`证据页 p.${p}`;document.querySelectorAll('.page-chip').forEach(x=>x.classList.toggle('active',Number(x.dataset.page)===p))}
function render(){const r=current(),s=state();document.getElementById('source').textContent=r.source_name;document.getElementById('section').textContent=r.section;document.getElementById('record-id').textContent=r.review_id;const materials=document.getElementById('materials');materials.replaceChildren(...categories.map(([f,l])=>materialBlock(f,l)));renderDecisions();const notes=document.getElementById('notes');notes.value=s.notes||'';notes.oninput=()=>{const next=state();next.notes=notes.value;reviews[r.review_id]=next;save()};document.getElementById('position').textContent=`${index+1} / ${app.records.length}`;const strip=document.getElementById('page-strip');strip.replaceChildren();r.cited_pages.forEach(p=>{const b=document.createElement('button');b.className='page-chip';b.dataset.page=p;b.textContent=`p.${p}`;b.onclick=()=>showPage(p);strip.append(b)});pageIndex=0;showPage(r.cited_pages[0]);updateProgress()}
function complete(r){return categories.every(([field])=>r?.decisions?.[field])}function updateProgress(){const done=app.records.filter(r=>complete(reviews[r.review_id])).length;document.getElementById('progress').textContent=`已完成 ${done} / ${app.records.length}`}
document.getElementById('previous').onclick=()=>{index=(index-1+app.records.length)%app.records.length;render()};document.getElementById('next').onclick=()=>{index=(index+1)%app.records.length;render()};document.getElementById('page-previous').onclick=()=>{pageIndex=(pageIndex-1+current().cited_pages.length)%current().cited_pages.length;showPage(current().cited_pages[pageIndex])};document.getElementById('page-next').onclick=()=>{pageIndex=(pageIndex+1)%current().cited_pages.length;showPage(current().cited_pages[pageIndex])};document.getElementById('show-pending').onclick=()=>{const found=app.records.findIndex(r=>!complete(reviews[r.review_id]));if(found>=0){index=found;render()}};document.getElementById('export').onclick=()=>{const rows=app.records.map(r=>({review_id:r.review_id,document_id:r.document_id,source_name:r.source_name,section:r.section,decisions:reviews[r.review_id]?.decisions||{},notes:reviews[r.review_id]?.notes||'',review_status:complete(reviews[r.review_id])?'reviewed':'pending'}));const blob=new Blob([rows.map(r=>JSON.stringify(r)).join('\\n')+'\\n'],{type:'application/jsonl'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='reviewed-study-materials.jsonl';a.click();URL.revokeObjectURL(a.href)};render();
</script></body></html>"""
