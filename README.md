# RAG over Indian digital payments & lending regulation

A retrieval-augmented QA pipeline over 15 public regulatory documents (RBI directions/circulars,
Payments Vision 2025, DPDP Rules 2025). It compares two chunking strategies and dense vs hybrid
retrieval, answers with cited chunk ids, declines when the sources don't support an answer, and
keeps superseded circulars from being cited as current law.

See `WRITEUP.md` for results and analysis, `RESEARCH.md` for the design research.

## Layout
```
corpus/sources.json        document list (URLs, dates, status, superseded_by)
corpus/metadata.csv        generated metadata + parsing notes for every document
corpus/raw/                downloaded files (RBI notification pages as HTML, DPDP Gazette PDF)
corpus/adversarial/        synthetic prompt-injection test document (not part of the 15)
corpus/parsed/             cleaned text + blocks with char offsets
data/chunks/               chunks_A.jsonl (fixed 400/50), chunks_B.jsonl (section-aware)
data/index/                FAISS + BM25 indexes per strategy
eval/build_eval_set.py     the 50 questions; verifies gold passages and writes eval/eval_set.jsonl
src/
  download.py  parse.py  chunk.py  index.py      ingestion
  retrieve.py                                    dense / BM25 / hybrid (RRF) / rerank + version policy
  generate.py  judge.py                          LLM answer step (Groq / OpenRouter / Anthropic), LLM judge
  evaluate.py                                    metrics + results table
  superseded_demo.py                             old-vs-new circular demo
  ask.py                                         ask one question, or compare setups side by side
  tables.py                                      terminal and Markdown table helpers
  make_metadata.py
results/                   retrieval_metrics.json, answers_*.jsonl, judgments_*.jsonl, results_table.md/.csv, superseded_demo.md
results/old_run/           earlier and stopped runs (prompt v1, partial judge runs), kept for comparison
eval/judge_audit.json      manual audit of judge verdicts
scripts/                   document PDFs, Markdown table check/format helpers
```

## Run
```bash
py -3.12 -m venv .venv && .venv/Scripts/pip install -r requirements.txt
python src/download.py            # fetch corpus (RBI PDFs are bot-protected; notification pages are used)
python src/parse.py               # clean text, drop Hindi Gazette pages, strip headers/footers
python src/make_metadata.py
python src/chunk.py               # strategies A and B
python src/index.py               # BGE embeddings + FAISS, BM25
python eval/build_eval_set.py     # 35 answerable + 10 unanswerable + 5 adversarial
python src/evaluate.py retrieval  # hit@5 / MRR@10 for all retrieval configs (no API needed)

# needs GROQ_API_KEY in .env (git-ignored): echo GROQ_API_KEY=... > .env
python src/evaluate.py answers    # all answer configs, resumable
python src/evaluate.py judge --loop  # LLM judge (can run alongside `answers`)
python src/evaluate.py table      # results/results_table.md
python src/superseded_demo.py     # results/superseded_demo.md
python src/ask.py "your question" # one question end to end: retrieved chunks, answer, citations, flags
```
Models: embeddings `BAAI/bge-base-en-v1.5`, reranker `cross-encoder/ms-marco-MiniLM-L-12-v2`,
generators `openai/gpt-oss-20b` and `openai/gpt-oss-120b` on Groq (`GROQ_API_KEY` in `.env`). Groq's free tier allows
200k tokens/day per model per account, so when `OPENROUTER_API_KEY` is set `gpt-oss-120b` goes through OpenRouter,
pinned to the Groq provider (same model and serving stack). Judge `qwen/qwen3.8-27b` on Groq (env `RAG_JUDGE_MODEL`),
a different model family from the generators; manual audit overrides are in `eval/judge_audit.json`.
`claude-*` model names (env `RAG_GEN_MODEL`) route to the Anthropic API (`ANTHROPIC_API_KEY`).
On a low-RAM machine set `OPENBLAS_NUM_THREADS=1`. All Hugging Face caches go to `.cache/` inside the project.

## Results (prompt v2, all 300 answers judged and audited)

| Chunks  | Retrieval       | Model | hit@5 |   MRR | Correct | Wrong answers | False refusals | Adversarial | Latency |
| ------- | --------------- | ----- | ----: | ----: | ------: | ------------: | -------------: | ----------: | ------: |
| fixed   | dense           | 20b   | 0.914 | 0.692 |   91.4% |             1 |           1/35 |         5/5 |   1.1 s |
| fixed   | hybrid          | 20b   | 0.971 | 0.805 |   97.1% |             1 |           0/35 |         5/5 |   1.2 s |
| section | dense           | 20b   | 0.886 | 0.796 |   91.4% |             0 |           3/35 |         4/5 |   1.0 s |
| section | hybrid          | 20b   | 0.971 | 0.860 |   97.1% |             0 |           1/35 |         5/5 |   1.1 s |
| section | hybrid + rerank | 20b   | 0.971 | 0.942 |   97.1% |             0 |           1/35 |         5/5 |   4.4 s |
| section | hybrid + rerank | 120b  | 0.971 | 0.942 |   97.1% |             0 |           0/35 |         5/5 |   5.5 s |

Recommended setup: **section chunks + hybrid retrieval, no reranker** (best correctness, no wrong answers, about 1 s).
All six setups declined all 10 unanswerable questions. Full tables: `results/results_table.md`; analysis: `WRITEUP.md`.

- **Answers:** `results/answers_*.jsonl`, generated with the current prompt (v2) in `src/generate.py`.
- **Judge verdicts:** `results/judgments_*.jsonl`, all 300 from `qwen/qwen3.8-27b` on Groq.
- **Manual audit:** `eval/judge_audit.json`, 43 verdicts checked, 77% agreement, 10 overrides (all where the judge was
  stricter than its rubric). "Correct" above applies the audit; raw judge scores are in the full table.
- **Earlier run (prompt v1):** answers, verdicts and audit in `results/old_run/prompt_v1/`, kept for comparison.
  `results/old_run/` also holds partial runs that were stopped (for example verdicts from another provider), so that
  every reported verdict comes from one judge on one provider.

### Getting all verdicts on the free tier
Groq's free tier allows 200k tokens per day per model per **account** (about 55-100 judge verdicts), and keys from the
same account share it. `evaluate.py judge` is resumable: it skips questions already judged, so it can be re-run with a
key from another account (`GROQ_API_KEY=... python src/evaluate.py judge <config>`). Give each process different
configs so two processes never append to the same file.
