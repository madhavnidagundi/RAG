"""Build dense (bge-base-en-v1.5 + FAISS) and keyword (BM25) indexes for each chunking strategy."""
import json
import re
import sys
import time

import bm25s
import faiss
import numpy as np

import config as C


def load_chunks(strategy):
    with (C.CHUNKS / f"chunks_{strategy}.jsonl").open(encoding="utf-8") as f:
        return [json.loads(l) for l in f]


_TOKEN = re.compile(r"₹?\d+(?:[.,]\d+)*%?|[a-z]+(?:-[a-z]+)*", re.I)
STOP = set("""a an the of and or to in on for by with as at from is are was be been shall may
which that this these those it its such any all such other than not no under per into within""".split())


def bm25_tokenize(text: str):
    """Lower-case word/number tokens. Keeps acronyms (KFS, DLA, PA-P), numbers and ₹ amounts; no stemming."""
    return [t.lower().replace(",", "") for t in _TOKEN.findall(text) if t.lower() not in STOP]


_EMB = None


def embedder():
    global _EMB
    if _EMB is None:
        from sentence_transformers import SentenceTransformer
        _EMB = SentenceTransformer(C.EMBED_MODEL, device="cpu")
        _EMB.max_seq_length = 512
    return _EMB


def embed(texts, batch_size=16, query=False):
    if query:
        texts = [C.QUERY_PREFIX + t for t in texts]
    return embedder().encode(texts, batch_size=batch_size, normalize_embeddings=True,
                             show_progress_bar=len(texts) > 50, convert_to_numpy=True).astype("float32")


def build(strategy):
    chunks = load_chunks(strategy)
    t0 = time.time()
    vecs = embed([c["embed_text"] for c in chunks])
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(C.INDEX / f"dense_{strategy}.faiss"))
    np.save(C.INDEX / f"dense_{strategy}.npy", vecs)
    t1 = time.time()
    retriever = bm25s.BM25()
    retriever.index([bm25_tokenize(c["embed_text"]) for c in chunks])
    retriever.save(str(C.INDEX / f"bm25_{strategy}"))
    print(f"strategy {strategy}: {len(chunks)} chunks embedded in {t1 - t0:.0f}s, BM25 built in {time.time() - t1:.1f}s")


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["A", "B"]):
        build(s)
