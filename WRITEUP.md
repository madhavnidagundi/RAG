# Write-up: RAG over Indian digital payments & lending regulation

**Setup.** 15 public RBI and MeitY documents (~240 page-equivalents, 7 superseded) plus one planted injection note; details in `corpus/metadata.csv`. Retrieval: `bge-base` + FAISS, BM25, RRF fusion, optional MiniLM reranker. Generator: `gpt-oss-20b` (one row with 120b) over the top 5 chunks. Judge: `qwen3.8-27b`; I hand-checked 72 verdicts and agreed with 75% (overrides in `eval/judge_audit.json`, raw judge scores in brackets). These numbers are from the first answer prompt; a revised prompt (v2) is in the code and its answers are regenerated, but judging them is incomplete (see README, "Status of the results").

| Chunks | Retrieval | Model | hit@5 | MRR | Correct (raw judge) | False refusals | Adversarial | Latency | Cost/q |
|---|---|---|---|---|---|---|---|---|---|
| fixed | dense | 20b | 0.914 | 0.692 | 94.3% (94.3) | 1/35 | 4/5 | 1.5 s | $0.00024 |
| fixed | hybrid | 20b | 0.971 | 0.805 | 97.1% (88.6) | 1/35 | 5/5 | 1.4 s | $0.00023 |
| section | dense | 20b | 0.886 | 0.796 | 88.6% (82.9) | 3/35 | 4/5 | 1.1 s | $0.00019 |
| **section** | **hybrid** | **20b** | 0.971 | 0.860 | 94.3% (88.6) | 1/35 | 5/5 | 0.9 s | $0.00020 |
| section | hybrid + rerank | 20b | 0.971 | 0.942 | 97.1% (94.3) | 1/35 | 5/5 | 9.7 s | $0.00019 |
| section | hybrid + rerank | 120b | 0.971 | 0.942 | 94.3% (94.3) | 1/35 | 4/5 | 7.3 s | $0.00041 |

All six declined all 10 unanswerable questions; citation precision was 100% except fixed + dense (97.5%). BM25 alone: 0.971 / 0.912 (fixed), 0.971 / 0.874 (section). Latency is from a laptop CPU.

## Best configuration: hybrid retrieval, no reranker
- **Hybrid beats dense** on both chunkings: fewer wrong or refused answers (1 vs 2 on fixed, 2 vs 4 on section), and both dense setups fail adversarial X04 by quoting withdrawn 2022 text as current.
- **Chunking did not separate at the answer level.** Section chunks rank the right clause higher (MRR 0.805 → 0.860), but answers are 33/35 vs 34/35, each losing a different question. I keep section chunks because a citation then points to one whole numbered clause.
- **The reranker is not worth it:** one extra correct answer for about 10× the latency. The larger model adds nothing.
- **Caveats.** Every gap is one or two questions, the same size as my judge overrides. BM25 alone ranks best because the questions reuse the regulations' wording; hybrid is a hedge for paraphrased queries this eval does not test.

## Three failed questions
1. **A30, chunking (fixed).** *"Up to what amount can a mutual fund SIP run without AFA?"* The ₹1,00,000 limit sits in a 400-token window that starts in the previous section and carries its heading, "Pre-transaction Notification". Dense misses it, fusion drops BM25's rank-1 hit out of the top 5, and the model declines. The section chunk "8. Transaction limits" ranks 1st everywhere.
2. **A27, retrieval (section + dense).** *"When does Rule 4 (Consent Managers) come into force?"* The answer is in Rule 1 ("commencement"), so dense returns five Consent Manager chunks and declines. BM25 matches "come into force", so hybrid answers correctly.
3. **A09, generation.** *"What net worth must a new payment aggregator have?"* The right chunk ranks 1st and states two stages (₹15 crore at application, ₹25 crore by year 3). On section + hybrid, both 20b and 120b report only the first.

## Outdated documents
- **Metadata:** every chunk carries `status`, `superseded_by` and issue date, from RBI's repeal notes.
- **Current-rule questions:** superseded chunks are dropped when their replacement is in the corpus.
- **Historical questions** ("how did … change", or the year of a superseded document): old text is allowed and the newest version's best chunk is added.
- **Warning in code:** an answer resting on a withdrawn document (the 2016 KYC Direction, whose replacement isn't in the corpus) gets a note naming it and its replacement.

`results/superseded_demo.md` shows the effect: for the DLG cap, the naive pipeline cites the withdrawn May 2025 Directions and the versioned one cites the current clause. My first detector was a loose keyword list; new test questions showed "before" and "withdrawn" switching the filter off, so I narrowed it and regenerated the affected answers. **Remaining gaps:** supersession is mapped per document (the May 2025 Directions covered all lenders, their successor here covers NBFCs only), and X04 shows a historical question can still pull old text without a caveat.

## One thing I'd do differently
Build a larger, harder eval set first: questions written without looking at the passages, paraphrased wording, and near-miss unanswerable questions. The current set cannot separate the configurations that matter.
