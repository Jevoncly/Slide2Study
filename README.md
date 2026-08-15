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
slide2study inspect examples/sample_course.txt --pages-output artifacts/sample_pages.jsonl
slide2study search artifacts/sample_chunks.jsonl "正则化为什么能降低模型复杂度" --top-k 3
slide2study search artifacts/sample_chunks.jsonl "正则化" --levels page,passage
slide2study validate-dataset examples/retrieval_eval.jsonl --strict
slide2study evaluate artifacts/sample_chunks.jsonl examples/retrieval_eval.jsonl --top-k 3 --strict-dataset --output artifacts/bm25_report.json
slide2study mine-negatives artifacts/sample_chunks.jsonl examples/retrieval_eval.jsonl --output artifacts/train_triplets.jsonl
```

解析真实 PDF/PPTX 时安装文档依赖：

```bash
python -m pip install -e ".[documents]"
slide2study ingest data/raw/lecture.pdf --output artifacts/lecture_chunks.jsonl
```

页面视觉检索需要 Poppler；PPTX 还需要系统安装 LibreOffice。CLIP 编码依赖单独安装：

```bash
python -m pip install -e ".[documents,vision]"
slide2study render-pages data/raw/lecture.pdf --output-dir artifacts/pages
slide2study visual-search artifacts/pages/lecture.jsonl "IPv6 header fields" --top-k 5
```

`render-pages` 为每页生成稳定的 PNG、尺寸、原始文档路径、页码、SHA-256、页面角色和
视觉风险标签。`visual-search --only-vision` 可以只搜索解析阶段筛出的视觉风险页。首次使用
CLIP 时，SentenceTransformers 会下载指定模型；默认模型是 `clip-ViT-B-32`。

每条检索结果都包含 `document_id`、`page_start`、`page_end`、`section` 和稳定的 `chunk_id`，可直接作为引用生成的 evidence。

`inspect` 报告还会输出 `page_roles`、`requires_vision_pages`、
`text_retrieval_excluded_pages` 和 `removed_boilerplate_lines`。视觉页不会被删除：原始文本保存在
页面元数据中，供后续页面图像检索和引用回溯使用。

## 评测集格式

每行一个查询，可标注相关页或相关 chunk。正式评测集还应提供 `document_id` 和
`question_type`；支持的题型为 `text`、`formula`、`table_chart`、`visual_only` 和
`cross_page`：

```json
{"id":"q1","query":"验证集的作用是什么？","document_id":"lecture-01","relevant_pages":[3],"relevant_chunk_ids":[],"question_type":"text"}
```

`validate-dataset --strict` 会在实验前检查重复 ID、空问题、非法页码、缺失标注和题型。
`evaluate --output` 会保存实验配置、数据集概况、Recall@K、Precision@K、MRR、nDCG@K、
无结果率、平均/P95 延迟，以及按题型拆分的指标。

## 代码结构

```text
src/slide2study/
  parsing.py       # PDF/PPTX/TXT 页面解析与质量诊断
  chunking.py      # 跨页章节识别与 section/page/passage 三级切块
  retrieval.py     # BM25 baseline 与 Dense 接口
  evaluation.py    # 数据校验、检索指标、分类型与延迟报告
  interfaces.py    # Reranker / 多模态编码 / 引用生成接口
  vision.py        # PDF/PPTX 页面渲染、CLIP 编码和视觉页面检索
  training.py      # BM25/Dense hard-negative mining
  cli.py           # inspect / ingest / search / evaluate / mine-negatives
```

## 算法迭代路线

1. 固化真实课程评测集与 BM25 数字
2. 训练 text bi-encoder，并做 BM25 + Dense hybrid
3. 从 BM25/Dense 结果挖 hard negatives，微调 cross-encoder reranker
4. 渲染页面图像，训练 query-page 对比学习模型
5. 加入引用准确率、faithfulness、幻觉率和端到端延迟评测

测试：

```bash
python -m unittest discover -s tests -v
```
