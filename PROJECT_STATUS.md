# Slide2Study 项目进度与迁移交接

最后更新：2026-08-16（Australia/Sydney）

## 1. 项目位置与 Git 状态

- 规范工作目录：`E:\Work\Slide2study`
- 课程测试数据：`D:\important files\Unimelb\S1`
- GitHub：<https://github.com/Jevoncly/Slide2Study>
- 当前分支：`agent/document-parsing`
- 上一阶段提交：`4bd1270 Add balanced negative review workflow`
- 远程跟踪分支：`origin/agent/document-parsing`
- Draft PR：<https://github.com/Jevoncly/Slide2Study/pull/1>

远程分支已推送至 `7aaafac`；`4bd1270` 及本阶段正例映射修复尚未推送。

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
- 页面编码支持可配置批大小，避免一次加载全部课件图片。
- `VisualPageRetriever` 使用归一化向量和余弦相似度实现 query-to-page 检索。
- 页面向量缓存记录模型、文档、页码、图片 SHA-256 和归一化向量；加载时校验模型和图片内容。
- CLI：`render-pages`、`visual-search`、`visual-index`、`visual-evaluate`。

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

### 3.7 本地 QA 人工复核包

- `build-review-pack` 将候选 QA、答案提示、证据页图片和解析文本生成交互式 HTML。
- 支持按题型、split、复核状态筛选，并在浏览器本地保存进度和备注。
- 导出 JSONL 时，仅将人工选择“通过”的记录改为 `verified`。
- 四课程 pilot 审阅包包含 28 条 QA、30 个证据引用、28 张去重图片，缺图 0。
- 审阅 HTML、图片和课程数据均位于 `artifacts/`，不会进入 Git。

### 3.8 真实 CLIP 候选基线

- 已安装 SentenceTransformers、Torch 和 `clip-ViT-B-32` 权重；当前 Torch 为 CPU 版本。
- 四课程共 131 页已生成 512 维页面向量缓存，并通过模型名、页码与图片 SHA-256 校验。
- 候选 test split（9 条）CLIP：Recall@5 0.6667、MRR 0.5556、nDCG@5 0.5257。
- 同一候选 test split 的 passage-only BM25：Recall@5 0.8889、MRR 0.8333、nDCG@5 0.8091。
- 当前结果仅证明真实视觉基线与可复现实验链路可运行；候选标注未人工确认，不能作为正式模型结论。

### 3.9 BM25 + CLIP 页面融合与失败诊断

- `BM25PageRetriever` 将 passage 排名投影到可引用页面，并去除同页重复候选。
- `ReciprocalRankFusionRetriever` 支持 BM25/CLIP 权重、RRF 常数和候选深度配置。
- `hybrid-evaluate` 在一个报告中保存 BM25、CLIP、Hybrid 指标及逐题 Top 页面和首个正确页排名。
- dev split（4 条）上固定等权 RRF：Recall@5、MRR、nDCG@5 均为 1.0。
- test split（9 条）上 Hybrid：Recall@5 0.8889、MRR 0.8333、nDCG@5 0.7889。
- Hybrid 与 BM25 的 Recall/MRR 持平，但 nDCG@5 低于 BM25 的 0.8091，未达到提升验收标准。
- 逐题上，一题由第 2 名升至第 1 名，另一题由第 1 名降至第 2 名；跨页题还丢失了一个相关页。
- 所有结果仍基于 `candidate` 标注，应视为工程基线和失败分析，不是正式消融结论。

### 3.10 Dense Text Retriever 候选基线

- `SentenceTransformersTextEncoder` 支持批量编码、CPU/GPU 设备选择和非对称检索前缀。
- 默认模型为 `intfloat/multilingual-e5-small`，问题使用 `query: `，证据使用 `passage: `。
- chunk 向量缓存记录模型、前缀、chunk ID 和文本 SHA-256，语料变化时拒绝加载旧向量。
- `DenseRetriever` 使用归一化向量和余弦相似度返回 Top-K chunk；CLI 为 `dense-index`、
  `dense-evaluate`。
- 四课程 124 个 passage 已生成 384 维缓存；当前运行使用 CPU。
- dev split（4 条）：Recall@5、MRR、nDCG@5 均为 1.0。
- test split（9 条）：Recall@5 1.0、MRR 1.0、nDCG@5 0.9739，超过 BM25 候选基线。
- 机器辅助问题可能与原文措辞接近；在人工复核和困难负例扩充前，这不是正式泛化结论。

### 3.11 BM25 + Dense 文本融合

- `ReciprocalRankFusionChunkRetriever` 支持 BM25/Dense 权重、RRF 常数和候选深度配置。
- `text-hybrid-evaluate` 同时输出 BM25、Dense、Hybrid 指标及逐题 chunk 排名诊断。
- 等权 RRF 在 dev 上低于 Dense；仅使用 dev 将权重固定为 BM25 0.25、Dense 1.0。
- 固定参数在 dev（4 条）保持 Recall@5、MRR、nDCG@5 全部 1.0。
- test（9 条）Hybrid：Recall@5 0.8889、MRR 0.8889、nDCG@5 0.8628，低于 Dense。
- RRF 会提升两路共同命中的词面相似 chunk，可能挤掉 Dense 的正确首位；当前默认仍应使用
  Dense 单路，不能宣称融合改进。

### 3.12 Dense 困难负例挖掘

- `dense-mine-negatives` 复用已校验的 Dense 缓存，从指定 split 生成训练 triplet。
- 修复 page chunk 标签与 passage 挖掘语料不一致时整题被跳过的问题：现在按文档和相关页
  映射全部正例 passage，并从负例中排除。
- 四课程 train split 15 条候选问题生成 281 个 triplet、101 个去重负例，覆盖全部 15 条问题。
- 对输出执行页面回查，相关页被误标为负例的数量为 0；每条记录保留 miner 和原始排名。

### 3.13 困难负例分层与人工复核

- 按 Dense 原始排名标记 hard（1–5）、medium（6–10）和 easy（11+）。
- `dense-mine-negatives` 支持三档每题配额，避免训练集被单一难度或单一问题主导。
- 四课程 train split 使用每题 2 hard、1 medium、1 easy，得到 60 条平衡候选：hard 30、
  medium 15、easy 15，覆盖全部 15 条训练问题。
- `build-negative-review-pack` 展示 query、正例、候选负例、页码、rank、难度和 miner，支持
  有效负例、假负例、不确定三种决定、备注、本地进度和 JSONL 导出。
- 本地审阅包 60/60 条可解析、缺失 chunk 0；导出脚本已通过 JavaScript 语法检查。
- 修复同一相关页有多个 passage 时按 chunk ID 误选代表正例的问题：现在选择检索排名最高的
  相关 passage，同时继续排除该页全部 passage，防止进入负例。
- IPv4 最大 datagram 长度案例的正例已从仅含 fragment offset 的 passage 修正为包含
  `65,535 bytes including header and payload` 的 passage。
- 审阅包使用内容 SHA-256 指纹隔离浏览器本地进度，修正后的数据不会继承旧版审阅决定。

## 4. 验证证据

### 4.1 自动化测试

- 当前测试：37/37 通过；Ruff 检查通过。
- 测试覆盖：解析、质量诊断、三层 chunk、层级校验、BM25、评测指标、hard negatives、
  页面清单、PDF/PPTX 渲染流程、向量缓存及哈希校验、视觉页面排序、页面级评测、
  BM25 页面映射、页面/chunk 加权 RRF、逐题诊断、Dense 排序、chunk 缓存及文本哈希校验、
  评测集校验及分类型报告。

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

- 当前 Torch 为 CPU 版本；真实 CLIP 可以运行，但页面首次编码速度尚未获得 GPU 加速。
- 当前机器没有 LibreOffice；PPTX 转换路径已由自动化测试覆盖，但只对 PDF 做过真实渲染。
- 已有四门课 28 条机器辅助候选 QA，但尚未人工复核，不能作为正式测试集或可靠消融结论。
- BM25 + CLIP 和 BM25 + Dense RRF 均已实现，但候选 test 上没有超过各自最强单路；Dense
  候选基线虽达到很高指标，尚未经过人工测试集验证。尚未实现可靠的题型感知融合、
  Reranker 训练和多模态对比学习。
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
slide2study visual-index --manifests artifacts\pages\*.jsonl --output artifacts\page_embeddings.json
slide2study visual-evaluate artifacts\course_chunks.jsonl data\private\eval.jsonl --manifests artifacts\pages\*.jsonl --cache artifacts\page_embeddings.json --split test --top-k 5 --output artifacts\clip_report.json
slide2study hybrid-evaluate artifacts\course_chunks.jsonl data\private\eval.jsonl --manifests artifacts\pages\*.jsonl --cache artifacts\page_embeddings.json --split test --top-k 5 --output artifacts\hybrid_report.json
slide2study dense-index artifacts\course_chunks.jsonl --output artifacts\dense_embeddings.json --levels passage
slide2study dense-evaluate artifacts\course_chunks.jsonl data\private\eval.jsonl --cache artifacts\dense_embeddings.json --split test --top-k 5 --output artifacts\dense_report.json
slide2study text-hybrid-evaluate artifacts\course_chunks.jsonl data\private\eval.jsonl --cache artifacts\dense_embeddings.json --bm25-weight 0.25 --dense-weight 1 --split test --output artifacts\text_hybrid_report.json
slide2study dense-mine-negatives artifacts\course_chunks.jsonl data\private\eval.jsonl --cache artifacts\dense_embeddings.json --split train --top-k 20 --output artifacts\dense_triplets.jsonl
slide2study dense-mine-negatives artifacts\course_chunks.jsonl data\private\eval.jsonl --cache artifacts\dense_embeddings.json --split train --hard-per-query 2 --medium-per-query 1 --easy-per-query 1 --output artifacts\balanced_triplets.jsonl
slide2study build-negative-review-pack artifacts\course_chunks.jsonl artifacts\balanced_triplets.jsonl --output artifacts\negative_review\index.html
```

`artifacts/` 和 `data/raw/` 已被 Git 忽略。不要把墨尔本大学课件原文件提交到公开仓库。

## 7. 推荐的下一阶段

1. 从 3-5 门课程建立人工校验的 QA 数据集，每门先做 30-50 条。
2. 区分 text、formula、table/chart、visual-only、cross-page 五类问题。
3. 用更大的 dev 集验证题型感知门控，避免 CLIP 降低文本题和跨页题排序。
4. 使用本地审阅包人工复核 60 条平衡负例，去除语义相关但未标注的假负例。
5. 使用复核后的 triplet 微调 Reranker，比较能否在不损害 Dense 首位命中的前提下改善困难查询。
6. 在人工 test 集完成消融，然后再接带引用生成。

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

预期分支是 `agent/document-parsing`，最近已完成里程碑是 `072553f`。如果本文档后续被提交，
则以更新后的 HEAD 为准。
