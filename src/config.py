"""Shared paths, model names and prices. All model caches stay inside the project (.cache/)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
os.environ.setdefault("HF_HOME", str(CACHE / "hf"))
os.environ.setdefault("TMP", str(CACHE / "tmp"))
os.environ.setdefault("TEMP", str(CACHE / "tmp"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# API keys live in .env (git-ignored), never in code.
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip().upper(), _v.strip().strip("\"'"))  # tolerate lowercase names / quotes

CORPUS = ROOT / "corpus"
PARSED = CORPUS / "parsed"
CHUNKS = ROOT / "data" / "chunks"
INDEX = ROOT / "data" / "index"
EVAL = ROOT / "eval"
RESULTS = ROOT / "results"
for p in (CHUNKS, INDEX, RESULTS, CACHE / "tmp"):
    p.mkdir(parents=True, exist_ok=True)

EMBED_MODEL = "BAAI/bge-base-en-v1.5"   # small enough for a laptop CPU; BGE-M3 (2.3 GB) was the alternative
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"

# Chunking
FIXED_TOKENS = 400          # + ~40-token metadata header stays under the 512-token model limit
FIXED_OVERLAP = 50
SECTION_MAX_TOKENS = 450
SECTION_MIN_TOKENS = 40

# Retrieval
TOP_K = 5
CANDIDATES = 50
RRF_K = 60
RERANK_CANDIDATES = 30

# Generation. Provider is picked from the model name: "claude-*" -> Anthropic, otherwise Groq.
SMALL_GEN_MODEL = "openai/gpt-oss-20b"    # generator in the recommended configuration
LARGE_GEN_MODEL = "openai/gpt-oss-120b"   # one evaluation row, to test whether a larger model helps
GEN_MODEL = os.environ.get("RAG_GEN_MODEL", SMALL_GEN_MODEL)  # default for ask.py / the demo; e.g. claude-haiku-5-5 uses the Anthropic API
JUDGE_MODEL = os.environ.get("RAG_JUDGE_MODEL", "qwen/qwen3.8-27b")  # different family from the generator
# USD per million tokens (input, output). Groq prices from console.groq.com/docs/model/* (Nov 2026).
PRICES = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
