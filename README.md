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
  make_metadata.py
results/                   retrieval_metrics.json, answers_*.jsonl, results_table.md/.csv, superseded_demo.md
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
On a low-RAM machine set `OPENBLAS_NUM_THREADS=1`.

## Status of the results
- **Fully evaluated run (prompt v1):** the numbers in `WRITEUP.md` and `results/results_table.md`. Its answers, all 300
  judge verdicts and the manual audit are in `results/old_run/prompt_v1/` (with the v1 prompt as `generate_prompt_v1.py`).
- **Current prompt (v2, in `src/generate.py`):** changed after held-out live questions (everyday wording such as "OTP",
  entity scope, injection flag). All 300 answers are regenerated in `results/answers_*.jsonl`, but only 90 of 300 judge
  verdicts finished (`results/judgments_*.jsonl`) before Groq's free-tier capacity for the judge model ran out, so
  the v2 table is not built yet. To finish: `python src/evaluate.py judge`, audit, then `python src/evaluate.py table`.
All Hugging Face caches go to `.cache/` inside the project.
