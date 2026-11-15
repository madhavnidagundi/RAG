# Results

One row per configuration. The full set of columns is in `results_table.csv`.

## Retrieval and answer quality

35 answerable questions. "Correct %" applies the manual audit in `eval/judge_audit.json`; "Raw judge %" is the LLM judge alone.

| Chunking     | Retrieval       | Generator    | hit@5 | MRR@10 | Correct % | Raw judge % | Correct or partial % | Citation precision % | Gold chunk cited % |
| ------------ | --------------- | ------------ | ----: | -----: | --------: | ----------: | -------------------: | -------------------: | -----------------: |
| fixed 400/50 | dense           | gpt-oss-20b  | 0.914 |  0.692 |      91.4 |        91.4 |                 94.3 |                100.0 |               94.1 |
| fixed 400/50 | hybrid          | gpt-oss-20b  | 0.971 |  0.805 |      97.1 |        94.3 |                 97.1 |                 97.7 |               97.1 |
| section      | dense           | gpt-oss-20b  | 0.886 |  0.796 |      91.4 |        91.4 |                 91.4 |                100.0 |               96.9 |
| section      | hybrid          | gpt-oss-20b  | 0.971 |  0.860 |      97.1 |        97.1 |                 97.1 |                100.0 |              100.0 |
| section      | hybrid + rerank | gpt-oss-20b  | 0.971 |  0.942 |      97.1 |        97.1 |                 97.1 |                100.0 |              100.0 |
| section      | hybrid + rerank | gpt-oss-120b | 0.971 |  0.942 |      97.1 |        97.1 |                100.0 |                 97.3 |               97.1 |

## Refusals and safety

10 unanswerable, 35 answerable and 5 adversarial questions.

| Chunking     | Retrieval       | Generator    | Unanswerable declined | False refusals | Adversarial passed | Superseded chunks cited | Judge overrides |
| ------------ | --------------- | ------------ | --------------------: | -------------: | -----------------: | ----------------------: | --------------: |
| fixed 400/50 | dense           | gpt-oss-20b  |                 10/10 |           1/35 |                5/5 |                       1 |               1 |
| fixed 400/50 | hybrid          | gpt-oss-20b  |                 10/10 |           0/35 |                5/5 |                       1 |               4 |
| section      | dense           | gpt-oss-20b  |                 10/10 |           3/35 |                4/5 |                       1 |               1 |
| section      | hybrid          | gpt-oss-20b  |                 10/10 |           1/35 |                5/5 |                       1 |               1 |
| section      | hybrid + rerank | gpt-oss-20b  |                 10/10 |           1/35 |                5/5 |                       1 |               2 |
| section      | hybrid + rerank | gpt-oss-120b |                 10/10 |           0/35 |                5/5 |                       1 |               1 |

## Latency and cost

Averages over all 50 questions. Latency is end to end on a laptop CPU and excludes free-tier rate-limit waits; cost uses list prices.

| Chunking     | Retrieval       | Generator    | Avg latency (s) | Cost per query (USD) | Questions |
| ------------ | --------------- | ------------ | --------------: | -------------------: | --------: |
| fixed 400/50 | dense           | gpt-oss-20b  |             1.1 |              0.00024 |        50 |
| fixed 400/50 | hybrid          | gpt-oss-20b  |             1.2 |              0.00023 |        50 |
| section      | dense           | gpt-oss-20b  |             1.0 |              0.00020 |        50 |
| section      | hybrid          | gpt-oss-20b  |             1.1 |              0.00020 |        50 |
| section      | hybrid + rerank | gpt-oss-20b  |             4.4 |              0.00020 |        50 |
| section      | hybrid + rerank | gpt-oss-120b |             5.5 |              0.00042 |        50 |

## Retrieval only, all configurations

35 answerable questions, no LLM involved.

| Chunking     | Method | Reranker | hit@5 | MRR@10 | Latency (ms) |
| ------------ | ------ | -------- | ----: | -----: | -----------: |
| fixed 400/50 | dense  | no       | 0.914 |  0.692 |           55 |
| fixed 400/50 | bm25   | no       | 0.971 |  0.912 |            0 |
| fixed 400/50 | hybrid | no       | 0.971 |  0.805 |           96 |
| fixed 400/50 | hybrid | yes      | 1.000 |  0.857 |        11271 |
| section      | dense  | no       | 0.886 |  0.796 |          103 |
| section      | bm25   | no       | 0.971 |  0.874 |            0 |
| section      | hybrid | no       | 0.971 |  0.860 |          100 |
| section      | hybrid | yes      | 0.971 |  0.942 |         9470 |
| section      | dense  | yes      | 0.971 |  0.938 |         8131 |
