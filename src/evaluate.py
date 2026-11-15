"""Evaluation harness.

  python src/evaluate.py retrieval          # hit@5, MRR@10, latency for every retrieval config (no API)
  python src/evaluate.py answers [CFG ...]  # full pipeline for answer configs (Groq / OpenRouter)
  python src/evaluate.py judge [CFG ...]    # LLM judge for stored answers
  python src/evaluate.py table              # results/results_table.md + .csv

Hit: a retrieved chunk from the gold document whose [char_start, char_end) overlaps
the gold passage span. This works for both chunking strategies.
"""
import json
import statistics as st
import sys
import time

import config as C
from tables import md_table, text_table

RETRIEVAL_CONFIGS = [  # name, strategy, method, rerank
    ("A-dense", "A", "dense", False), ("A-bm25", "A", "bm25", False), ("A-hybrid", "A", "hybrid", False),
    ("A-hybrid-rerank", "A", "hybrid", True),
    ("B-dense", "B", "dense", False), ("B-bm25", "B", "bm25", False), ("B-hybrid", "B", "hybrid", False),
    ("B-hybrid-rerank", "B", "hybrid", True), ("B-dense-rerank", "B", "dense", True),
]
ANSWER_CONFIGS = {  # name -> (strategy, method, rerank, generator model)
    # Trimmed to fit Groq's free tier (200k tokens/day per model, ~3k tokens per answer).
    # Chunking A vs B and dense vs BM25 vs hybrid are compared for all 9 retrieval configs
    # by hit@5 / MRR (no LLM needed); the answer step compares dense vs hybrid with the same
    # generator, and the best retrieval config on the larger model.
    "B-dense-gptoss20b": ("B", "dense", False, C.SMALL_GEN_MODEL),
    "B-hybrid-gptoss20b": ("B", "hybrid", False, C.SMALL_GEN_MODEL),
    "B-hybrid-rerank": ("B", "hybrid", True, C.GEN_MODEL),
    # Added so every comparison changes one thing at a time with the same generator (20b):
    # fixed vs section chunks (A-* vs B-*), dense vs hybrid, and reranker on/off.
    "A-dense-gptoss20b": ("A", "dense", False, C.SMALL_GEN_MODEL),
    "A-hybrid-gptoss20b": ("A", "hybrid", False, C.SMALL_GEN_MODEL),
    "B-hybrid-rerank-gptoss20b": ("B", "hybrid", True, C.SMALL_GEN_MODEL),
}


def load_eval():
    with (C.EVAL / "eval_set.jsonl").open(encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def is_hit(chunk, item):
    return (chunk["doc_id"] == item["gold_doc"] and chunk["char_start"] < item["gold_char_end"]
            and chunk["char_end"] > item["gold_char_start"])


def retrieval_metrics(results, item):
    ranks = [c["rank"] for c in results if is_hit(c, item)]
    first = min(ranks) if ranks else None
    return {"hit@5": int(first is not None and first <= 5), "rr@10": (1.0 / first) if first else 0.0, "first_hit_rank": first}


_retrievers = {}


def get_retriever(strategy, rerank):
    key = (strategy, rerank)
    if key not in _retrievers:
        from retrieve import Retriever  # lazy: the judge step doesn't need torch / the models
        _retrievers.clear()  # one retriever in memory at a time (low-RAM machine)
        _retrievers[key] = Retriever(strategy, use_reranker=rerank)
        _retrievers[key].search("warm up the models", method="hybrid", rerank=rerank)  # exclude load time
    return _retrievers[key]


def run_retrieval():
    items = [i for i in load_eval() if i["type"] == "answerable"]
    rows, per_q = [], []
    for name, strategy, method, rerank in RETRIEVAL_CONFIGS:
        r = get_retriever(strategy, rerank)
        hits, rrs, lats = [], [], []
        for it in items:
            res = r.search(it["question"], method=method, k=10, rerank=rerank)
            m = retrieval_metrics(res["results"], it)
            hits.append(m["hit@5"]); rrs.append(m["rr@10"]); lats.append(res["latency_s"])
            per_q.append({"config": name, "qid": it["qid"], **m,
                          "top5": [(c["chunk_id"], c["section_heading"][:50]) for c in res["results"][:5]]})
        row = {"config": name, "strategy": strategy, "method": method, "rerank": rerank,
               "hit@5": sum(hits) / len(hits), "MRR@10": sum(rrs) / len(rrs),
               "retrieval_latency_ms": 1000 * st.mean(lats)}
        rows.append(row)
        print(f"{name:<18} hit@5={row['hit@5']:.3f}  MRR@10={row['MRR@10']:.3f}  latency={row['retrieval_latency_ms']:.0f} ms")
    (C.RESULTS / "retrieval_metrics.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print()
    print(text_table(*retrieval_rows(rows), right=(3, 4, 5)))
    with (C.RESULTS / "retrieval_per_question.jsonl").open("w", encoding="utf-8") as f:
        for p in per_q:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def run_answers(names):
    from generate import answer
    items = load_eval()
    for name in names:
        strategy, method, rerank, model = ANSWER_CONFIGS[name]
        r = get_retriever(strategy, rerank)
        out_path = C.RESULTS / f"answers_{name}.jsonl"
        done = set()
        if out_path.exists():
            done = {json.loads(l)["qid"] for l in out_path.open(encoding="utf-8")}
        with out_path.open("a", encoding="utf-8") as f:
            for it in items:
                if it["qid"] in done:
                    continue
                t0 = time.perf_counter()
                ret = r.search(it["question"], method=method, k=C.TOP_K, rerank=rerank)
                res = answer(it["question"], ret, model=model)
                total = time.perf_counter() - t0 - res.get("rate_limit_wait_s", 0.0)  # pipeline time, excl. free-tier throttling
                chunks = {c["chunk_id"]: c for c in ret["results"]}
                rm = retrieval_metrics(ret["results"], it) if it["type"] == "answerable" else {}
                gold_cited = (any(is_hit(chunks[c], it) for c in res["citations"])
                              if it["type"] == "answerable" and res["citations"] else False)
                rec = {"config": name, "qid": it["qid"], "type": it["type"], "version_sensitive": it["version_sensitive"],
                       **{k: res[k] for k in ("answer", "citations", "refused", "refusal_reason", "invalid_citations",
                                              "superseded_cited", "injection_detected", "cost_usd", "gen_latency_s", "rate_limit_wait_s", "usage")},
                       "retrieved": res["retrieved"], "retrieval_latency_s": ret["latency_s"], "total_latency_s": total,
                       **rm, "gold_cited": gold_cited}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{name:<16} {it['qid']} refused={res['refused']!s:<5} cost=${res['cost_usd']:.4f} gen={res['gen_latency_s']:.1f}s wait={res.get('rate_limit_wait_s', 0):.0f}s", flush=True)


def load_judgments(name):
    from judge import JUDGE_VERSION
    path = C.RESULTS / f"judgments_{name}.jsonl"
    out = {}
    if path.exists():
        for l in path.open(encoding="utf-8"):
            j = json.loads(l)
            if j.get("judge_version") == JUDGE_VERSION:
                out[j["qid"]] = j  # last write wins
    return out


_chunks = {}


def load_chunks(strategy):
    if strategy not in _chunks:
        with (C.CHUNKS / f"chunks_{strategy}.jsonl").open(encoding="utf-8") as f:
            _chunks[strategy] = {c["chunk_id"]: c for c in map(json.loads, f)}
    return _chunks[strategy]


def judge_pending(names, loop=False):
    """Grade every stored answer that has no judgment under the current rubric version.
    Judgments go to results/judgments_<config>.jsonl, so this can run while generation
    is still appending to answers_<config>.jsonl. With loop=True it keeps polling until
    every config has 50 judged answers."""
    from judge import judge, JUDGE_VERSION
    items = {i["qid"]: i for i in load_eval()}
    while True:
        remaining = 0
        for name in names:
            path = C.RESULTS / f"answers_{name}.jsonl"
            if not path.exists():
                remaining += len(items)
                continue
            by_id = load_chunks(ANSWER_CONFIGS[name][0])  # text only; no models loaded
            done = load_judgments(name)
            recs = [json.loads(l) for l in path.open(encoding="utf-8")]
            remaining += len(items) - len(recs)
            with (C.RESULTS / f"judgments_{name}.jsonl").open("a", encoding="utf-8") as f:
                for r in recs:
                    if r["qid"] in done:
                        continue
                    j = judge(items[r["qid"]], r, [by_id[c] for c in r["citations"]])
                    j.update(qid=r["qid"], judge_version=JUDGE_VERSION)
                    f.write(json.dumps(j, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"judge {name:<16} {r['qid']} {j.get('verdict')}", flush=True)
        if not loop or remaining == 0:
            return
        time.sleep(30)


def summarise(name):
    path = C.RESULTS / f"answers_{name}.jsonl"
    recs = [json.loads(l) for l in path.open(encoding="utf-8")]
    judg = load_judgments(name)
    missing = [r["qid"] for r in recs if r["qid"] not in judg]
    if missing:
        raise SystemExit(f"{name}: {len(missing)} answers not judged yet, run `evaluate.py judge`")
    audit_path = C.EVAL / "judge_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")).get(name, {}) if audit_path.exists() else {}
    raw_correct = sum(judg[r["qid"]]["verdict"] == "correct" for r in recs if r["type"] == "answerable")
    for r in recs:
        r["judge"] = dict(judg[r["qid"]])
        if r["qid"] in audit:  # manual audit override (documented in eval/judge_audit.json)
            v = audit[r["qid"]]["verdict"]
            r["judge"]["verdict"] = v
            if "unsupported_citations" in audit[r["qid"]]:
                r["judge"]["unsupported_citations"] = audit[r["qid"]]["unsupported_citations"]
            if r["type"] == "adversarial":
                r["judge"]["adversarial_pass"] = v == "pass"
    ans = [r for r in recs if r["type"] == "answerable"]
    una = [r for r in recs if r["type"] == "unanswerable"]
    adv = [r for r in recs if r["type"] == "adversarial"]
    answered = [r for r in ans if not r["refused"]]
    cited = [c for r in answered for c in r["citations"]]
    unsupported = sum(len(r["judge"].get("unsupported_citations", [])) for r in answered)
    return {
        "config": name,
        "correct_%": 100 * sum(r["judge"]["verdict"] == "correct" for r in ans) / len(ans),
        "correct_raw_judge_%": 100 * raw_correct / len(ans),
        "audit_overrides": len(audit),
        "correct_or_partial_%": 100 * sum(r["judge"]["verdict"] in ("correct", "partial") for r in ans) / len(ans),
        "citation_precision_%": 100 * (1 - unsupported / len(cited)) if cited else 0.0,
        "gold_cited_%": 100 * sum(r["gold_cited"] for r in answered) / len(answered) if answered else 0.0,
        "correct_refusal_%": 100 * sum(r["refused"] for r in una) / len(una),
        "false_refusal_%": 100 * sum(r["refused"] for r in ans) / len(ans),
        "adversarial_pass_%": 100 * sum(bool(r["judge"].get("adversarial_pass")) for r in adv) / len(adv),
        "superseded_cited": sum(len(r["superseded_cited"]) for r in recs),
        "avg_latency_s": st.mean(r["total_latency_s"] for r in recs),
        "cost_per_query_usd": st.mean(r["cost_usd"] for r in recs),
        "n": len(recs),
    }


CHUNKING = {"A": "fixed 400/50", "B": "section"}
ROW_ORDER = ["A-dense-gptoss20b", "A-hybrid-gptoss20b", "B-dense-gptoss20b", "B-hybrid-gptoss20b",
             "B-hybrid-rerank-gptoss20b", "B-hybrid-rerank"]


def retrieval_rows(rows):
    """(headers, rows) for the retrieval-only comparison of all retrieval configs."""
    out = [[CHUNKING[r["strategy"]], r["method"], "yes" if r["rerank"] else "no",
            f"{r['hit@5']:.3f}", f"{r['MRR@10']:.3f}", f"{r['retrieval_latency_ms']:.0f}"] for r in rows]
    return ["Chunking", "Method", "Reranker", "hit@5", "MRR@10", "Latency (ms)"], out


def table():
    """Write results/results_table.md (+ .csv with every column) and print the same tables."""
    retr_all = json.loads((C.RESULTS / "retrieval_metrics.json").read_text(encoding="utf-8"))
    retr = {r["config"]: r for r in retr_all}
    n_eval = len(load_eval())
    rows = []
    for name in ROW_ORDER + [n for n in ANSWER_CONFIGS if n not in ROW_ORDER]:
        strategy, method, rerank, model = ANSWER_CONFIGS[name]
        path = C.RESULTS / f"answers_{name}.jsonl"
        n_done = sum(1 for _ in path.open(encoding="utf-8")) if path.exists() else 0
        if n_done < n_eval:
            print(f"skipping {name}: {n_done}/{n_eval} answers so far")
            continue
        s = summarise(name)
        rr = retr.get(f"{strategy}-{method}" + ("-rerank" if rerank else ""), {})
        rows.append({"config": name, "chunking": CHUNKING[strategy], "retrieval": method + (" + rerank" if rerank else ""),
                     "generator": model, "hit@5": rr.get("hit@5"), "MRR@10": rr.get("MRR@10"),
                     **{k: v for k, v in s.items() if k != "config"}})
    import pandas as pd
    pd.DataFrame(rows).to_csv(C.RESULTS / "results_table.csv", index=False)

    ident = lambda r: [r["chunking"], r["retrieval"], r["generator"].split("/")[-1]]
    count = lambda pct, n: f"{round(pct * n / 100)}/{n}"
    t1 = (["Chunking", "Retrieval", "Generator", "hit@5", "MRR@10", "Correct %", "Raw judge %", "Correct or partial %",
           "Citation precision %", "Gold chunk cited %"],
          [ident(r) + [f"{r['hit@5']:.3f}", f"{r['MRR@10']:.3f}", f"{r['correct_%']:.1f}", f"{r['correct_raw_judge_%']:.1f}",
                       f"{r['correct_or_partial_%']:.1f}", f"{r['citation_precision_%']:.1f}", f"{r['gold_cited_%']:.1f}"]
           for r in rows], tuple(range(3, 10)))
    t2 = (["Chunking", "Retrieval", "Generator", "Unanswerable declined", "False refusals", "Adversarial passed",
           "Superseded chunks cited", "Judge overrides"],
          [ident(r) + [count(r["correct_refusal_%"], 10), count(r["false_refusal_%"], 35), count(r["adversarial_pass_%"], 5),
                       str(r["superseded_cited"]), str(r["audit_overrides"])] for r in rows], tuple(range(3, 8)))
    t3 = (["Chunking", "Retrieval", "Generator", "Avg latency (s)", "Cost per query (USD)", "Questions"],
          [ident(r) + [f"{r['avg_latency_s']:.1f}", f"{r['cost_per_query_usd']:.5f}", str(r["n"])] for r in rows], (3, 4, 5))
    h4, r4 = retrieval_rows(retr_all)
    sections = [
        ("Retrieval and answer quality", "35 answerable questions. \"Correct %\" applies the manual audit in "
         "`eval/judge_audit.json`; \"Raw judge %\" is the LLM judge alone.", t1),
        ("Refusals and safety", "10 unanswerable, 35 answerable and 5 adversarial questions.", t2),
        ("Latency and cost", "Averages over all 50 questions. Latency is end to end on a laptop CPU and excludes "
         "free-tier rate-limit waits; cost uses list prices.", t3),
        ("Retrieval only, all configurations", "35 answerable questions, no LLM involved.", (h4, r4, (3, 4, 5))),
    ]
    md = ["# Results", "", "One row per configuration. The full set of columns is in `results_table.csv`.", ""]
    for title, note, (h, r, right) in sections:
        md += [f"## {title}", "", note, "", md_table(h, r, right), ""]
        print()
        print(title)
        print(text_table(h, r, right))
    (C.RESULTS / "results_table.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "retrieval"
    if cmd == "retrieval":
        run_retrieval()
    elif cmd == "answers":
        run_answers(sys.argv[2:] or list(ANSWER_CONFIGS))
    elif cmd == "judge":
        args = [a for a in sys.argv[2:] if a != "--loop"]
        judge_pending(args or list(ANSWER_CONFIGS), loop="--loop" in sys.argv)
    elif cmd == "table":
        table()
