# 评测集标注指南

## 目标

评测集用于比较 BM25、Dense、Hybrid 和视觉页面检索。课程原文件、页面图片和私有标注
保留在 `data/private/` 或 `artifacts/`，不得提交到公开仓库。

## 每条记录

JSONL 每行一条问题，必须包含：

- `id`：全数据集唯一标识。
- `query`：不直接复制整段课件的自然问题。
- `document_id`：由入库命令生成的 `doc-...` 内容哈希标识。
- `relevant_pages`：复核者确认能够回答问题的全部页面。
- `relevant_chunk_ids`：对应的 page 或 passage chunk。
- `question_type`：`text`、`formula`、`table_chart`、`visual_only` 或 `cross_page`。
- `split`：`train`、`dev` 或 `test`。
- `annotation_status`：机器辅助产生时为 `candidate`，逐条语义复核后才改为 `verified`。
- `reviewer_type`：复核来源，使用 `human` 或 `ai`；正式 test 必须为 `human`。

可选的 `answer_hint` 只用于复核，不参与检索评分。

## 语义复核步骤

1. 打开原始页面，确认问题无需课件外信息即可回答。
2. 检查所有相关页，补充跨页证据，删除仅关键词相似但不能回答问题的页。
3. 检查相关 chunk 包含完整证据；公式、图表和图注不能被错误拆开。
4. 确认题型；必须查看图片才能回答的问题标为 `visual_only`。
5. 检查问题没有泄漏答案，也不是整句照抄原文。
6. 记录 `reviewer_type`，再将 `annotation_status` 从 `candidate` 改为 `verified`。

可以先生成本地审阅包，将候选问题与证据图片放在同一页面：

```powershell
slide2study build-review-pack artifacts/course_chunks.jsonl data/private/eval.jsonl `
  --output artifacts/review/index.html `
  --manifests artifacts/rendered/*.jsonl
```

双击 `index.html` 后可以按题型、split 和复核状态筛选。复核选择与备注保存在浏览器本地，
“导出复核 JSONL”会保留全部记录，并仅将选择“通过”的记录改为 `verified`。

## 数据划分

- 同一近重复问题只能出现在一个 split。
- test 只保留 `reviewer_type=human` 的 `verified` 样本；AI 复核样本可用于开发诊断，但正式结论前
  应由独立人工抽查。
- 参数选择使用 dev，不根据 test 指标调参。
- 每门课程最终目标为 30–50 条，五种题型均应覆盖。

## 校验与评测

```powershell
slide2study validate-dataset data/private/eval.jsonl `
  --corpus artifacts/course_chunks.jsonl --strict

slide2study evaluate artifacts/course_chunks.jsonl data/private/eval.jsonl `
  --split test --levels passage --top-k 5 --strict-dataset `
  --output artifacts/bm25_report.json
```

结构校验通过只代表引用存在，不代表语义标注已经人工确认；只有 `verified` 且
`reviewer_type=human` 的数据才能用于正式 test 报告。
