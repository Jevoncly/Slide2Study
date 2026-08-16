# Slide2Study

Slide2Study 是一个面向课程 Slides/PDF 的多模态、结构感知 RAG 项目。它把文字、公式、图表和章节结构组织成可追溯的证据单元，最终用于生成带页码引用的复习笔记、闪卡和分层题库。

当前版本先建立可复现的经典检索基线：

- PDF、PPTX、Markdown、纯文本的页级解析
- PPTX 阅读顺序、表格、演讲者备注与页面布局元数据
- PDF 页面尺寸、旋转、图片数量、视觉风险与低价值页面诊断
- 跨页重复页眉/页脚清理，保留原始文本用于证据追溯
- 版权页、视觉空白页和章节封面标注；文本检索默认跳过低价值内容
- PDF/PPTX 页面渲染、稳定页码映射与 SHA-256 图像校验
- SentenceTransformers CLIP query-to-page 视觉检索基线
- 章节级、页面级、局部内容级三级切块，保留跨页章节和父子关系
- 无额外分词依赖的中英文混合 BM25
- Recall@K、MRR、nDCG@K 评测
- 为 Dense Retrieval、视觉页面编码、Reranker 和带引用生成预留统一接口

## 快速开始

Python 3.10+：

```bash
python -m pip install -e .
slide2study ingest examples/sample_course.txt --output artifacts/sample_chunks.jsonl --max-chars 200
slide2study ingest-corpus lecture1.pdf lecture2.pdf --output artifacts/course_chunks.jsonl
slide2study inspect examples/sample_course.txt --pages-output artifacts/sample_pages.jsonl
slide2study search artifacts/sample_chunks.jsonl "正则化为什么能降低模型复杂度" --top-k 3
slide2study search artifacts/sample_chunks.jsonl "正则化" --levels page,passage
slide2study validate-dataset examples/retrieval_eval.jsonl --strict
slide2study evaluate artifacts/sample_chunks.jsonl examples/retrieval_eval.jsonl --split test --top-k 3 --strict-dataset --output artifacts/bm25_report.json
slide2study build-review-pack artifacts/course_chunks.jsonl data/private/eval.jsonl --output artifacts/review/index.html --manifests artifacts/pages/*.jsonl
slide2study mine-negatives artifacts/sample_chunks.jsonl examples/retrieval_eval.jsonl --output artifacts/train_triplets.jsonl
```

解析真实 PDF/PPTX 时安装文档依赖：

```bash
python -m pip install -e ".[documents]"
slide2study ingest data/raw/lecture.pdf --output artifacts/lecture_chunks.jsonl
```

PDF 页面渲染优先使用 Poppler，并在 Poppler 不可用时自动回退到 PyMuPDF；PPTX 仍需要系统
安装 LibreOffice。CLIP 编码依赖单独安装：

```bash
python -m pip install -e ".[documents,vision]"
slide2study render-pages data/raw/lecture.pdf --output-dir artifacts/pages
slide2study visual-search artifacts/pages/lecture.jsonl "IPv6 header fields" --top-k 5
slide2study visual-index --manifests artifacts/pages/*.jsonl --output artifacts/page_embeddings.json
slide2study visual-evaluate artifacts/course_chunks.jsonl data/private/eval.jsonl --manifests artifacts/pages/*.jsonl --cache artifacts/page_embeddings.json --split test --top-k 5 --output artifacts/clip_report.json
slide2study hybrid-evaluate artifacts/course_chunks.jsonl data/private/eval.jsonl --manifests artifacts/pages/*.jsonl --cache artifacts/page_embeddings.json --split test --top-k 5 --output artifacts/hybrid_report.json
slide2study dense-index artifacts/course_chunks.jsonl --output artifacts/dense_embeddings.json --levels passage
slide2study dense-evaluate artifacts/course_chunks.jsonl data/private/eval.jsonl --cache artifacts/dense_embeddings.json --split test --top-k 5 --output artifacts/dense_report.json
slide2study text-hybrid-evaluate artifacts/course_chunks.jsonl data/private/eval.jsonl --cache artifacts/dense_embeddings.json --bm25-weight 0.25 --dense-weight 1 --split test --output artifacts/text_hybrid_report.json
slide2study dense-mine-negatives artifacts/course_chunks.jsonl data/private/eval.jsonl --cache artifacts/dense_embeddings.json --split train --top-k 20 --output artifacts/dense_triplets.jsonl
slide2study dense-mine-negatives artifacts/course_chunks.jsonl data/private/eval.jsonl --cache artifacts/dense_embeddings.json --split train --hard-per-query 2 --medium-per-query 1 --easy-per-query 1 --output artifacts/balanced_triplets.jsonl
slide2study build-negative-review-pack artifacts/course_chunks.jsonl artifacts/balanced_triplets.jsonl --output artifacts/negative_review/index.html
slide2study apply-negative-reviews artifacts/negative_review/reviewed-negative-triplets.jsonl --output artifacts/reviewed_train_triplets.jsonl
slide2study train-reranker artifacts/course_chunks.jsonl artifacts/reviewed_train_triplets.jsonl --output-dir artifacts/reranker --epochs 1
slide2study reranker-evaluate artifacts/course_chunks.jsonl data/private/eval.jsonl --cache artifacts/dense_embeddings.json --reranker artifacts/reranker --split dev --output artifacts/reranker_dev_report.json
```

`render-pages` 为每页生成稳定的 PNG、尺寸、原始文档路径、页码、SHA-256、页面角色和
视觉风险标签。`visual-search --only-vision` 可以只搜索解析阶段筛出的视觉风险页。首次使用
CLIP 时，SentenceTransformers 会下载指定模型；默认模型是 `clip-ViT-B-32`。
`visual-index` 会分批编码页面，并把模型名、页码、图片 SHA-256 和归一化向量保存为缓存。
`visual-evaluate` 会在加载时校验模型与图片哈希，复用页面向量，只编码查询，并输出与 BM25
一致的 Recall@K、Precision@K、MRR、nDCG@K、无结果率、延迟和分题型指标。
`hybrid-evaluate` 将 passage BM25 结果映射到页面，以加权 Reciprocal Rank Fusion 融合
BM25 与 CLIP；同一报告包含三路指标及逐题 Top 页面、命中状态和首个正确页排名。融合权重
应在 dev split 固定后再运行 test split，避免用测试集调参。

`dense-index` 默认使用 `intfloat/multilingual-e5-small`，按模型要求为问题和证据分别添加
`query: ` 与 `passage: ` 前缀，批量生成归一化文本向量。缓存记录模型、前缀、chunk ID、
文本 SHA-256 和向量；`dense-evaluate` 校验缓存后复用同一评测框架。
`text-hybrid-evaluate` 对 BM25、Dense 和加权 RRF 使用同一批 chunk，保存三路指标和逐题
Top chunk 诊断。融合参数必须只在 dev 上选择；如果 test 未超过 Dense，应继续使用 Dense
单路作为默认检索器。
`dense-mine-negatives` 从缓存 Dense 排名中生成 query-positive-negative triplet，并将页级
正例映射到同文档 passage，防止层级过滤后把相关 passage 误标为负例。
同一相关页存在多个 passage 时，以检索排名最高的相关 passage 作为代表正例，其他同页
passage 仍全部排除出负例。
负例按原始排名划分为 hard（1–5）、medium（6–10）和 easy（11+），可设置每题配额。
`build-negative-review-pack` 生成仅在本机使用的交互式 HTML，支持标记有效负例、假负例或
不确定，并导出带人工决定和备注的 JSONL。
审阅数据带内容指纹；重新生成内容后会使用新的浏览器本地进度空间，避免旧决定错配。
`apply-negative-reviews` 默认要求全部条目已明确复核，只保留 `valid_negative`，并去除审阅
页面预览字段，输出可直接供训练使用的规范 triplet；存在 `pending` 或 `uncertain` 时会拒绝
生成，除非显式使用 `--allow-incomplete`。
`train-reranker` 将规范 triplet 展开为 query-positive 和 query-negative 二分类样本，正例对会
自动去重；默认从 multilingual-e5-small 初始化交叉编码器分类头，固定随机种子，并将模型
checkpoint 与训练配置写入输出目录。该命令建立训练链路，正式模型选择仍需独立 dev 集。
`reranker-evaluate` 从缓存 Dense 检索获取较宽的候选集，再用 cross-encoder 重排，并使用同一
套 Recall、MRR、nDCG 和延迟指标评估；模型选择只应使用 dev split。

每条检索结果都包含基于文件内容 SHA-256 生成的稳定 `document_id`、`page_start`、
`page_end`、`section` 和稳定的 `chunk_id`，可直接作为引用生成的 evidence。原始文件名保存在
chunk metadata 中；同一内容改名后 `document_id` 不变。

`inspect` 报告还会输出 `page_roles`、`requires_vision_pages`、
`text_retrieval_excluded_pages` 和 `removed_boilerplate_lines`。视觉页不会被删除：原始文本保存在
页面元数据中，供后续页面图像检索和引用回溯使用。

## 公开课件—复习资料对应组

`data/public_course_pairs.json` 记录可复现的公开来源、主题对应关系、原始 URL 和许可边界。
首批包含 3 个来源、4 个主题对应组：MIT 6.006 的动态规划，Berkeley CS188 的 Search 与
MDP，以及 OpenDSA 的 Sorting Part 1。下载 PDF：

```powershell
python scripts/download_public_course_pairs.py data/public_course_pairs.json
$files = Get-ChildItem data/raw/public_course_pairs -Recurse -Filter *.pdf | Select-Object -ExpandProperty FullName
slide2study ingest-corpus $files --output artifacts/public_course_pairs_chunks.jsonl
```

原始下载位于被 Git 忽略的 `data/raw/public_course_pairs/`；下载报告记录每个文件的 URL、
SHA-256、大小、角色与许可。MIT OCW 内容遵循 CC BY-NC-SA 4.0，使用时必须署名、限非商业
并以相同许可共享。Berkeley 文件虽可公开访问，但没有找到逐文件再分发授权，因此只用于
本地研究，不提交原文件。OpenDSA 源码使用 MIT License；其同一模块可编译为演示幻灯片和
带注释讲义，并与练习源文件精确对应。公开来源只是候选语料，不能替代人工 QA 标注。

首批公开检索候选集由复习资料提供问题方向，但正例只允许指向 7 份对应课件，避免把答案或
discussion 文件混入检索语料造成泄漏：

```powershell
python scripts/build_public_eval_candidates.py artifacts/public_courseware_chunks.jsonl `
  --output data/public_course_eval_candidates.jsonl
slide2study validate-dataset data/public_course_eval_candidates.jsonl `
  --corpus artifacts/public_courseware_chunks.jsonl --strict
slide2study build-review-pack artifacts/public_courseware_chunks.jsonl `
  data/public_course_eval_candidates.jsonl --output artifacts/public_course_review/index.html
```

当前 30 条记录全部为 `candidate`：train/dev/test 为 18/6/6，AI 语义复核后题型包含 17 条
text、9 条 formula、3 条 cross-page 和 1 条 visual-only。PDF 回退渲染已覆盖 7 份课件的
256 页；审阅包中的 33 个证据页
图片全部存在，且已逐页检查清晰度、裁切和页面对应关系。视觉材料已具备人工标注条件，但
只有人工确认问题、答案提示与证据页的语义对应后，才能将记录改为 `verified` 并作为正式
测试集使用。AI 复核记录保存在 `data/public_course_eval_ai_review.jsonl`：23 条无需修改，7 条
已修正证据页或题型，0 条拒绝。

## 评测集格式

每行一个查询，可标注相关页或相关 chunk。正式评测集还应提供 `document_id`、`split`、
`question_type` 和 `annotation_status`；支持的题型为 `text`、`formula`、`table_chart`、
`visual_only` 和 `cross_page`：

```json
{"id":"q1","query":"验证集的作用是什么？","document_id":"doc-56bfc8ff5fcfd37a","relevant_pages":[3],"relevant_chunk_ids":[],"question_type":"text","split":"test","annotation_status":"verified"}
```

`annotation_status` 使用 `candidate` 或 `verified`，防止将机器辅助候选误当作人工测试集。
`validate-dataset --corpus ... --strict` 会在实验前检查重复 ID、空问题、split、题型，以及
文档、页码和 chunk 是否真实存在于语料中。完整人工标注流程见
[评测集标注指南](docs/evaluation_dataset.md)。
`evaluate --split test --output` 会只评测 test split，并保存实验配置、数据集概况、
Recall@K、Precision@K、MRR、nDCG@K、
无结果率、平均/P95 延迟，以及按题型拆分的指标。

`build-review-pack` 会生成仅在本机使用的交互式 HTML：逐条展示问题、答案提示、证据页
图片和解析文本，保存浏览器内复核进度，并导出带 `review_decision` 的 JSONL。课程图片和
审阅包应继续放在被 Git 忽略的 `artifacts/` 中。

## 代码结构

```text
src/slide2study/
  parsing.py       # PDF/PPTX/TXT 页面解析与质量诊断
  chunking.py      # 跨页章节识别与 section/page/passage 三级切块
  retrieval.py     # BM25 baseline 与 Dense 接口
  dense.py         # 多语言文本编码与可校验 chunk 向量缓存
  evaluation.py    # 数据校验、检索指标、分类型与延迟报告
  review.py        # 私有 QA 人工复核 HTML 与导出
  negative_review.py # 困难负例人工复核 HTML 与导出
  interfaces.py    # Reranker / 多模态编码 / 引用生成接口
  vision.py        # PDF/PPTX 页面渲染、CLIP 编码和视觉页面检索
  fusion.py        # BM25 页面映射、加权 RRF 与多模态融合
  training.py      # BM25/Dense hard-negative mining
  cli.py           # inspect / ingest / search / evaluate / mine-negatives
```

## 算法迭代路线

1. 人工复核并扩充真实课程评测集
2. 训练 text bi-encoder，并做 BM25 + Dense/Visual hybrid
3. 从 BM25/Dense 结果挖 hard negatives，微调 cross-encoder reranker
4. 渲染页面图像，训练 query-page 对比学习模型
5. 加入引用准确率、faithfulness、幻觉率和端到端延迟评测

测试：

```bash
python -m unittest discover -s tests -v
```
