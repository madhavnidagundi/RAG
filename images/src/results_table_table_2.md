| Chunking     | Retrieval       | Generator    | Unanswerable declined | False refusals | Adversarial passed | Superseded chunks cited | Judge overrides |
| ------------ | --------------- | ------------ | --------------------: | -------------: | -----------------: | ----------------------: | --------------: |
| fixed 400/50 | dense           | gpt-oss-20b  |                 10/10 |           1/35 |                4/5 |                       1 |               2 |
| fixed 400/50 | hybrid          | gpt-oss-20b  |                 10/10 |           1/35 |                5/5 |                       1 |               5 |
| section      | dense           | gpt-oss-20b  |                 10/10 |           3/35 |                4/5 |                       1 |               2 |
| section      | hybrid          | gpt-oss-20b  |                 10/10 |           1/35 |                5/5 |                       1 |               4 |
| section      | hybrid + rerank | gpt-oss-20b  |                 10/10 |           1/35 |                5/5 |                       1 |               3 |
| section      | hybrid + rerank | gpt-oss-120b |                 10/10 |           1/35 |                4/5 |                       1 |               3 |
