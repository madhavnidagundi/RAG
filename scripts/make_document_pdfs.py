"""Build corpus/documents/<doc_id>.pdf for every document that was ingested from a web page.

The official RBI PDF server refuses automated downloads, so each PDF is rendered from the
parsed text of the official web page (headings kept, table rows rebuilt into real tables).
Documents that were downloaded as PDF (the DPDP Rules) are copied unchanged.
Needs Microsoft Edge (headless print-to-PDF).   python scripts/make_document_pdfs.py
"""
import csv
import html
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS, OUT, TMP = ROOT / "corpus", ROOT / "corpus" / "documents", ROOT / ".cache" / "pdf_build"
EDGE = next(p for p in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")) if p.exists())
CSS = """body{font-family:Georgia,serif;font-size:11pt;line-height:1.45;margin:0}
h1{font-size:17pt;margin:0 0 6pt} h2,h3,h4{font-size:12pt;margin:14pt 0 4pt}
p{margin:0 0 7pt;text-align:justify}
.meta{font-family:Arial,sans-serif;font-size:9pt;color:#444;border:1px solid #999;padding:6pt;margin-bottom:14pt}
table{border-collapse:collapse;width:100%;table-layout:auto;max-width:100%;margin:6pt 0 12pt;font-family:Arial,sans-serif;font-size:9pt;line-height:1.3}
th,td{border:1px solid #555;padding:3pt 5pt;vertical-align:top;text-align:left;overflow-wrap:break-word}
th{background:#e6e6e6} tr{break-inside:avoid} thead{display:table-header-group}
@page{size:A4;margin:20mm 18mm}"""


def table_html(rows):
    """rows: list of cell lists. First row is the header when it has as many cells as the widest row."""
    width = max(len(r) for r in rows)
    out, body = ["<table>"], rows
    if len(rows) > 1 and len(rows[0]) == width:
        out.append("<thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in rows[0]) + "</tr></thead>")
        body = rows[1:]
    out.append("<tbody>")
    for r in body:
        cells = [f"<td>{html.escape(c)}</td>" for c in r[:-1]]
        span = width - len(r) + 1  # a short row: let its last cell span the remaining columns
        cells.append(f'<td colspan="{span}">{html.escape(r[-1])}</td>' if span > 1 else f"<td>{html.escape(r[-1])}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def body_html(blocks):
    parts, rows = [], []
    for b in blocks + [{"text": "", "table_row": False, "end": True}]:
        if b.get("table_row"):
            rows.append([c.strip() for c in b["text"].split(" | ")])
            continue
        if rows:
            parts.append(table_html(rows))
            rows = []
        if b.get("end"):
            break
        t = html.escape(b["text"]).replace("\n", "<br>")
        if b.get("is_heading"):
            lvl = min(4, 1 + int(b.get("level") or 1))
            parts.append(f"<h{lvl}>{t}</h{lvl}>")
        else:
            parts.append(f"<p>{t}</p>")
    return "\n".join(parts)


def main():
    import pymupdf
    TMP.mkdir(parents=True, exist_ok=True)
    (OUT / "clean_text").mkdir(parents=True, exist_ok=True)
    (OUT / "web_pages_as_downloaded").mkdir(exist_ok=True)
    sources = json.loads((CORPUS / "sources.json").read_text(encoding="utf-8"))
    meta = {r["doc_id"]: r for r in csv.DictReader(open(CORPUS / "metadata.csv", encoding="utf-8"))}
    index = []
    for s in sources:
        d, url = s["doc_id"], meta[s["doc_id"]]["source_url"]
        doc = json.loads((CORPUS / "parsed" / f"{d}.json").read_text(encoding="utf-8"))
        (OUT / "clean_text" / f"{d}.txt").write_text(doc["text"], encoding="utf-8")
        pdf, web, n_tables = OUT / f"{d}.pdf", "", 0
        if (CORPUS / "raw" / f"{d}.pdf").exists():
            shutil.copy2(CORPUS / "raw" / f"{d}.pdf", pdf)
            kind = "official PDF as downloaded"
        else:
            raw = next(p for p in (CORPUS / "raw" / f"{d}.html", CORPUS / "adversarial" / f"{d}.html") if p.exists())
            shutil.copy2(raw, OUT / "web_pages_as_downloaded" / f"{d}.html")
            web = f"web_pages_as_downloaded/{d}.html"
            status = s["status"] + (f" (replaced by {s['superseded_by']})" if s.get("superseded_by") else "")
            box = "<br>".join(html.escape(x) for x in (
                f"Issuer: {meta[d]['issuer']}   |   Issued: {s['issue_date']}   |   Status: {status}",
                f"Source: {url}",
                "This PDF was generated from the text of the official web page above (site navigation removed). "
                "It is not the issuer's own PDF file."))
            body = body_html(doc["blocks"])
            n_tables = body.count("<table>")
            page = TMP / f"{d}.html"
            page.write_text(f"<!doctype html><meta charset='utf-8'><title>{html.escape(s['title'])}</title>"
                            f"<style>{CSS}</style><h1>{html.escape(s['title'])}</h1><div class='meta'>{box}</div>\n{body}",
                            encoding="utf-8")
            subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={TMP / 'edge_profile'}", f"--print-to-pdf={pdf}", page.as_uri()],
                           capture_output=True, timeout=300)
            kind = "PDF generated from the official web page text"
        pages = pymupdf.open(pdf).page_count
        index.append({"pdf": pdf.name, "pdf_type": kind, "pdf_pages": pages, "tables_rebuilt": n_tables, "web_page": web,
                      "clean_text": f"clean_text/{d}.txt", "title": s["title"], "issuer": meta[d]["issuer"],
                      "issue_date": s["issue_date"], "status": s["status"], "superseded_by": s.get("superseded_by") or "",
                      "source_url": url})
        print(f"{d:<34} {pages:>3} pages  {n_tables:>2} tables  {kind}")
    with open(OUT / "INDEX.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(index[0]))
        w.writeheader()
        w.writerows(index)
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
