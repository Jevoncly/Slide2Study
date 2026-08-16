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

- PDF 优先通过 Poppler 渲染；Poppler 不可用时自动回退到 PyMuPDF，均生成稳定的
  `page-0001.png`。
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

### 3.14 复核结果清洗与训练集固化

- 60 条平衡候选已全部复核：有效负例 50、假负例 10、不确定 0，15 个训练问题均至少保留
  一条负例。
- 假负例主要集中在 hard 档：hard 8/30、medium 1/15、easy 1/15，说明高排名候选更容易
  包含能够部分回答问题的语义相关证据。
- 清洗后训练集为 50 条：hard 22、medium 14、easy 14；假负例不会进入 Reranker 训练。
- 新增 `apply-negative-reviews`：默认要求所有条目已完成复核，仅保留 `valid_negative`，并
  输出规范的 query-positive-negative triplet；遇到 pending/uncertain 会拒绝生成。
- 本地清洗结果位于 `artifacts/pilot_negative_review/reviewed-train-triplets.jsonl`，课程文本
  与私有标注继续由 Git 忽略。

### 3.15 Cross-encoder Reranker 训练链路

- 新增 `train-reranker`，将已清洗 triplet 展开为去重的 query-text 二分类样本，支持模型、
  device、batch size、epoch、学习率与随机种子配置，并保存可重新加载的 checkpoint。
- 50 条已复核 triplet 生成 65 个去重训练 pair：正例 15、负例 50，覆盖全部 15 个训练问题。
- 使用本机缓存的 `intfloat/multilingual-e5-small` 初始化 cross-encoder 分类头，在 CPU 上完成
  1 epoch、9 step 的可复现训练，checkpoint 位于 `artifacts/pilot_reranker_e5`。
- checkpoint 已成功重新加载。训练集 pairwise 烟雾测试为 29/50（58%），正负均值仅有轻微
  分离；这说明训练链路可运行，但当前模型仍明显不足，不能作为泛化或模型改进结论。
- 下一步必须在独立 dev 候选集上比较 Dense 与 Dense+Reranker，并据此加入 early stopping、
  checkpoint 恢复和训练曲线；不得根据 test 调整训练参数。
- 新增 `reranker-evaluate`，从 Dense Top-N 候选中用 cross-encoder 重排，并复用统一的检索
  指标与分题型报告。
- 当前 1-epoch 模型在候选 dev（4 条）上明显失败：Recall@5 0.25、MRR 0.0833、nDCG@5
  0.125；同一 dev 的 Dense 基线三项均为 1.0。该模型不得用于 test 或设为默认检索器。
- 失败原因与训练诊断一致：仅 65 个 pair、随机初始化分类头且只有 9 个更新 step。后续应优先
  扩充并人工确认 dev/训练数据，或引入已有检索预训练的 cross-encoder，再实施 early stopping；
  不能围绕 4 条 candidate dev 反复调参。

### 3.16 公开课件—复习资料对应组

- `data/public_course_pairs.json` 记录 3 个公开来源、4 个主题对应组、原始 URL、角色和许可边界。
- MIT 6.006 动态规划：3 份讲义对应 recitation、problem session、problem set 及答案。
- Berkeley CS188：Search 与 MDP 讲义分别对应 discussion、exam prep 及答案；因未找到明确的
  逐文件再分发许可，原文件仅限本地研究。
- OpenDSA Sorting Part 1：同一 RST 模块同时进入演示幻灯片和带注释讲义配置，并对应 3 个
  排序练习与可视化源文件；仓库使用 MIT License。
- 下载脚本校验 PDF 文件头，并记录 URL、内容类型、字节数和 SHA-256。当前下载 22/22 成功，
  共 18,658,921 字节（17.79 MiB），缺失 0、大小不一致 0。
- 现有 `ingest-corpus` 已实测导入全部 22 份 PDF：328 页、935 个 chunk、失败 0。
- 原始文件、OpenDSA 稀疏源码和解析产物位于被 Git 忽略的 `data/raw/`、`artifacts/`；公开
  仓库只保留清单、下载脚本和许可说明。
- 已建立 66 条公开检索记录：原 54 条及新增 12 条 test 均已完成人工确认；所有记录的
  `reviewer_type` 均为 `human`。
- train/dev/test 为 18/30/18，text/formula/cross-page/table-chart/visual-only 为 25/14/12/6/9；
  66/66 条均为 `verified`，严格数据校验通过。正式文件为
  `data/public_course_eval_reviewed.jsonl`。
- 评测语料已收紧为 7 份纯课件、256 页、566 个层级 chunk（253 个 passage）；复习资料只用作
  问题来源，不参与检索，避免 discussion 或答案文件泄漏。
- 扩充 dev（30 条）：BM25 Recall@5/MRR/nDCG@5 为 0.867/0.596/0.647，Dense 为
  0.967/0.806/0.836，BM25+Dense 固定权重 RRF 为 0.933/0.756/0.796；Dense 单路继续领先。
- table/chart 两条在 BM25 下 Recall@5 为 0，在 Dense 下均命中；扩充集已能暴露原 6 条 dev
  看不到的题型差异。
- 新增 `type-aware-evaluate`，把 BM25/Dense chunk 排名映射到页面，与 CLIP 和 Dense+CLIP
  RRF 做统一页面级比较，并保存题型路由与逐题选择结果。
- 仅用扩充 dev 固定路由：text→BM25，formula/cross-page→Dense，table/chart→CLIP，
  visual-only→Dense+CLIP RRF。页面 Dense 为 0.967/0.811/0.829，门控后为
  1.000/0.833/0.855；平均延迟从 39.8 ms 降到 31.8 ms。未运行 test，避免数据泄漏。
- 人工复核 test：BM25 为 1.000/0.514/0.597，Dense 为 1.000/0.917/0.925，RRF 为
  1.000/0.833/0.887。正式报告明确引用 reviewed 数据；样本仅 6 条，仍不得根据 test 调权重。
- 两个本机 Poppler 入口仍不可用；新增并实测 PyMuPDF 回退路径，7/7 份课件共 256 页均成功
  渲染，页面清单的 SHA-256 校验有效。
- 审阅包现包含 54 条记录、67 个证据页引用和 64 张去重图片，缺失 0；新增 visual-only 与
  table/chart 证据已逐页检查，未发现裁切、模糊或页面错配。
- AI 语义复核日志现覆盖 54 条；原 30 条中 23 条无需修改、7 条修正后通过，新增 24 条均在
  构建时通过。完整理由保存在 `data/public_course_eval_ai_review.jsonl`，生成脚本可同时重建
  candidate 与 reviewed 数据，避免后续回退。
- 人工备注使用 `review_notes` 字段；内容对应 `public-search-003` 和 `public-search-005`，导出时
  误落在同编号的 DP 记录。现已恢复两条 DP 记录，并将决定和备注迁移到正确的 Search 记录；
  两条 Search train 已按备注修正并完成人工确认。

### 3.17 Reranker 验证与模型选择链路

- `train-reranker` 可接收独立 dev 数据集和 Dense 向量缓存，训练前冻结 Dense Top-N 候选。
- 每个 epoch 直接计算候选重排后的 Recall@K、MRR 和 nDCG@K，以 dev MRR 选择最佳 checkpoint。
- 支持 patience 和 min-delta 早停；最佳 epoch、最佳 MRR、是否早停及逐 epoch 曲线均保存到
  `slide2study_training.json`。
- 未提供 dev 时仍保留原有单次训练模式；提供 dev 时必须同时提供 Dense 缓存，避免静默使用
  不可复现的候选集。
- 本阶段只完成并验证训练基础设施，尚未用未经人工筛查的公开课件负例训练或查看 test。
- 已从公开课件 train 的 18 个问题生成 72 条待复核候选：hard 36、medium 18、easy 18；
  本地审阅包为 `artifacts/public_courseware_reranker_review/index.html`，72/72 条可解析。
- 本轮人工约定“未复核代表通过”：导出含 pending 62、false negative 5、uncertain 5；通过
  显式 `--pending-as-valid --allow-incomplete` 固化 62 条训练 triplet，覆盖全部 18 个问题。
- 使用 62 条 triplet 得到 79 个去重 pair（正例 18、负例 61），CPU 训练在连续两轮 dev MRR
  无提升后早停；最佳内部 epoch 为 4，统一 dev 评测 Recall@5 0.500、MRR 0.220、nDCG@5
  0.241，平均延迟 858.4 ms。
- 同一 dev 的 Dense chunk 基线为 Recall@5 0.967、MRR 0.806、nDCG@5 0.836，平均延迟
  81.2 ms；当前 Reranker 大幅退化且约慢 10.6 倍，因此不得设为默认或运行 test。最佳 checkpoint 与报告仅保存在
  `artifacts/public_courseware_reranker_e5` 和对应本地报告中。

### 3.18 检索预训练 Reranker 基线

- `reranker-evaluate --reranker` 现在同时接受本地 checkpoint 和 Hugging Face 模型标识，并
  支持 `--reranker-local-files-only` 离线复现缓存模型。
- 使用多语言检索预训练的 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`，避免从 E5 随机
  分类头开始；模型约 1 亿参数，首次下载后可完全离线运行。
- 仅在 dev 比较 candidate-k 20、10、5；k=5 最优：Recall@5 0.967、MRR 0.908、nDCG@5
  0.893、平均延迟 189.5 ms。k=20 为 0.967/0.892/0.885、775.0 ms，k=10 为
  0.967/0.892/0.889、344.4 ms。
- 同口径 Dense 为 Recall@5 0.967、MRR 0.806、nDCG@5 0.836、81.2 ms；Reranker 保持召回，
  MRR 提高 0.103、nDCG@5 提高 0.057，代价是约 2.3 倍延迟。当前 dev 配置固定为 k=5。
- 仍未运行 test；必须先完成新增 AI-dev 的独立人工抽查，再对冻结配置做一次测试集评估。

### 3.19 AI-dev 独立人工抽查包

- `build-review-pack` 新增 split、reviewer type 筛选，可只构建待独立抽查的数据子集。
- `--reset-review-state` 会将原有机器复核状态重置为未复核，避免页面打开时错误显示已完成；
  `--verified-reviewer-type human` 会在人工选择通过并导出后更新复核来源。
- 本地专项包 `artifacts/ai_dev_human_review/index.html` 包含 24 条 AI-dev、32 个证据页和
  32 张页面图片，缺图 0；train/test 记录均为 0，初始状态为 0/24。
- 专项包及导出结果均位于 Git 忽略的 `artifacts/`，不会公开课件内容或未冻结标注。
- 用户已确认专项包 24/24 条均正确；正式评测集现为 train 18、dev 30、test 6，全部
  `annotation_status=verified` 且 `reviewer_type=human`。生成脚本的人工确认集合已同步更新，
  重新构建不会把这 24 条退回 AI 状态。

### 3.20 冻结 Reranker 测试结果

- 人工确认后的 dev 复跑与冻结前一致：Recall@5 0.967、MRR 0.908、nDCG@5 0.893。
- 冻结配置 `mmarco-mMiniLMv2-L12-H384-v1`、candidate-k=5 在 6 条人工 test 上只运行一次；
  Reranker 为 Recall@5 1.000、MRR 0.833、nDCG@5 0.880、平均延迟 239.1 ms。
- 同一 test 的 Dense 为 Recall@5 1.000、MRR 0.917、nDCG@5 0.925、平均延迟 39.2 ms；
  Reranker 未在 test 稳定超过 Dense，不能设为默认检索器。
- 退化集中在唯一 cross-page 测试题 `public-mdp-009`：首个相关结果由第 1 名降至第 2 名；
  formula、text、visual-only 的 test MRR 未改变。由于 test 仅 6 条，不据此调整任何参数。

### 3.21 人工 test 扩充

- 新增可复现脚本 `scripts/build_public_test_expansion.py`，只从现有 54 条未使用的课件证据页
  构建候选，并检查 ID、页面存在性、单文档范围及证据页不重叠。
- 扩充候选共 12 条：cross-page 4、table/chart 4、visual-only 4；用户已确认 12/12 条正确，
  现已作为 `human + verified` 合并进入正式 test。
- 已逐页检查 17 个证据页图像；本地审阅包
  `artifacts/test_expansion_human_review/index.html` 包含 12 条、17 张图片，缺图 0，初始状态
  为 0/12。
- 候选文件 `data/public_course_test_expansion_candidates.jsonl` 保留为审阅前审计记录；正式来源
  是 `data/public_course_eval_reviewed.jsonl`。统一生成脚本可精确重建 66 条记录且不会丢失
  人工状态。

### 3.22 扩充后冻结测试结果

- 按事先冻结的配置只运行一次 18 条 test：Dense Recall@5/MRR/nDCG@5 为
  0.833/0.704/0.720，平均延迟 56.8 ms；mMARCO Reranker（candidate-k=5）为
  0.833/0.704/0.719，平均延迟 241.1 ms。
- Reranker 没有改善 Recall@5 或 MRR，nDCG@5 略降 0.001，平均延迟约为 Dense 的 4.2 倍；
  扩大样本后仍不支持将其设为默认检索器。
- Dense 未召回的 3 条为 `public-mdp-019`（table/chart）、`public-mdp-020`（visual-only）和
  `public-mdp-022`（table/chart）。由于 Reranker 只能重排 Dense Top-5，它无法恢复未进入
  候选集的证据；当前主要瓶颈是图表/视觉页的候选召回，而不是候选排序。
- 以上 test 结果只用于最终报告，不据此调整模型、路由或 candidate-k。后续改进必须在
  train/dev 建立并冻结后，才能再用新的独立 test 验证。

### 3.23 视觉 dev 扩充候选

- 新增可复现脚本 `scripts/build_public_visual_dev_expansion.py`，从正式 66 条数据未使用的页面
  构建 12 条视觉重型 dev 候选：table/chart 6 条、visual-only 6 条。
- 12 条覆盖 Search 与 MDP 各 6 条，共引用 14 个互不属于现有标注的证据页；已逐页检查问题、
  答案提示和渲染图，严格数据校验通过。
- 候选文件为 `data/public_course_visual_dev_candidates.jsonl`，当前仍为 `candidate`，没有合并
  进入正式数据，也没有用于选择模型或路由。
- 本地人工审阅包为 `artifacts/visual_dev_human_review/index.html`：12 条、14 张证据图、缺图 0，
  初始状态 0/12。只有完成独立确认后，才扩大 dev 并重跑 Dense、CLIP、Dense+CLIP 与题型路由。

## 4. 验证证据

### 4.1 自动化测试

- 当前测试：48/48 通过；Ruff 检查通过。
- 测试覆盖：解析、质量诊断、三层 chunk、层级校验、BM25、评测指标、hard negatives、
  页面清单、PDF/PPTX 渲染流程、向量缓存及哈希校验、视觉页面排序、页面级评测、
  通用 chunk→page 映射、页面/chunk 加权 RRF、题型路由、逐题诊断、Dense 排序、chunk 缓存
  及文本哈希校验、评测集校验及分类型报告。

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
- BM25 + CLIP、BM25 + Dense RRF 和 dev 校准的题型门控均已实现；全局固定权重 RRF 未超过
  Dense，题型门控在扩充 dev 上超过 Dense。新增 24 条 dev 为 AI 复核，正式对外结论前仍应
  做独立人工抽查；人工 test 仍只有 6 条。检索预训练 Reranker 已在 dev 显著提升排序质量，
  但尚未经过冻结 test 验证；多模态对比学习仍未实现。
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

- PDF 页面渲染：优先 Poppler / `pdftoppm`，不可用时回退到随 `documents` extra 安装的 PyMuPDF
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
slide2study type-aware-evaluate artifacts\course_chunks.jsonl data\private\eval.jsonl --manifests artifacts\pages\*.jsonl --dense-cache artifacts\dense_embeddings.json --visual-cache artifacts\page_embeddings.json --route text=bm25_page --route table_chart=clip_page --route visual_only=dense_clip_rrf --split dev --output artifacts\type_aware_dev.json
slide2study dense-mine-negatives artifacts\course_chunks.jsonl data\private\eval.jsonl --cache artifacts\dense_embeddings.json --split train --top-k 20 --output artifacts\dense_triplets.jsonl
slide2study dense-mine-negatives artifacts\course_chunks.jsonl data\private\eval.jsonl --cache artifacts\dense_embeddings.json --split train --hard-per-query 2 --medium-per-query 1 --easy-per-query 1 --output artifacts\balanced_triplets.jsonl
slide2study build-negative-review-pack artifacts\course_chunks.jsonl artifacts\balanced_triplets.jsonl --output artifacts\negative_review\index.html
```

`artifacts/` 和 `data/raw/` 已被 Git 忽略。不要把墨尔本大学课件原文件提交到公开仓库。

## 7. 推荐的下一阶段

1. 保持 Dense 为默认检索器，将 Reranker 记录为“dev 提升、扩充 test 未复现”的失败消融；
   不得围绕当前 test 调模型或 candidate-k。
2. 完成 12 条视觉 dev 候选的独立确认；合并后比较已有 CLIP、Dense+CLIP 和题型路由，并在
   扩充 dev 上冻结方案。
3. 为下一轮改进另建未查看的独立 test；验证通过后再接带引用生成。

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
