| Chunking     | Retrieval       | Generator    | hit@5 | MRR@10 | Correct % | Raw judge % | Correct or partial % | Citation precision % | Gold chunk cited % |
| ------------ | --------------- | ------------ | ----: | -----: | --------: | ----------: | -------------------: | -------------------: | -----------------: |
| fixed 400/50 | dense           | gpt-oss-20b  | 0.914 |  0.692 |      94.3 |        94.3 |                 97.1 |                 97.5 |               94.1 |
| fixed 400/50 | hybrid          | gpt-oss-20b  | 0.971 |  0.805 |      97.1 |        88.6 |                 97.1 |                100.0 |              100.0 |
| section      | dense           | gpt-oss-20b  | 0.886 |  0.796 |      88.6 |        82.9 |                 91.4 |                100.0 |               96.9 |
| section      | hybrid          | gpt-oss-20b  | 0.971 |  0.860 |      94.3 |        88.6 |                 97.1 |                100.0 |              100.0 |
| section      | hybrid + rerank | gpt-oss-20b  | 0.971 |  0.942 |      97.1 |        94.3 |                 97.1 |                100.0 |              100.0 |
| section      | hybrid + rerank | gpt-oss-120b | 0.971 |  0.942 |      94.3 |        94.3 |                 97.1 |                100.0 |              100.0 |
