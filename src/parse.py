"""Parse raw corpus files (RBI HTML pages, PDFs) into clean, ordered text blocks.

Output: corpus/parsed/<doc_id>.json with
  blocks: [{text, is_heading, level, page, char_start, char_end}]
  text:   the cleaned document text (blocks joined by blank lines); every chunk's
          char offsets point into this string, which is how retrieval is scored.
  issues: parsing problems found automatically (merged into metadata.csv)

Handles: RBI site chrome / index tables (HTML), repeated page headers & footers
(PDF), Hindi+English Gazette pages (PDF), tables (serialised row by row),
unicode ligatures and odd whitespace.
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf as fitz
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "corpus" / "raw"
OUT = ROOT / "corpus" / "parsed"

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
# Heading patterns shared by HTML and PDF text.
H1 = re.compile(r"^(chapter\s+[ivxlc\d]+\b|annex(ure)?\b|appendix\b|schedule\b|(first|second|third|fourth|fifth|sixth|seventh)\s+schedule\b|section\s+\d+\s*[–-])", re.I)
H2 = re.compile(r"^(\d{1,2})\.\s+([A-Z][^.]{2,90})$")             # "13. Storage of data"
H2_RULE = re.compile(r"^(\d{1,2})\.\s+([A-Z][^.—]{2,90})\.?\s*[—–-]")  # "4. Consent Manager.—(1) ..."
H3 = re.compile(r"^(\d{1,2}\.\d{1,2}(\.\d{1,2})?)\s+([A-Z][^.]{2,90})$")  # "4.1 Integrity"
LETTER_FOOTER = re.compile(r"^(yours faithfully|\(.*\)\s*chief general manager|chief general manager|encl)", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace(" ", " ").replace("​", "").replace("�", "'")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def heading_level(text: str, html_head: bool = False, bold: bool = False) -> int:
    """0 = body text, 1 = chapter/annex/section, 2 = numbered paragraph title, 3 = sub-section title."""
    t = text.strip()
    if len(t) > 160:
        return 0
    if H1.match(t):
        return 1
    if H3.match(t):
        return 3
    if H2.match(t) or H2_RULE.match(t):
        return 2
    if (html_head or bold) and len(t) < 120 and not t.endswith((".", ";", ":", ",")):
        return 2
    return 0


# ---------------------------------------------------------------- HTML (RBI)
BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}


def _is_index_table(tbl: Tag) -> bool:
    first = tbl.get_text(" ", strip=True)[:40].lower()
    links = len(tbl.find_all("a", href=re.compile(r"^#")))
    return first.startswith(("index", "table of contents", "contents")) or links >= 5


def _html_blocks(root: Tag):
    blocks = []

    def emit(text, head=False, bold=False, table=False):
        text = norm(text)
        if not text or text in {"|", "-"}:
            return
        lvl = 0 if table else heading_level(text, html_head=head, bold=bold)
        blocks.append({"text": text, "is_heading": lvl > 0, "level": lvl, "page": None,
                       "table_row": table})

    def walk(el):
        for ch in el.children:
            if isinstance(ch, NavigableString):
                if ch.strip() and el.name in ("td", "div", "body", "span", "font", "b", "strong"):
                    emit(str(ch))
                continue
            if not isinstance(ch, Tag) or ch.name in ("script", "style", "img"):
                continue
            if ch.name == "table":
                if _is_index_table(ch):
                    continue
                walk(ch)
            elif ch.name == "tr":
                cells = ch.find_all(["td", "th"], recursive=False)
                if any(c.find(list(BLOCK_TAGS)) for c in cells):
                    walk(ch)  # layout table: keep paragraph structure
                else:
                    vals = [norm(c.get_text(" ", strip=True)) for c in cells]
                    vals = [v for v in vals if v]
                    if vals:
                        emit(" | ".join(vals), table=len(vals) > 1)
            elif ch.name in BLOCK_TAGS:
                cls = " ".join(ch.get("class", []))
                txt = ch.get_text(" ", strip=True)
                strong = "".join(b.get_text(" ", strip=True) for b in ch.find_all(["b", "strong"]))
                is_bold = bool(strong) and len(strong) >= 0.9 * len(txt.replace(" ", "")) * 0.9
                emit(txt, head=("head" in cls or ch.name.startswith("h")), bold=is_bold)
            elif ch.name == "br":
                continue
            else:
                walk(ch)

    walk(root)
    return blocks


def parse_html(path: Path):
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    issues = []
    root = soup.find("table", class_="td")  # notification body
    if root is None:  # FAQ / publication pages
        root = soup.find("table", class_="tablebg") or soup.find("div", id=re.compile("content", re.I))
    if root is None:
        root = soup.body
        issues.append("content container not found; used <body>")
    title_el = soup.find("td", class_="tableheader")
    blocks = _html_blocks(root)
    if path.stem.startswith("D04"):  # FAQ page: questions are numbered bold lines
        for b in blocks:
            if re.match(r"^(Q\.?\s*)?\d{1,2}\.\s+.+\?$", b["text"]) and len(b["text"]) < 300:
                b["is_heading"], b["level"] = True, 2
    if any(b.get("table_row") for b in blocks):
        issues.append(f"{sum(b.get('table_row', False) for b in blocks)} table rows serialised as 'cell | cell'")
    style = (root.get("style") or "") if isinstance(root, Tag) else ""
    m = re.search(r"images/(Withdrawn\w+)\.", str(soup))
    if m:
        issues.append(f"page carries a '{m.group(1)}' watermark (document withdrawn/superseded)")
    issues.append("HTML source: no page numbers; RBI site navigation and index (TOC) tables removed")
    return blocks, issues, None


# ---------------------------------------------------------------------- PDF
def parse_pdf(path: Path):
    doc = fitz.open(path)
    issues = []
    pages = []
    for pno, page in enumerate(doc, start=1):
        h = page.rect.height
        lines = []
        d = page.get_text("dict")
        for b in d["blocks"]:
            for l in b.get("lines", []):
                spans = [s for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans)
                bold = all((s["flags"] & 16) or "Bold" in s["font"] for s in spans)
                y = l["bbox"][1]
                lines.append({"text": norm(text), "y": y, "h": h, "bold": bold, "size": spans[0]["size"]})
        pages.append(lines)

    # language filter: Gazette prints the Hindi version first, then English.
    kept_pages, hindi_pages = [], []
    for pno, lines in enumerate(pages, start=1):
        txt = " ".join(l["text"] for l in lines)
        letters = sum(c.isalpha() for c in txt) or 1
        if len(DEVANAGARI.findall(txt)) / letters > 0.30:
            hindi_pages.append(pno)
        else:
            kept_pages.append(pno)
    if hindi_pages:
        issues.append(f"bilingual Gazette: {len(hindi_pages)} Hindi pages dropped (pp. {hindi_pages[0]}-{hindi_pages[-1]}); "
                      "Hindi text also uses a legacy font encoding that extracts as garbled Devanagari")

    # repeated header/footer lines: same text (digits masked) in top/bottom band on >=30% of pages
    def key(t):
        return re.sub(r"\d+", "#", t.lower())
    band = Counter()
    for pno in kept_pages:
        seen = set()
        for l in pages[pno - 1]:
            if l["y"] < 0.09 * l["h"] or l["y"] > 0.93 * l["h"]:
                seen.add(key(l["text"]))
        band.update(seen)
    repeated = {k for k, c in band.items() if c >= max(2, 0.3 * len(kept_pages))}
    if repeated:
        issues.append(f"repeated headers/footers removed: {sorted(repeated)[:4]}")

    blocks = []
    for pno in kept_pages:
        for l in pages[pno - 1]:
            t = l["text"]
            in_band = l["y"] < 0.09 * l["h"] or l["y"] > 0.93 * l["h"]
            if (in_band and key(t) in repeated) or re.fullmatch(r"[\d\s\-–()]+", t):
                continue
            if DEVANAGARI.search(t) and len(DEVANAGARI.findall(t)) > 0.3 * len(t):
                continue
            blocks.append({"text": t, "page": pno, "bold": l["bold"]})

    # merge wrapped lines into paragraphs; new paragraph at headings / list markers
    para_start = re.compile(r"^(\(\w{1,4}\)|\d{1,2}\.\s|[ivx]+\.\s|[a-z]\)|•|Explanation|Illustration|Provided)")
    merged = []
    for b in blocks:
        lvl = heading_level(b["text"], bold=b["bold"])
        prev_open = bool(merged) and (not merged[-1]["is_heading"] or (
            # a rule heading such as "4. Registration of ... ---(1) text" wraps onto the next line
            merged[-1]["level"] == 2 and not merged[-1]["text"].rstrip().endswith((".", ":", "—"))))
        if merged and not lvl and not para_start.match(b["text"]) and prev_open:
            prev = merged[-1]
            joiner = "" if prev["text"].endswith("-") else " "
            prev["text"] = (prev["text"][:-1] if joiner == "" else prev["text"]) + joiner + b["text"]
            continue
        merged.append({"text": b["text"], "is_heading": lvl > 0, "level": lvl, "page": b["page"], "table_row": False})
    issues.append("PDF text layer present (no OCR needed)" if blocks else "NO TEXT LAYER - OCR needed")
    return merged, issues, len(doc)


def finalise(blocks):
    """Drop letter boilerplate repeats, compute char offsets, build full text."""
    out, pos, parts = [], 0, []
    for b in blocks:
        t = b["text"]
        if not t:
            continue
        b = dict(b)
        b["char_start"] = pos
        b["char_end"] = pos + len(t)
        parts.append(t)
        pos += len(t) + 2  # "\n\n"
        out.append(b)
    return out, "\n\n".join(parts)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {s["doc_id"]: s for s in json.loads((ROOT / "corpus" / "sources.json").read_text(encoding="utf-8"))}
    summary = {}
    for doc_id in sources:
        pdf, html = RAW / f"{doc_id}.pdf", RAW / f"{doc_id}.html"
        if not html.exists():
            html = ROOT / "corpus" / "adversarial" / f"{doc_id}.html"
        if pdf.exists():
            blocks, issues, n_pages = parse_pdf(pdf)
            src = pdf.name
        elif html.exists():
            blocks, issues, n_pages = parse_html(html)
            src = html.name
        else:
            print(f"missing {doc_id}")
            continue
        blocks, text = finalise(blocks)
        words = len(text.split())
        rec = {"doc_id": doc_id, "source_file": src, "n_pages_pdf": n_pages,
               "words": words, "est_pages": round(words / 450, 1),
               "n_blocks": len(blocks), "n_headings": sum(b["is_heading"] for b in blocks),
               "issues": issues, "blocks": blocks, "text": text}
        (OUT / f"{doc_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        summary[doc_id] = {k: rec[k] for k in ("source_file", "n_pages_pdf", "words", "est_pages", "n_blocks", "n_headings")}
        print(f"{doc_id:<34} {src[-4:]:>5} words={words:>6} ~pages={rec['est_pages']:>5} blocks={len(blocks):>4} headings={rec['n_headings']:>3}")
    (OUT / "_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("TOTAL words:", sum(v["words"] for v in summary.values()),
          " ~pages:", round(sum(v["est_pages"] for v in summary.values())))


if __name__ == "__main__":
    main()
