"""Download the corpus listed in corpus/sources.json into corpus/raw/.

Route per document:
  1. If a real PDF for the doc already exists in corpus/raw/ (e.g. saved by hand
     from a browser), keep it.
  2. Try `download_url`. Accept it only if the bytes really are a PDF / the
     expected HTML. rbidocs.rbi.org.in answers scripted requests with a
     JavaScript bot-check page instead of the PDF; we do NOT try to get around
     that check.
  3. Fall back to `page_url` (the RBI notification web page, which carries the
     full text of the circular) and save it as .html.

curl is used for transport because it uses the Windows certificate store
(egazette.gov.in fails Python's default certificate bundle).
"""
import json
import subprocess
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "corpus" / "raw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"


def curl(url: str, out: Path) -> bool:
    r = subprocess.run(["curl", "-s", "-L", "--max-time", "180", "-A", UA, "-o", str(out), url])
    return r.returncode == 0 and out.exists() and out.stat().st_size > 1000


def is_pdf(p: Path) -> bool:
    return p.exists() and p.read_bytes()[:5] == b"%PDF-"


def is_bot_check(p: Path) -> bool:
    head = p.read_bytes()[:4000]
    return b"TSPD" in head or b"bobcmn" in head


def main() -> None:
    sources = json.loads((ROOT / "corpus" / "sources.json").read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    log = {}
    for s in sources:
        if s["format"] == "local_html":
            continue  # synthetic test fixture, lives in corpus/adversarial/
        pdf = RAW / f"{s['doc_id']}.pdf"
        html = RAW / f"{s['doc_id']}.html"
        route = None
        if is_pdf(pdf):
            route = "pdf (already present)"
        else:
            if pdf.exists():
                pdf.unlink()  # remove bot-check page saved under .pdf
            if s["format"] == "pdf":
                if curl(s["download_url"], pdf) and is_pdf(pdf):
                    route = "pdf"
                elif pdf.exists():
                    pdf.unlink()
            if route is None:
                if html.exists() and not is_bot_check(html):
                    route = "html (already present)"
                elif curl(s["page_url"], html) and not is_bot_check(html):
                    route = "html (notification web page)"
            time.sleep(1.0)  # be polite
        out = pdf if route and route.startswith("pdf") else html
        print(f"{s['doc_id']:<32} {route or 'FAILED'}")
        if route:
            log[s["doc_id"]] = {"file": out.name, "route": route, "bytes": out.stat().st_size,
                                "download_date": str(date.today())}
    (ROOT / "corpus" / "download_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
