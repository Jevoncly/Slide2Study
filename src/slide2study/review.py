from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from slide2study.models import Chunk, RenderedPage


def build_review_pack(
    examples: list[dict[str, Any]],
    chunks: Sequence[Chunk],
    output: str | Path,
    rendered_pages: Sequence[RenderedPage] = (),
) -> dict[str, Any]:
    """Create a private, self-contained HTML workflow for reviewing candidate QA."""
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    assets = target.parent / f"{target.stem}_assets"
    assets.mkdir(parents=True, exist_ok=True)

    page_chunks = {
        (chunk.document_id, chunk.page_start): chunk
        for chunk in chunks
        if chunk.level == "page" and chunk.page_start == chunk.page_end
    }
    image_pages = {(page.document_id, page.page_number): page for page in rendered_pages}
    copied_images: dict[tuple[str, int], str] = {}
    missing_images: set[tuple[str, int]] = set()
    review_examples = []

    for example in examples:
        document_id = str(example["document_id"])
        evidence_pages = []
        for page_number in example.get("relevant_pages", []):
            key = (document_id, int(page_number))
            chunk = page_chunks.get(key)
            rendered = image_pages.get(key)
            image_path = None
            if rendered:
                image_path = copied_images.get(key)
                if image_path is None:
                    source = Path(rendered.image_path)
                    if source.is_file():
                        destination = assets / (
                            f"{document_id}-page-{int(page_number):04d}{source.suffix.lower()}"
                        )
                        shutil.copy2(source, destination)
                        image_path = destination.relative_to(target.parent).as_posix()
                        copied_images[key] = image_path
                    else:
                        missing_images.add(key)
            else:
                missing_images.add(key)
            evidence_pages.append(
                {
                    "page_number": int(page_number),
                    "source_name": chunk.metadata.get("source_name") if chunk else None,
                    "text": chunk.text if chunk else "",
                    "image": image_path,
                }
            )
        review_examples.append({"record": example, "evidence_pages": evidence_pages})

    serialized = json.dumps(examples, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload = {
        "fingerprint": hashlib.sha256(serialized).hexdigest()[:16],
        "examples": review_examples,
    }
    target.write_text(_render_html(payload), encoding="utf-8")
    return {
        "output": str(target),
        "examples": len(examples),
        "evidence_pages": sum(len(item["evidence_pages"]) for item in review_examples),
        "copied_images": len(copied_images),
        "missing_images": len(missing_images),
    }


def _render_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Slide2Study QA Review</title>
<style>
:root {{ color-scheme: light; font-family: Inter, "Segoe UI", sans-serif; }}
body {{ margin: 0; background: #f4f6f8; color: #17202a; }}
header {{ position: sticky; top: 0; z-index: 2; padding: 16px 24px; background: #102a43;
  color: white; box-shadow: 0 2px 8px #0003; }}
h1 {{ margin: 0 0 10px; font-size: 22px; }}
.toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
select, button, textarea {{ font: inherit; }}
select, button {{ padding: 7px 10px; border-radius: 7px; border: 1px solid #bcccdc; }}
button {{ cursor: pointer; background: white; }}
#progress {{ font-weight: 650; margin-left: auto; }}
main {{ max-width: 1180px; margin: 20px auto; padding: 0 16px 60px; }}
.card {{ background: white; border-radius: 12px; margin: 16px 0; padding: 18px;
  box-shadow: 0 2px 10px #102a4314; border-left: 6px solid #829ab1; }}
.card.verified {{ border-left-color: #1f9d55; }}
.card.needs_revision {{ border-left-color: #f0a202; }}
.card.rejected {{ border-left-color: #d64545; opacity: .78; }}
.meta {{ display: flex; gap: 8px; flex-wrap: wrap; color: #52667a; font-size: 13px; }}
.tag {{ background: #e8eef3; border-radius: 999px; padding: 3px 8px; }}
.query {{ font-size: 18px; font-weight: 700; margin: 12px 0 8px; }}
.hint {{ background: #fff8df; border-radius: 8px; padding: 10px; }}
.evidence {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(330px,1fr)); gap: 12px;
  margin-top: 12px; }}
.page {{ border: 1px solid #d9e2ec; border-radius: 9px; overflow: hidden; }}
.page h3 {{ margin: 0; padding: 8px 10px; background: #eef3f7; font-size: 14px; }}
.page img {{ display: block; width: 100%; max-height: 520px; object-fit: contain;
  background: #111; }}
.page pre {{ margin: 0; padding: 10px; max-height: 230px; overflow: auto; white-space: pre-wrap;
  font: 12px/1.45 Consolas, monospace; }}
.decision {{ margin-top: 14px; display: grid; grid-template-columns: 190px 1fr; gap: 10px; }}
textarea {{ min-height: 55px; resize: vertical; padding: 8px; border: 1px solid #bcccdc;
  border-radius: 7px; }}
.empty {{ text-align: center; padding: 50px; color: #627d98; }}
@media(max-width:700px) {{ .decision {{ grid-template-columns: 1fr; }}
  #progress {{ width: 100%; }} }}
</style>
</head>
<body>
<header>
  <h1>Slide2Study QA 人工复核</h1>
  <div class="toolbar">
    <select id="typeFilter"><option value="">全部题型</option></select>
    <select id="splitFilter"><option value="">全部 split</option></select>
    <select id="decisionFilter"><option value="">全部状态</option>
      <option value="unreviewed">未复核</option><option value="verified">通过</option>
      <option value="needs_revision">需修改</option><option value="rejected">拒绝</option>
    </select>
    <button id="exportButton">导出复核 JSONL</button>
    <span id="progress"></span>
  </div>
</header>
<main id="cards"></main>
<script>
const payload = {data};
const storageKey = `slide2study-review-${{payload.fingerprint}}`;
let state = {{}};
try {{ state = JSON.parse(localStorage.getItem(storageKey) || "{{}}"); }} catch {{ state = {{}}; }}
const cards = document.getElementById("cards");
const typeFilter = document.getElementById("typeFilter");
const splitFilter = document.getElementById("splitFilter");
const decisionFilter = document.getElementById("decisionFilter");
function addOptions(select, values) {{
  [...new Set(values)].sort().forEach(value => {{
    const option = document.createElement("option"); option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }});
}}
addOptions(typeFilter, payload.examples.map(item => item.record.question_type));
addOptions(splitFilter, payload.examples.map(item => item.record.split));
function save() {{
  try {{ localStorage.setItem(storageKey, JSON.stringify(state)); }} catch {{ /* file mode */ }}
  render();
}}
function currentReview(record) {{
  if (state[record.id]) return state[record.id];
  return {{
    decision: record.review_decision ||
      (record.annotation_status === "verified" ? "verified" : "unreviewed"),
    notes: record.review_notes || ""
  }};
}}
function element(tag, className, text) {{
  const value = document.createElement(tag); if (className) value.className = className;
  if (text !== undefined) value.textContent = text; return value;
}}
function render() {{
  cards.replaceChildren(); let visible = 0;
  payload.examples.forEach(item => {{
    const record = item.record; const review = currentReview(record);
    const decision = review.decision || "unreviewed";
    if (typeFilter.value && record.question_type !== typeFilter.value) return;
    if (splitFilter.value && record.split !== splitFilter.value) return;
    if (decisionFilter.value && decision !== decisionFilter.value) return;
    visible += 1;
    const card = element("article", `card ${{decision === "unreviewed" ? "" : decision}}`);
    const meta = element("div", "meta");
    [record.id, record.question_type, record.split, record.annotation_status,
      record.document_id].forEach(value => meta.appendChild(element("span", "tag", value)));
    card.append(meta, element("div", "query", record.query));
    if (record.answer_hint)
      card.appendChild(element("div", "hint", `答案提示：${{record.answer_hint}}`));
    const evidence = element("div", "evidence");
    item.evidence_pages.forEach(page => {{
      const box = element("section", "page");
      box.appendChild(element("h3", "",
        `${{page.source_name || record.document_id}} · p.${{page.page_number}}`));
      if (page.image) {{ const image = document.createElement("img"); image.src = page.image;
        image.alt = `Evidence page ${{page.page_number}}`; image.loading = "lazy";
        box.appendChild(image); }}
      else box.appendChild(element("div", "hint", "未提供页面图片，以下为解析文本。"));
      box.appendChild(element("pre", "", page.text || "（没有可提取文本）")); evidence.appendChild(box);
    }});
    card.appendChild(evidence);
    const controls = element("div", "decision");
    const select = document.createElement("select");
    [["unreviewed","未复核"],["verified","通过"],["needs_revision","需修改"],
      ["rejected","拒绝"]].forEach(([value,label]) => {{
        const option = document.createElement("option");
        option.value=value; option.textContent=label; select.appendChild(option); }});
    select.value = decision; select.onchange = () => {{ state[record.id] = {{...review,
      decision: select.value}}; save(); }};
    const notes = document.createElement("textarea"); notes.placeholder = "复核备注或修改建议";
    notes.value = review.notes || ""; notes.onchange = () => {{
      state[record.id] = {{...review, notes: notes.value}}; save(); }};
    controls.append(select, notes); card.appendChild(controls); cards.appendChild(card);
  }});
  if (!visible) cards.appendChild(element("div", "empty", "没有符合筛选条件的记录。"));
  const reviewed = payload.examples.filter(item =>
    currentReview(item.record).decision !== "unreviewed").length;
  document.getElementById("progress").textContent =
    `已复核 ${{reviewed}} / ${{payload.examples.length}}`;
}}
[typeFilter, splitFilter, decisionFilter].forEach(select => select.onchange = render);
document.getElementById("exportButton").onclick = () => {{
  const rows = payload.examples.map(item => {{
    const record = {{...item.record}}; const review = currentReview(record);
    record.review_decision = review.decision || "unreviewed";
    if (review.notes) record.review_notes = review.notes;
    if (review.decision === "verified") record.annotation_status = "verified";
    return JSON.stringify(record);
  }});
  const blob = new Blob([rows.join("\\n") + "\\n"], {{type: "application/x-ndjson"}});
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
  link.download = `reviewed-${{payload.fingerprint}}.jsonl`; link.click();
  URL.revokeObjectURL(link.href);
}};
render();
</script>
</body>
</html>
"""
