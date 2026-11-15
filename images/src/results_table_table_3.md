| Chunking     | Retrieval       | Generator    | Avg latency (s) | Cost per query (USD) | Questions |
| ------------ | --------------- | ------------ | --------------: | -------------------: | --------: |
| fixed 400/50 | dense           | gpt-oss-20b  |             1.5 |              0.00024 |        50 |
| fixed 400/50 | hybrid          | gpt-oss-20b  |             1.4 |              0.00023 |        50 |
| section      | dense           | gpt-oss-20b  |             1.1 |              0.00019 |        50 |
| section      | hybrid          | gpt-oss-20b  |             0.9 |              0.00020 |        50 |
| section      | hybrid + rerank | gpt-oss-20b  |             9.7 |              0.00019 |        50 |
| section      | hybrid + rerank | gpt-oss-120b |             7.3 |              0.00041 |        50 |
