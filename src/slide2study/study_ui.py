from __future__ import annotations

import json
import shutil
from pathlib import Path

from slide2study.models import RenderedPage
from slide2study.study import ChapterStudyGuide


def build_study_ui(
    guide: ChapterStudyGuide,
    rendered_pages: list[RenderedPage],
    output_dir: str | Path,
) -> Path:
    """Build a self-contained local study UI with trusted page previews."""
    target = Path(output_dir)
    assets = target / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    page_lookup = {
        (page.document_id, page.page_number): page
        for page in rendered_pages
    }
    page_assets: dict[str, str] = {}
    missing = []
    for page_number in guide.to_dict()["cited_pages"]:
        page = page_lookup.get((guide.document_id, page_number))
        if page is None or not Path(page.image_path).is_file():
            missing.append(page_number)
            continue
        suffix = Path(page.image_path).suffix.lower() or ".png"
        name = f"{guide.document_id}-page-{page_number:04d}{suffix}"
        shutil.copy2(page.image_path, assets / name)
        page_assets[str(page_number)] = f"assets/{name}"
    if missing:
        raise ValueError(f"Missing rendered page images for cited pages: {missing}")

    payload = {
        **guide.to_dict(),
        "page_assets": page_assets,
        "source_name": _source_name(guide),
    }
    serialized = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _HTML.replace("__STUDY_DATA__", serialized)
    output = target / "index.html"
    output.write_text(html, encoding="utf-8")
    return output


def _source_name(guide: ChapterStudyGuide) -> str:
    citations = [item.citation for item in (*guide.summary, *guide.flashcards)]
    return citations[0].source_name if citations else guide.document_id


_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Slide2Study · 离线复习</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17212b;
      --muted: #68737f;
      --paper: #f4f1e9;
      --panel: #fffdf8;
      --line: #d8d2c5;
      --accent: #df5b3f;
      --accent-dark: #a83d29;
      --green: #296b58;
      --shadow: 0 18px 50px rgba(41, 33, 24, .10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at 8% 5%, rgba(223, 91, 63, .12), transparent 25rem),
        linear-gradient(135deg, #f8f5ed, var(--paper));
      font: 16px/1.55 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    button { font: inherit; }
    .shell { width: min(1500px, calc(100% - 40px)); margin: 0 auto; padding: 28px 0 40px; }
    header { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
    .eyebrow { color: var(--accent-dark); font-weight: 800; letter-spacing: .14em; text-transform: uppercase; font-size: 12px; }
    h1 { margin: 4px 0 5px; font-family: Georgia, "Times New Roman", serif; font-size: clamp(30px, 4vw, 52px); line-height: 1.05; }
    .source { color: var(--muted); }
    .status { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .pill { padding: 6px 11px; border-radius: 999px; border: 1px solid var(--line); background: rgba(255,255,255,.55); font-size: 13px; font-weight: 700; }
    .pill.offline { color: var(--green); border-color: rgba(41,107,88,.35); }
    .workspace { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(380px, .95fr); gap: 22px; align-items: start; }
    .panel { background: rgba(255,253,248,.93); border: 1px solid var(--line); border-radius: 22px; box-shadow: var(--shadow); overflow: hidden; }
    .tabs { display: flex; gap: 4px; padding: 10px; border-bottom: 1px solid var(--line); background: rgba(236,231,219,.55); }
    .tab { border: 0; border-radius: 12px; padding: 10px 16px; color: var(--muted); background: transparent; cursor: pointer; font-weight: 750; }
    .tab[aria-selected="true"] { color: white; background: var(--ink); }
    .view { display: none; padding: 22px; }
    .view.active { display: block; }
    .section-head { display: flex; justify-content: space-between; gap: 20px; align-items: baseline; margin-bottom: 16px; }
    h2 { margin: 0; font: 700 25px/1.2 Georgia, serif; }
    .count { color: var(--muted); font-size: 13px; }
    .summary-list { display: grid; gap: 12px; }
    .summary-card { display: grid; grid-template-columns: 38px 1fr; gap: 12px; padding: 17px; border: 1px solid var(--line); border-radius: 15px; background: var(--panel); }
    .number { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; background: #efe8dc; color: var(--accent-dark); font: 700 15px Georgia, serif; }
    .summary-card p { margin: 2px 0 12px; }
    .citation { border: 0; padding: 0; color: var(--accent-dark); background: transparent; cursor: pointer; font-size: 13px; font-weight: 800; text-decoration: underline; text-underline-offset: 3px; }
    .flash-stage { min-height: 390px; display: grid; align-content: center; }
    .flashcard { position: relative; min-height: 290px; border: 0; border-radius: 20px; padding: 0; background: transparent; cursor: pointer; perspective: 1000px; text-align: left; }
    .flash-inner { position: absolute; inset: 0; transition: transform .48s cubic-bezier(.2,.8,.2,1); transform-style: preserve-3d; }
    .flashcard.flipped .flash-inner { transform: rotateY(180deg); }
    .face { position: absolute; inset: 0; padding: 30px; border: 1px solid var(--line); border-radius: 20px; backface-visibility: hidden; background: linear-gradient(145deg, #fffefb, #f4ecdf); box-shadow: 0 12px 28px rgba(45,35,24,.10); display: flex; flex-direction: column; justify-content: space-between; }
    .face.back { transform: rotateY(180deg); background: linear-gradient(145deg, #203b34, #28594b); color: white; }
    .face-label { font-size: 12px; text-transform: uppercase; letter-spacing: .14em; font-weight: 800; opacity: .7; }
    .prompt { font: 700 clamp(22px, 3vw, 34px)/1.3 Georgia, serif; }
    .answer { font: 700 clamp(28px, 4vw, 44px)/1.2 Georgia, serif; }
    .evidence { opacity: .78; font-size: 14px; }
    .flash-controls { margin-top: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .control { border: 1px solid var(--line); border-radius: 11px; padding: 9px 14px; background: white; cursor: pointer; font-weight: 700; }
    .control.primary { color: white; background: var(--accent); border-color: var(--accent); }
    .preview { position: sticky; top: 18px; }
    .preview-head { padding: 17px 18px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--line); }
    .preview-title { font-weight: 850; }
    .page-controls { display: flex; align-items: center; gap: 7px; }
    .icon-btn { width: 34px; height: 34px; border: 1px solid var(--line); border-radius: 10px; background: white; cursor: pointer; }
    .page-frame { background: #23272b; padding: 14px; min-height: 360px; display: grid; place-items: center; }
    .page-frame img { display: block; width: 100%; max-height: 70vh; object-fit: contain; border-radius: 5px; background: white; box-shadow: 0 8px 25px rgba(0,0,0,.28); }
    .page-strip { display: flex; gap: 8px; padding: 12px 16px; overflow-x: auto; border-top: 1px solid var(--line); }
    .page-chip { flex: 0 0 auto; border: 1px solid var(--line); border-radius: 9px; padding: 7px 11px; background: white; cursor: pointer; font-size: 13px; font-weight: 750; }
    .page-chip.active { color: white; border-color: var(--accent); background: var(--accent); }
    .empty { color: var(--muted); padding: 30px; text-align: center; }
    @media (max-width: 900px) {
      .shell { width: min(100% - 24px, 760px); padding-top: 18px; }
      header { align-items: flex-start; flex-direction: column; }
      .status { justify-content: flex-start; }
      .workspace { grid-template-columns: 1fr; }
      .preview { position: static; }
    }
    @media (prefers-reduced-motion: reduce) { .flash-inner { transition: none; } }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <div class="eyebrow">Slide2Study / Study desk</div>
        <h1 id="chapter-title"></h1>
        <div class="source" id="source-name"></div>
      </div>
      <div class="status">
        <span class="pill offline">● 完全离线</span>
        <span class="pill" id="page-count"></span>
      </div>
    </header>
    <div class="workspace">
      <section class="panel">
        <nav class="tabs" aria-label="学习模式">
          <button class="tab" data-tab="summary" aria-selected="true">章节摘要</button>
          <button class="tab" data-tab="flashcards" aria-selected="false">闪卡练习</button>
        </nav>
        <div class="view active" id="summary-view">
          <div class="section-head"><h2>核心内容</h2><span class="count" id="summary-count"></span></div>
          <div class="summary-list" id="summary-list"></div>
        </div>
        <div class="view" id="flashcards-view">
          <div class="section-head"><h2>主动回忆</h2><span class="count" id="flash-progress"></span></div>
          <div class="flash-stage" id="flash-stage"></div>
          <div class="flash-controls">
            <button class="control" id="previous-card">← 上一张</button>
            <button class="control primary" id="master-card">标记已掌握</button>
            <button class="control" id="next-card">下一张 →</button>
          </div>
        </div>
      </section>
      <aside class="panel preview">
        <div class="preview-head">
          <div><div class="eyebrow">Evidence</div><div class="preview-title" id="preview-title">原始课件</div></div>
          <div class="page-controls"><button class="icon-btn" id="previous-page" aria-label="上一证据页">←</button><button class="icon-btn" id="next-page" aria-label="下一证据页">→</button></div>
        </div>
        <div class="page-frame"><img id="page-image" alt="引用的原始课件页面"></div>
        <div class="page-strip" id="page-strip"></div>
      </aside>
    </div>
  </main>
  <script type="application/json" id="study-data">__STUDY_DATA__</script>
  <script>
    const model = JSON.parse(document.getElementById('study-data').textContent);
    const pages = model.cited_pages;
    let pageIndex = 0;
    let cardIndex = 0;
    const masteryKey = `slide2study:${model.document_id}:${model.section}:mastery`;
    let mastered;
    try { mastered = new Set(JSON.parse(localStorage.getItem(masteryKey) || '[]')); }
    catch { mastered = new Set(); }

    document.getElementById('chapter-title').textContent = model.section;
    document.getElementById('source-name').textContent = model.source_name;
    document.getElementById('page-count').textContent = `${pages.length} 个证据页`;
    document.getElementById('summary-count').textContent = `${model.summary.length} 条 · 均可追溯`;

    function citationButton(citation) {
      const button = document.createElement('button');
      button.className = 'citation';
      button.textContent = citation.label + ' ↗';
      button.addEventListener('click', () => showPage(citation.page_start));
      return button;
    }

    model.summary.forEach((item, index) => {
      const card = document.createElement('article');
      card.className = 'summary-card';
      const number = document.createElement('div');
      number.className = 'number';
      number.textContent = String(index + 1).padStart(2, '0');
      const body = document.createElement('div');
      const text = document.createElement('p');
      text.textContent = item.text;
      body.append(text, citationButton(item.citation));
      card.append(number, body);
      document.getElementById('summary-list').append(card);
    });

    function renderFlashcard() {
      const stage = document.getElementById('flash-stage');
      stage.replaceChildren();
      if (!model.flashcards.length) {
        stage.innerHTML = '<div class="empty">本章节没有可生成的闪卡。</div>';
        ['previous-card', 'next-card', 'master-card'].forEach(id => document.getElementById(id).disabled = true);
        return;
      }
      const item = model.flashcards[cardIndex];
      const card = document.createElement('button');
      card.className = 'flashcard';
      card.setAttribute('aria-label', '点击翻转闪卡');
      card.innerHTML = '<span class="flash-inner"><span class="face front"><span class="face-label">问题 · 点击查看答案</span><span class="prompt"></span><span class="evidence front-evidence"></span></span><span class="face back"><span class="face-label">答案</span><span class="answer"></span><span class="evidence"></span></span></span>';
      card.querySelector('.prompt').textContent = item.front;
      card.querySelector('.answer').textContent = item.back;
      card.querySelector('.front-evidence').textContent = `证据 ${item.citation.label}`;
      card.querySelector('.back .evidence').textContent = item.evidence_text;
      card.addEventListener('click', () => {
        card.classList.toggle('flipped');
        showPage(item.citation.page_start);
      });
      stage.append(card);
      document.getElementById('flash-progress').textContent = `${cardIndex + 1} / ${model.flashcards.length} · 已掌握 ${mastered.size}`;
      const master = document.getElementById('master-card');
      master.textContent = mastered.has(cardIndex) ? '✓ 已掌握' : '标记已掌握';
    }

    function showPage(page) {
      const index = pages.indexOf(page);
      if (index >= 0) pageIndex = index;
      const current = pages[pageIndex];
      document.getElementById('page-image').src = model.page_assets[String(current)];
      document.getElementById('preview-title').textContent = `原始课件 · 第 ${current} 页`;
      document.querySelectorAll('.page-chip').forEach(chip => chip.classList.toggle('active', Number(chip.dataset.page) === current));
    }

    pages.forEach(page => {
      const chip = document.createElement('button');
      chip.className = 'page-chip';
      chip.dataset.page = page;
      chip.textContent = `p.${page}`;
      chip.addEventListener('click', () => showPage(page));
      document.getElementById('page-strip').append(chip);
    });

    document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(item => item.setAttribute('aria-selected', String(item === tab)));
      document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === `${tab.dataset.tab}-view`));
    }));
    document.getElementById('previous-card').addEventListener('click', () => { if (!model.flashcards.length) return; cardIndex = (cardIndex - 1 + model.flashcards.length) % model.flashcards.length; renderFlashcard(); });
    document.getElementById('next-card').addEventListener('click', () => { if (!model.flashcards.length) return; cardIndex = (cardIndex + 1) % model.flashcards.length; renderFlashcard(); });
    document.getElementById('master-card').addEventListener('click', () => {
      if (!model.flashcards.length) return;
      mastered.has(cardIndex) ? mastered.delete(cardIndex) : mastered.add(cardIndex);
      localStorage.setItem(masteryKey, JSON.stringify([...mastered]));
      renderFlashcard();
    });
    document.getElementById('previous-page').addEventListener('click', () => { pageIndex = (pageIndex - 1 + pages.length) % pages.length; showPage(pages[pageIndex]); });
    document.getElementById('next-page').addEventListener('click', () => { pageIndex = (pageIndex + 1) % pages.length; showPage(pages[pageIndex]); });

    renderFlashcard();
    showPage(pages[0]);
  </script>
</body>
</html>
"""
