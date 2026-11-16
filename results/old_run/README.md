# Earlier and stopped runs

Kept so the history of the evaluation can be checked. Nothing here feeds the reported numbers;
those come from `results/answers_*.jsonl` and `results/judgments_*.jsonl` one level up.

| Folder or file                                | What it is                                                                                         |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `prompt_v1/`                                  | The complete first run: 300 answers, 300 verdicts, manual audit and the v1 answer prompt           |
| `before_detection_fix/`                       | Answers and verdicts from before the historical-question detector was narrowed                     |
| `retrieval_metrics_before_detection_fix.json` | Retrieval metrics from the same point                                                              |
| `gptoss120b_partial/`                         | A 120b run on fixed + dense that stopped at Groq's daily limit                                     |
| `judge_deepinfra_partial/`                    | Prompt v2 verdicts from the judge served by another provider; set aside to keep one judge provider |
| `judge_openrouter_partial/`                   | 18 prompt v2 verdicts via OpenRouter; set aside for the same reason                                |
| `answers_A-dense.jsonl`, `answers_A-hybrid.jsonl` | First 120b answer files, before the configurations were renamed                                |
