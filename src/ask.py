"""Ask the pipeline one or more questions and see every step.

  python src/ask.py "Can digital lending data be stored outside India?"
  python src/ask.py --method dense --strategy A "question 1" "question 2"
  python src/ask.py --no-llm "question"        # retrieval only, no API call
  python src/ask.py --compare "question"       # same question through four setups, side by side

Prints the top-5 retrieved chunks (with status) as a table, then the answer, its
citations, and whether the pipeline declined.
"""
import argparse
import textwrap

import config as C
from retrieve import Retriever
from tables import text_table

COMPARE = [("A", "dense"), ("A", "hybrid"), ("B", "dense"), ("B", "hybrid")]
CHUNKING = {"A": "fixed", "B": "section"}


def wrap(label, text):
    print(textwrap.fill(text, width=110, initial_indent=label, subsequent_indent=" " * len(label)))


def flags_of(res):
    flags = []
    if res["superseded_cited"]:
        flags.append(f"cites superseded chunk(s) {', '.join(res['superseded_cited'])}")
    if res["injection_detected"]:
        flags.append("injection detected in sources")
    if res["invalid_citations"]:
        flags.append(f"invalid citation ids dropped: {', '.join(res['invalid_citations'])}")
    return "; ".join(flags) or "none"


def show_one(r, q, a):
    ret = r.search(q, method=a.method, rerank=a.rerank)
    print("=" * 110)
    wrap("Q: ", q)
    print(text_table(["Setup", "Retrieval time", "Historical question", "Superseded chunks filtered"],
                     [[f"{CHUNKING[a.strategy]} chunks, {a.method}{' + rerank' if a.rerank else ''}",
                       f"{ret['latency_s'] * 1000:.0f} ms", "yes" if ret["historical"] else "no",
                       "yes" if ret["version_filtered"] else "no"]]))
    print(text_table(["#", "Chunk", "Status", "Issued", "Document", "Section"],
                     [[c["rank"], c["chunk_id"], c["status"], c["issue_date"], c["doc_title"][:46], c["section_heading"][:40]]
                      for c in ret["results"]], right=(0,)))
    if a.no_llm:
        return
    from generate import answer
    res = answer(q, ret, model=a.model)
    if res["refused"]:
        wrap("DECLINED:  ", res["refusal_reason"])
    else:
        wrap("ANSWER:    ", res["answer"])
        print("CITATIONS: " + ", ".join(res["citations"]))
    print(f"FLAGS:     {flags_of(res)}")
    print(f"TIME:      generation {res['gen_latency_s']:.1f} s")


def compare(q, a):
    """Same question through fixed/section chunks x dense/hybrid. One summary table, then the full answers."""
    print("=" * 110)
    wrap("Q: ", q)
    rows, full, retr = [], [], {}
    for strategy, method in COMPARE:
        if strategy not in retr:
            retr.clear()  # one retriever in memory at a time
            retr[strategy] = Retriever(strategy)
            retr[strategy].search("warm up", method="hybrid")
        ret = retr[strategy].search(q, method=method)
        setup = f"{CHUNKING[strategy]} + {method}"
        top = ret["results"][0]
        row = [setup, f"{top['chunk_id']} {top['section_heading'][:30]}",
               sum(c["status"] == "superseded" for c in ret["results"])]
        if not a.no_llm:
            from generate import answer
            res = answer(q, ret, model=a.model)
            row += ["declined" if res["refused"] else "answered", ", ".join(res["citations"]) or "-", flags_of(res)[:40]]
            full.append((setup, res))
        rows.append(row)
    headers = ["Setup", "Top chunk", "Superseded in top 5"] + ([] if a.no_llm else ["Result", "Citations", "Flags"])
    print(text_table(headers, rows, right=(2,)))
    for setup, res in full:
        print()
        wrap(f"[{setup}] ", res["refusal_reason"] if res["refused"] else res["answer"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("questions", nargs="+")
    ap.add_argument("--strategy", default="B", choices=["A", "B"], help="A = fixed chunks, B = section chunks")
    ap.add_argument("--method", default="hybrid", choices=["dense", "bm25", "hybrid"])
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--model", default=C.SMALL_GEN_MODEL)
    ap.add_argument("--no-llm", action="store_true", help="retrieval only")
    ap.add_argument("--compare", action="store_true", help="run each question through four setups side by side")
    a = ap.parse_args()

    if a.compare:
        for q in a.questions:
            compare(q, a)
        return
    r = Retriever(a.strategy, use_reranker=a.rerank)
    r.search("warm up", method=a.method, rerank=a.rerank)
    for q in a.questions:
        show_one(r, q, a)


if __name__ == "__main__":
    main()
