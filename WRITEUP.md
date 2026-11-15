# Write-up: RAG over Indian digital payments & lending regulation

**Setup.** 15 public RBI and MeitY documents (~240 page-equivalents, 7 superseded) plus one planted injection note; details in `corpus/metadata.csv`. Retrieval: `bge-base` + FAISS, BM25, RRF fusion, optional MiniLM reranker. Generator: `gpt-oss-20b` (one row with 120b) over the top 5 chunks, answer prompt v2. Judge: `qwen3.8-27b`; I hand-checked 43 verdicts and agreed with 77% (overrides in `eval/judge_audit.json`, raw judge scores in brackets). Eval set: 35 answerable, 10 unanswerable, 5 adversarial questions.

| Chunks      | Retrieval       | Model   | hit@5 |   MRR | Correct (raw judge) | Wrong answers | False refusals | Adversarial | Latency |
| ----------- | --------------- | ------- | ----: | ----: | ------------------: | ------------: | -------------: | ----------: | ------: |
| fixed       | dense           | 20b     | 0.914 | 0.692 |        91.4% (91.4) |             1 |           1/35 |         5/5 |   1.1 s |
| fixed       | hybrid          | 20b     | 0.971 | 0.805 |        97.1% (94.3) |             1 |           0/35 |         5/5 |   1.2 s |
| section     | dense           | 20b     | 0.886 | 0.796 |        91.4% (91.4) |             0 |           3/35 |         4/5 |   1.0 s |
| **section** | **hybrid**      | **20b** | 0.971 | 0.860 |        97.1% (97.1) |             0 |           1/35 |         5/5 |   1.1 s |
| section     | hybrid + rerank | 20b     | 0.971 | 0.942 |        97.1% (97.1) |             0 |           1/35 |         5/5 |   4.4 s |
| section     | hybrid + rerank | 120b    | 0.971 | 0.942 |        97.1% (97.1) |             0 |           0/35 |         5/5 |   5.5 s |

"Wrong answers" counts answerable questions judged incorrect (a partial answer counts as neither correct nor wrong). All six declined all 10 unanswerable questions; citation precision was 97–100%. BM25 alone: 0.971 / 0.912 (fixed), 0.971 / 0.874 (section). Latency is from a laptop CPU; cost is about $0.0002 per question for 20b. The full table is in `results/results_table.md`.

## Best configuration: section chunks, hybrid retrieval, no reranker
- **It ties for the best correctness (34/35) and gives no wrong answers.** Its one miss is a decline, which is the safer failure for a compliance tool. Fixed + hybrid also reaches 34/35, but its miss is a confidently wrong figure (A30 below).
- **Hybrid beats dense** on both chunkings (97.1% vs 91.4%). Section + dense also fails adversarial X04 by quoting withdrawn 2022 text as current.
- **The reranker is not worth it here:** it raises MRR (0.860 → 0.942) but not a single answer, at about 4× the latency. The larger model only turns the one decline into an answer whose citation does not support it (A21).
- **Caveats.** Every gap is one to three questions, about the size of my judge overrides. BM25 alone ranks best because the questions reuse the regulations' wording; hybrid is a hedge for paraphrased queries this eval does not test.

## Three failed questions
1. **A30, chunking (fixed).** *"Up to what amount can a mutual fund SIP run without AFA?"* The ₹1,00,000 limit sits in a 400-token window that starts in the previous section and carries its heading. Fixed + dense never retrieves it and declines. Fixed + hybrid retrieves an annexure window that lists the title of a withdrawn 2016 circular ("relaxation … for payments upto ₹2,000") and answers ₹2,000. The section chunk "8. Transaction limits" ranks 1st everywhere.
2. **A21, retrieval (section, all hybrid setups).** *"Can an account aggregator process payment transactions for its customers?"* The answer is one sentence ("NBFC-AA shall not support transactions by customers") inside a long scope clause. "Payment" pulls in payment-aggregator chunks instead, so the gold sentence is not in the top 5. 20b declines; 120b answers "No" correctly but cites a chunk that does not say it.
3. **A09, generation (120b).** *"What net worth must a new payment aggregator have?"* The cited chunk states two stages (₹15 crore at application, ₹25 crore by year 3); 120b reports only the first. Under prompt v1, section + hybrid with 20b made the same mistake; under v2 all five 20b runs give both stages, but no v2 rule targets this, so I treat it as run-to-run variation, not a fix.

## Outdated documents
- **Metadata:** every chunk carries `status`, `superseded_by` and issue date, from RBI's repeal notes.
- **Current-rule questions:** superseded chunks are dropped when their replacement is in the corpus.
- **Historical questions** ("how did … change", "before 2023", or the year of a superseded-only document): old text is allowed and the newest version's best chunk is added.
- **Warning in code:** an answer resting on a withdrawn document (the 2016 KYC Direction, whose replacement isn't in the corpus) gets a note naming it and its replacement. This is the one superseded citation in every row (A34).

`results/superseded_demo.md` shows the effect: for the DLG cap, the naive pipeline cites the withdrawn May 2025 Directions and the versioned one cites the current clause. My first detector was a loose keyword list; new test questions showed "before" and "withdrawn" switching the filter off, so I narrowed it and regenerated the affected answers. **Remaining gaps:** supersession is mapped per document (the May 2025 Directions covered all lenders, their successor here covers NBFCs only), and X04 on section + dense shows a question that names an old year can still pull old text without a caveat.

## What changed between prompt v1 and v2
I tested the pipeline on new questions written in everyday words. Three failures came from the prompt, not retrieval: it declined when the user said "OTP" or "auto-pay" instead of the regulation's terms, it answered NBFC rules to a bank question without saying so, and it noticed injected text without setting the flag. Prompt v2 maps everyday words to regulatory terms, requires a scope note when the entity differs, and sets the flag whenever an injection is mentioned. I regenerated and re-judged all 300 answers. Section + hybrid went from 94.3% to 97.1%; fixed + dense went from 94.3% to 91.4%, because in one answer the model expanded "KFS" as "KYC form" (A06). The v1 results are kept in `results/old_run/prompt_v1/`.

## One thing I'd do differently
Build a larger, harder eval set first: questions written without looking at the passages, paraphrased wording, and near-miss unanswerable questions. The current set cannot separate the configurations that matter.
