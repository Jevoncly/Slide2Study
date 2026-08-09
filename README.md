# Slide2Study

Slide2Study 是一个面向课程 Slides/PDF 的多模态、结构感知 RAG 项目。它把文字、公式、图表和章节结构组织成可追溯的证据单元，最终用于生成带页码引用的复习笔记、闪卡和分层题库。

当前版本先建立可复现的经典检索基线：

- PDF、PPTX、Markdown、纯文本的页级解析
- PPTX 阅读顺序、表格、演讲者备注与页面布局元数据
- PDF 页面尺寸、旋转、图片数量与低文本页面诊断
- 保留章节、页码与父子关系的分层切块
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
slide2study evaluate artifacts/sample_chunks.jsonl examples/retrieval_eval.jsonl --top-k 3
slide2study mine-negatives artifacts/sample_chunks.jsonl examples/retrieval_eval.jsonl --output artifacts/train_triplets.jsonl
```

解析真实 PDF/PPTX 时安装文档依赖：

```bash
python -m pip install -e ".[documents]"
slide2study ingest data/raw/lecture.pdf --output artifacts/lecture_chunks.jsonl
```

每条检索结果都包含 `document_id`、`page_start`、`page_end`、`section` 和稳定的 `chunk_id`，可直接作为引用生成的 evidence。

## 评测集格式

每行一个查询，可标注相关页或相关 chunk：

```json
{"id":"q1","query":"验证集的作用是什么？","relevant_pages":[3],"relevant_chunk_ids":[]}
```

## 代码结构

```text
src/slide2study/
  parsing.py       # PDF/PPTX/TXT 页面解析与质量诊断
  chunking.py      # 结构感知、页码对齐切块
  retrieval.py     # BM25 baseline 与 Dense 接口
  evaluation.py    # Recall@K / MRR / nDCG@K
  interfaces.py    # Reranker / 多模态编码 / 引用生成接口
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
