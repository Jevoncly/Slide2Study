# Slide2Study 项目进度与迁移交接

最后更新：2026-08-16（Australia/Sydney）

## 1. 项目位置与 Git 状态

- 规范工作目录：`E:\Work\Slide2study`
- 课程测试数据：`D:\important files\Unimelb\S1`
- GitHub：<https://github.com/Jevoncly/Slide2Study>
- 当前分支：`agent/document-parsing`
- 上一阶段提交：`7bde05e Add reproducible retrieval evaluation reports`
- 远程跟踪分支：`origin/agent/document-parsing`
- Draft PR：<https://github.com/Jevoncly/Slide2Study/pull/1>

`7bde05e` 尚未推送；本阶段在此基线上推进真实多课程 pilot。

## 2. 项目目标

Slide2Study 是一个面向算法工程师简历的大模型项目：将课程 Slides/PDF 转换为带页码和
证据引用的复习笔记、闪卡与分层题库。算法主线是多模态、结构感知 RAG，重点解决传统
OCR 加固定文本切块对图表、公式、章节结构和跨页知识检索效果差的问题。

模型策略：不从零预训练大模型；生成端先接现成模型，自己训练和评测关键检索模块。
训练方向包括合成 QA、hard-negative mining、对比学习、Dense Retriever、Reranker 和
multimodal page retriever。

## 3. 已完成模块

### 3.1 文档解析与质量诊断

- 支持 PDF、PPTX、Markdown 和纯文本解析。
- PDF 保存页码、尺寸、旋转角度和图片对象数量。
- PPTX 提取标题、文本、表格、阅读顺序、布局位置和演讲者备注。
- 清理跨页重复页眉、页脚与页码，同时在 `metadata.raw_text` 中保留原始证据。
- 页面角色分类：`content`、`boilerplate`、`section_divider`、`visual_only`、`empty`。
- 视觉风险信号：低文本高图片、大量图片对象和密集视觉布局。
- 低价值文本页默认不进入 BM25，但页面和页码不会被删除，可供视觉检索使用。

主要代码：`src/slide2study/parsing.py`、`src/slide2study/models.py`。

### 3.2 三层结构感知切块

- `section -> page -> passage` 三层 chunk。
- 支持跨页章节及稳定的 `parent_id`、`child_ids`。
- 保留 `document_id`、页码范围、章节名称和原始页面元数据。
- 章节封面可触发新的 section；低价值页面保留 page 节点但不生成 passage。
- 提供层级一致性验证和旧版 chunk JSON 兼容。

主要代码：`src/slide2study/chunking.py`。

### 3.3 BM25 与评测基线

- 中英文混合分词：英文、数字、部分公式符号、中文单字和二元词。
- 支持 section/page/passage 混合检索和层级权重。
- 指标：Recall@K、MRR、nDCG@K。
- 支持 BM25 hard-negative mining。
- CLI：`ingest`、`inspect`、`search`、`evaluate`、`mine-negatives`。

主要代码：`src/slide2study/retrieval.py`、`src/slide2study/evaluation.py`、
`src/slide2study/training.py`。

### 3.4 页面视觉理解（需求 12）

- PDF 通过 Poppler 渲染为稳定的 `page-0001.png`。
- PPTX 通过 LibreOffice 转换为 PDF 后复用渲染管线。
- JSONL 清单记录文档、页码、图片绝对路径、尺寸、SHA-256、页面角色和视觉风险。
- `MultimodalPageEncoder` 提供页面图像编码和文本问题编码接口。
- `SentenceTransformersCLIPEncoder` 提供 `clip-ViT-B-32` 基线。
- `VisualPageRetriever` 使用归一化向量和余弦相似度实现 query-to-page 检索。
- CLI：`render-pages`、`visual-search`，支持 `--only-vision`。

主要代码：`src/slide2study/vision.py`、`src/slide2study/interfaces.py`、
`src/slide2study/cli.py`。

### 3.5 评测数据校验与报告

- `validate-dataset` 检查 ID、问题、相关页/chunk、文档 ID 和五类问题标签。
- `evaluate` 输出 Recall@K、Precision@K、MRR、nDCG@K 和无结果率。
- 统计平均与 P95 检索延迟，并按问题类型拆分指标。
- `--output` 将检索器、Top-K、chunk 层级、语料/数据集路径和指标保存为 JSON。

主要代码：`src/slide2study/evaluation.py`、`src/slide2study/cli.py`。

### 3.6 稳定文档标识与多文档 pilot

- `document_id` 由完整文件内容的 SHA-256 前缀生成，文件改名不会改变 ID。
- `ingest-corpus` 可将多份 PDF/PPTX/TXT 合并为统一检索语料。
- 严格校验会核对 split、标注状态以及文档、页码、chunk 是否真实存在。
- 本地私有 pilot 选取 COMP90007、COMP90049、COMP90054、COMP90087 各一份课件。
- 当前有 28 条 `candidate` QA：train 15、dev 4、test 9；尚未计为人工测试集。
- Passage-only BM25 全部候选题 pilot：Recall@5 0.9286、MRR 0.8244、nDCG@5 0.8384。
- 仅候选 test split（9 条）：Recall@5 0.8889、MRR 0.8333、nDCG@5 0.8091；仍非正式测试结论。
- 未命中集中在 KNN 逆距离权重公式和 KNN 优缺点，两者受到跨文档/相邻页面关键词干扰。

课程语料、候选 QA 和报告位于被 Git 忽略的 `artifacts/`、`data/private/`，不会提交到公开仓库。

## 4. 验证证据

### 4.1 自动化测试

- 当前测试：25/25 通过。
- 测试覆盖：解析、质量诊断、三层 chunk、层级校验、BM25、评测指标、hard negatives、
  页面清单、PDF/PPTX 渲染流程、向量校验、视觉页面排序、评测集校验及分类型报告。

运行：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

### 4.2 S1 真实课件扫描

判定规则：直接位于课程 `slides` 文件夹中的 PDF 视为课件。

- 课程：COMP90007、COMP90049、COMP90054、COMP90087。
- 课件：67 份 PDF，共 2,814 页。
- 解析失败：0。
- 生成：5,950 个 chunk、224 个 section。
- 视觉风险页：1,549 页。
- 文本检索排除页：221 页。
- 清理重复页眉/页脚：3,026 行。
- 层级结构错误：0。

代表性 BM25 查询：

- IPv6 header：目标第 19 页，排名第 1。
- Feature learning 表格：目标第 23 页，排名第 3。
- OpenClaw / ClawHub：目标第 46 页，排名第 1。
- Moravec's Paradox：纯文本 BM25 未命中，因为标题位于视觉层；该页已进入视觉队列。

### 4.3 页面渲染验证

- `Network-Layer-3.pdf` 的 21 页全部成功渲染。
- 页面尺寸为 1440 x 1080，页码与清单映射一致。
- 人工检查子网图和 IPv6 header 图，内容清晰且没有裁切。
- 目标第 19 页的 `requires_vision=true`，视觉风险分数为 `0.55`。

## 5. 当前限制

- 当前运行环境没有安装 SentenceTransformers、Torch 和 CLIP 权重；CLIP 适配器已经实现，
  检索数学与接口由确定性假编码器测试，但尚未用真实 CLIP 权重生成课件指标。
- 当前机器没有 LibreOffice；PPTX 转换路径已由自动化测试覆盖，但只对 PDF 做过真实渲染。
- 已有四门课 28 条机器辅助候选 QA，但尚未人工复核，不能作为正式测试集或可靠消融结论。
- 尚未实现 Dense Text Retriever、Hybrid Retrieval、Reranker 训练和多模态对比学习。
- 尚未实现带引用答案、笔记、闪卡、题库和 UI。
- 视觉页数量较多；后续需要通过标注集校准视觉风险阈值，而不是只依赖启发式规则。

## 6. 安装与运行

要求 Python 3.10+。

```powershell
cd E:\Work\Slide2study
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[documents,vision,dev]"
```

系统依赖：

- PDF 页面渲染：Poppler / `pdftoppm`
- PPTX 页面渲染：LibreOffice / `soffice`
- 首次视觉检索：SentenceTransformers 会下载 `clip-ViT-B-32`

示例：

```powershell
slide2study inspect "D:\path\lecture.pdf"
slide2study ingest "D:\path\lecture.pdf" --output artifacts\lecture_chunks.jsonl
slide2study render-pages "D:\path\lecture.pdf" --output-dir artifacts\pages
slide2study visual-search artifacts\pages\lecture.jsonl "Which diagram shows IPv6 fields?" --top-k 5
```

`artifacts/` 和 `data/raw/` 已被 Git 忽略。不要把墨尔本大学课件原文件提交到公开仓库。

## 7. 推荐的下一阶段

1. 从 3-5 门课程建立人工校验的 QA 数据集，每门先做 30-50 条。
2. 区分 text、formula、table/chart、visual-only、cross-page 五类问题。
3. 安装并运行真实 CLIP baseline，保存 Recall@K、MRR、nDCG、延迟和失败案例。
4. 为页面向量增加缓存，避免每次查询重新编码图片。
5. 实现 Dense Text Retriever 和 BM25 + Dense/Visual Hybrid Retrieval。
6. 挖掘 hard negatives 并微调 Reranker。
7. 完成纯文本与视觉检索消融，然后再接带引用生成。

短期最重要的不是继续堆功能，而是先获得可信的评测集和 baseline 数字。

## 8. 更新工作目录后的接手方法

Codex 中应使用 `E:\Work\Slide2study` 创建或打开本地项目，再创建新任务。不要继续把
`C:\Users\Jevon\Documents\Slide2study` 作为工作区，也不需要保留旧路径目录联接。

新任务的第一条消息可以直接使用：

> 请接手 Slide2Study。规范工作目录是 `E:\Work\Slide2study`。先完整读取
> `PROJECT_STATUS.md`、`README.md` 和 `REQUIREMENTS.md`，再检查 Git 分支、工作区状态和
> 最近提交。不要重做已经完成的功能；从评测集和真实 CLIP baseline 开始继续。

新任务开始后先执行：

```powershell
git status --short --branch
git log -3 --oneline --decorate
python -m unittest discover -s tests -v
```

预期分支是 `agent/document-parsing`，基线提交是 `3e71ae9`。如果本文档后续被提交，
则以更新后的 HEAD 为准。
