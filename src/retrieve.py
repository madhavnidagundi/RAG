"""Retrieval: dense, BM25, hybrid (RRF), optional cross-encoder reranking,
and the version policy that keeps superseded circulars out of current answers.

Version policy (`version_mode`):
  "none"     - plain retrieval, no awareness of document status (used to show the failure)
  "current"  - default. Unless the question asks about the past, drop chunks from a
               superseded document whose successor is in the corpus (the successor
               text is retrievable instead). Superseded documents whose successor is
               NOT in the corpus are kept but flagged, so the answer can warn.
               If the question is historical ("2022 guidelines", "earlier", "before
               2025"...), everything is kept and the generator labels old text as old.
"""
import json
import re
import time

import bm25s
import faiss
import numpy as np

import config as C
from index import bm25_tokenize, embed, load_chunks

# A question is "historical" when it asks about an old version or about how a rule changed.
# Deliberately narrow: bare words such as "before", "prior" or "withdrawn" are common in ordinary
# questions ("disclose before disbursing", "cash withdrawn") and must not switch the filter off.
_INTENT = re.compile(
    r"\b(earlier|previously|original(ly)?|used to|no longer|superseded|repealed|histor(y|ical)|over the years|"
    r"old(er)? (rule|limit|guideline|circular|direction|version|framework|regime)s?|"
    r"previous (rule|limit|guideline|circular|direction|version|framework|regime)s?|"
    r"withdrawn (rule|guideline|circular|direction|version)s?|"
    r"(how|what) (did|has|have|had)\b[^?]*\bchang\w*|chang\w* (over|since|from|between|in the)|"
    r"compared? (to|with)|versus|vs\.?)\b", re.I)
_BEFORE_DATE = re.compile(r"\b(before|prior to|until|till|up to|as of|back in)\b[^.?]{0,30}\b(19|20)\d\d\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_superseded_years = None


def _years_of_superseded_docs():
    """Issue years of the superseded documents: 'the 2022 guidelines' names an old version,
    while 'the 2021 PPI Master Direction' names a document that is still current."""
    global _superseded_years
    if _superseded_years is None:
        src = json.loads((C.CORPUS / "sources.json").read_text(encoding="utf-8"))
        # years in which a replacement was issued are ambiguous (old and new share the year)
        repl = {s["issue_date"][:4] for s in src if s.get("supersedes")}
        _superseded_years = {s["issue_date"][:4] for s in src if s["status"] == "superseded"} - repl
    return _superseded_years


def is_historical(question: str) -> bool:
    if _INTENT.search(question) or _BEFORE_DATE.search(question):
        return True
    return any(y in _years_of_superseded_docs() for y in _YEAR.findall(question))


class Retriever:
    def __init__(self, strategy: str, use_reranker: bool = False):
        self.strategy = strategy
        self.chunks = load_chunks(strategy)
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        self.dense = faiss.read_index(str(C.INDEX / f"dense_{strategy}.faiss"))
        self.bm25 = bm25s.BM25.load(str(C.INDEX / f"bm25_{strategy}"))
        self.doc_ids = {c["doc_id"] for c in self.chunks}
        self.reranker = None
        if use_reranker:
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(C.RERANK_MODEL, device="cpu", max_length=512)

    # -- individual retrievers: return [(idx, score)] best first
    def dense_search(self, q: str, n: int):
        v = embed([q], query=True)
        scores, idx = self.dense.search(v, n)
        return [(int(i), float(s)) for i, s in zip(idx[0], scores[0]) if i >= 0]

    def bm25_search(self, q: str, n: int):
        toks = bm25_tokenize(q)
        if not toks:
            return []
        res, scores = self.bm25.retrieve([toks], k=min(n, len(self.chunks)), show_progress=False)
        return [(int(i), float(s)) for i, s in zip(res[0], scores[0]) if s > 0]

    @staticmethod
    def rrf(*rankings, k=C.RRF_K):
        fused = {}
        for ranking in rankings:
            for rank, (i, _) in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (k + rank + 1)
        return sorted(fused.items(), key=lambda x: -x[1])

    # -- version policy
    def apply_version_policy(self, ranked, question, mode):
        if mode == "none" or is_historical(question):
            return ranked, False
        kept = []
        for i, s in ranked:
            c = self.chunks[i]
            if c["status"] == "superseded" and c["superseded_by"] in self.doc_ids:
                continue  # successor is in the corpus -> never cite the old text as current
            kept.append((i, s))
        return kept, True

    def latest_version(self, doc_id):
        seen = set()
        while doc_id in self.doc_ids and doc_id not in seen:
            seen.add(doc_id)
            nxt = next((c["superseded_by"] for c in self.chunks if c["doc_id"] == doc_id), None)
            if not nxt or nxt not in self.doc_ids:
                break
            doc_id = nxt
        return doc_id

    def add_successors(self, top, ranked, k):
        """Historical / 'how did it change' questions: if old text is retrieved, make sure the
        best-matching chunk of the newest version of that document is in the context too."""
        have_docs = {self.chunks[i]["doc_id"] for i, _ in top}
        want = []
        for i, _ in top:
            c = self.chunks[i]
            if c["status"] == "superseded":
                latest = self.latest_version(c["doc_id"])
                if latest != c["doc_id"] and latest not in have_docs and latest not in want:
                    want.append(latest)
        for doc in want:
            best = next(((i, s) for i, s in ranked if self.chunks[i]["doc_id"] == doc), None)
            if best is None:  # successor not among candidates: score its chunks directly
                cand = [j for j, c in enumerate(self.chunks) if c["doc_id"] == doc]
                best = (cand[0], 0.0) if cand else None
            if best:
                top = top[:k - 1] + [best] if len(top) >= k else top + [best]
        return top

    def search(self, question: str, method: str = "hybrid", k: int = C.TOP_K,
               version_mode: str = "current", rerank: bool = False):
        t0 = time.perf_counter()
        n = C.CANDIDATES
        if method == "dense":
            ranked = self.dense_search(question, n)
        elif method == "bm25":
            ranked = self.bm25_search(question, n)
        elif method == "hybrid":
            ranked = self.rrf(self.dense_search(question, n), self.bm25_search(question, n))
        else:
            raise ValueError(method)
        ranked, filtered = self.apply_version_policy(ranked, question, version_mode)
        rerank_scores = None
        if rerank and self.reranker is not None:
            cand = ranked[:C.RERANK_CANDIDATES]
            pairs = [(question, self.chunks[i]["embed_text"]) for i, _ in cand]
            scores = self.reranker.predict(pairs, batch_size=8, show_progress_bar=False)
            ranked = sorted(zip([i for i, _ in cand], map(float, scores)), key=lambda x: -x[1])
            rerank_scores = [s for _, s in ranked]
        top = ranked[:k]
        if version_mode != "none" and is_historical(question):
            top = self.add_successors(top, ranked, k)
        out = []
        for rank, (i, s) in enumerate(top):
            c = dict(self.chunks[i])
            c["score"] = s
            c["rank"] = rank + 1
            out.append(c)
        return {"results": out, "latency_s": time.perf_counter() - t0,
                "historical": is_historical(question), "version_filtered": filtered,
                "top_rerank_score": rerank_scores[0] if rerank_scores else None}


if __name__ == "__main__":
    # Side-by-side comparison of the three retrieval methods for one question (no LLM).
    import sys
    r = Retriever(sys.argv[1] if len(sys.argv) > 1 else "B")
    q = sys.argv[2] if len(sys.argv) > 2 else "Can digital lending data be stored outside India?"
    methods = ("dense", "bm25", "hybrid")
    res = {m: r.search(q, method=m)["results"] for m in methods}
    cell = lambda c: f"{c['chunk_id']} {'(superseded) ' if c['status'] == 'superseded' else ''}{c['section_heading'][:28]}"
    rows = [[str(k + 1)] + [cell(res[m][k]) if k < len(res[m]) else "" for m in methods] for k in range(C.TOP_K)]
    headers = ["#"] + [m.upper() for m in methods]
    widths = [max(len(x) for x in col) for col in zip(headers, *rows)]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = lambda row: "| " + " | ".join(x.ljust(w) for x, w in zip(row, widths)) + " |"
    print(f"Q: {q}")
    print(line)
    print(fmt(headers))
    print(line)
    for row in rows:
        print(fmt(row))
    print(line)
