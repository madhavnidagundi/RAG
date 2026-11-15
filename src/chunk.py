"""Two chunking strategies over the parsed corpus.

A  fixed : 400-token windows (bge-base tokenizer) with 50-token overlap, ends snapped
           back to a sentence boundary where one is close.
B  section: one chunk per numbered clause / heading section. Small sections are
           merged into the next one, long ones are split on paragraph boundaries.

Every chunk keeps: doc title, issue date, status, superseded_by, the nearest
section heading and the full heading path, and char offsets into the parsed text
(used to score retrieval fairly across strategies).
"""
import bisect
import json
import re

from transformers import AutoTokenizer

import config as C

TOK = AutoTokenizer.from_pretrained(C.EMBED_MODEL)


def ntok(text: str) -> int:
    return len(TOK(text, add_special_tokens=False)["input_ids"])


def load_docs():
    sources = {s["doc_id"]: s for s in json.loads((C.CORPUS / "sources.json").read_text(encoding="utf-8"))}
    docs = []
    for doc_id, meta in sources.items():
        p = C.PARSED / f"{doc_id}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            d["meta"] = meta
            docs.append(d)
    return docs


def heading_paths(blocks):
    """For every block index, the heading path in force at that block."""
    stack, paths = [], []
    for b in blocks:
        if b["is_heading"]:
            lvl = b["level"]
            stack = [h for h in stack if h[0] < lvl]
            title = re.split(r"\s*[—–]\s*", b["text"])[0][:120]  # "4. Consent Manager.— (1) ..." -> title
            stack.append((lvl, title))
        paths.append([t for _, t in stack])
    return paths


def make_chunk(doc, strategy, idx, text, start, end, path, pages):
    m = doc["meta"]
    section = path[-1] if path else m["title"]
    header = f"[{m['title']} | {m['issue_date']} | status: {m['status']} | {' > '.join(path) or 'Preamble'}]"
    return {
        "chunk_id": f"{doc['doc_id'][:3]}_{strategy}_{idx:04d}",
        "doc_id": doc["doc_id"], "strategy": strategy,
        "doc_title": m["title"], "issuer": m["issuer"], "issue_date": m["issue_date"],
        "effective_date": m["effective_date"], "status": m["status"], "superseded_by": m["superseded_by"],
        "section_heading": section, "section_path": " > ".join(path),
        "page_start": min(pages) if pages else None, "page_end": max(pages) if pages else None,
        "char_start": start, "char_end": end, "n_tokens": ntok(text),
        "text": text, "embed_text": header + "\n" + text,
    }


# ------------------------------------------------------------- Strategy A
SENT_END = re.compile(r"(?<=[.;:?!])\s+|\n\n")


def chunk_fixed(doc):
    text, blocks = doc["text"], doc["blocks"]
    paths = heading_paths(blocks)
    starts = [b["char_start"] for b in blocks]
    enc = TOK(text, add_special_tokens=False, return_offsets_mapping=True)
    offs = [o for o in enc["offset_mapping"] if o[1] > o[0]]
    chunks, i, idx = [], 0, 0
    while i < len(offs):
        j = min(i + C.FIXED_TOKENS, len(offs))
        cs, ce = offs[i][0], offs[j - 1][1]
        if j < len(offs):  # snap end back to a sentence boundary in the last 20% of the window
            window = text[cs:ce]
            cut = [m.end() for m in SENT_END.finditer(window) if m.end() > 0.8 * len(window)]
            if cut:
                ce = cs + cut[-1]
                while j > i + 1 and offs[j - 1][0] >= ce:
                    j -= 1
        seg = text[cs:ce].strip()
        bi = max(0, bisect.bisect_right(starts, cs) - 1)
        be = max(0, bisect.bisect_right(starts, ce - 1) - 1)
        pages = [b["page"] for b in blocks[bi:be + 1] if b["page"]]
        chunks.append(make_chunk(doc, "A", idx, seg, cs, ce, paths[bi], pages))
        idx += 1
        if j >= len(offs):
            break
        i = max(j - C.FIXED_OVERLAP, i + 1)
    return chunks


# ------------------------------------------------------------- Strategy B
def chunk_sections(doc):
    blocks = doc["blocks"]
    paths = heading_paths(blocks)
    # 1. group blocks into sections: a new section starts at every heading
    sections, cur = [], []
    for k, b in enumerate(blocks):
        if b["is_heading"] and cur:
            sections.append(cur)
            cur = []
        cur.append(k)
    if cur:
        sections.append(cur)
    # 2. merge tiny sections (e.g. a bare chapter title) into the following one
    merged, carry = [], []
    for sec in sections:
        sec = carry + sec
        size = sum(ntok(blocks[k]["text"]) for k in sec)
        if size < C.SECTION_MIN_TOKENS and sec is not sections[-1]:
            carry = sec
            continue
        merged.append(sec)
        carry = []
    if carry:
        merged.append(carry)
    # 3. split long sections on block boundaries
    chunks, idx = [], 0
    for sec in merged:
        pieces, cur, cur_tok = [], [], 0
        for k in sec:
            t = ntok(blocks[k]["text"])
            if cur and cur_tok + t > C.SECTION_MAX_TOKENS:
                pieces.append(cur)
                cur, cur_tok = [], 0
            cur.append(k)
            cur_tok += t
        if cur:
            pieces.append(cur)
        for piece in pieces:
            b0, b1 = blocks[piece[0]], blocks[piece[-1]]
            text = doc["text"][b0["char_start"]:b1["char_end"]]
            path = paths[piece[-1]] if not paths[piece[0]] else paths[piece[0]]
            # path of the deepest heading inside the piece, if the piece starts with a heading
            heads = [k for k in piece if blocks[k]["is_heading"]]
            if heads:
                path = paths[heads[-1]]
            pages = [blocks[k]["page"] for k in piece if blocks[k]["page"]]
            chunks.append(make_chunk(doc, "B", idx, text, b0["char_start"], b1["char_end"], path, pages))
            idx += 1
    return chunks


def main():
    docs = load_docs()
    for strategy, fn in (("A", chunk_fixed), ("B", chunk_sections)):
        allc = []
        for d in docs:
            allc.extend(fn(d))
        out = C.CHUNKS / f"chunks_{strategy}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for c in allc:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        toks = sorted(c["n_tokens"] for c in allc)
        print(f"strategy {strategy}: {len(allc)} chunks | tokens min {toks[0]} median {toks[len(toks)//2]} max {toks[-1]}")


if __name__ == "__main__":
    main()
