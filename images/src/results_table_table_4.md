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
