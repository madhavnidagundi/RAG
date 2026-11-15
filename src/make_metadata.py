"""Write corpus/metadata.csv: one row per document with provenance, status and parsing notes."""
import csv
import json

import config as C

CIRCULAR_FIX = {  # verified against the first lines of each parsed document
    "D02_dlg_guidelines_2023": "RBI/2023-24/41 DOR.CRE.REC.21/21.07.001/2023-24",
    "D06_pa_directions_2025": "RBI/DPSS/2025-26/141 CO.DPSS.POLC.No.S-633/02-14-008/2025-26",
    "D09_emandate_framework_2026": "RBI/DPSS/2026-27/396 CO.DPSS.POLC.No.S56/02.14.003/2026-27",
    "D10_authentication_2025": "RBI/2025-26/79 CO.DPSS.POLC.No.S-668/02-14-015/2025-26",
    "D12_kyc_md_2016": "RBI/DBR/2015-16/18 DBR.AML.BC.No.81/14.01.001/2015-16",
    "D13_aa_directions_2025": "RBI/DoR/2025-26/368 DoR.FIN.REC.No.287/03-10-123/2025-26",
    "D16_nbfc_credit_facilities_2025": "RBI/DOR/2025-26/347 DOR.CRE.REC.No.266/07-01-008/2025-26",
}

MANUAL_NOTES = {
    "D01_dl_guidelines_2022": "RBI site inserts a 'Circular has been repealed' banner above the text (kept: it is useful status evidence). Inline footnote markers. Annex tables.",
    "D02_dlg_guidelines_2023": "Repeal banner inserted by RBI site. Short circular; most content in numbered paras 1-10.",
    "D03_dl_directions_2025": "Withdrawn watermark image only (status not in the text itself). Inline footnote numbers ('guidelines 8 .'). Annex III repeal table.",
    "D05_pa_guidelines_2020": "'Updated as on November 17, 2020' stamp. Two annexes with baseline technology recommendations as long lists.",
    "D06_pa_directions_2025": "'Previous Versions' link text inside body; repeal list in annex table; later amendments (2026) linked but not merged.",
    "D07_emandate_2022": "Very short (1 page): whole circular becomes 1-2 chunks; chunk boundaries matter little.",
    "D08_emandate_2023": "Very short (1 page).",
    "D09_emandate_framework_2026": "Repeal list is a table (serialised row by row). Footnotes at end explain which clauses were added.",
    "D10_authentication_2025": "Annexure tables listing exempted transaction types (serialised row by row).",
    "D11_ppi_md_2021": "Five 'Updated as on' stamps at top; long; limits spread over prose and tables; appendices list repealed circulars.",
    "D12_kyc_md_2016": "Longest document (~76 page-equivalents). Footnote reference numbers merge into headings ('38. 112 Updation / Periodic Updation of KYC'). Many annex tables. Withdrawn watermark only (status not in text).",
    "D13_aa_directions_2025": "Long numbered lists of duties; consent artefact fields as a list.",
    "D14_payments_vision_2025": "Publication with charts/infographics that are images (lost in text extraction); multi-level numbering (4.1.10); acronym table at end.",
    "D15_dpdp_rules_2025": "PDF Gazette: Hindi version (pp.1-23) then English (pp.24-41); Hindi uses a legacy font encoding that extracts as garbled Devanagari, so Hindi pages are dropped. Running header 'THE GAZETTE OF INDIA : EXTRAORDINARY [PART II-SEC. 3(i)]' and page numbers removed. Schedule tables extract with columns interleaved (e.g. retention-period table).",
    "D16_nbfc_credit_facilities_2025": "Large consolidated direction (gold loans, digital lending, etc.); digital lending is only Chapter III, so many chunks are off-topic distractors. 'Previous Versions' link text in body.",
    "X01_injected_note": "SYNTHETIC test fixture (not part of the 15-document corpus): contains an embedded prompt-injection instruction in para 3.",
}


def main():
    sources = json.loads((C.CORPUS / "sources.json").read_text(encoding="utf-8"))
    dl = json.loads((C.CORPUS / "download_log.json").read_text(encoding="utf-8"))
    rows = []
    for s in sources:
        p = C.PARSED / f"{s['doc_id']}.json"
        parsed = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        log = dl.get(s["doc_id"], {})
        rows.append({
            "doc_id": s["doc_id"], "title": s["title"], "issuer": s["issuer"], "doc_type": s["doc_type"],
            "circular_no": CIRCULAR_FIX.get(s["doc_id"], s["circular_no"]),
            "issue_date": s["issue_date"], "effective_date": s["effective_date"],
            "status": s["status"], "superseded_by": s["superseded_by"] or "", "supersedes": ";".join(s["supersedes"]),
            "source_url": s["page_url"], "pdf_url": s["download_url"] if s["format"] == "pdf" else "",
            "format_used": (parsed.get("source_file", "").rsplit(".", 1)[-1] or s["format"]),
            "download_date": log.get("download_date", "2026-11-13"),
            "words": parsed.get("words"), "est_pages": parsed.get("est_pages"), "pdf_pages": parsed.get("n_pages_pdf") or "",
            "n_headings": parsed.get("n_headings"),
            "parsing_issues_auto": " | ".join(parsed.get("issues", [])),
            "parsing_notes": MANUAL_NOTES.get(s["doc_id"], ""),
            "status_notes": s.get("notes", ""),
        })
    out = C.CORPUS / "metadata.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    real = [r for r in rows if not r["doc_id"].startswith("X")]
    print(f"wrote {out} ({len(real)} corpus documents + {len(rows) - len(real)} synthetic test fixture); "
          f"~{sum(r['est_pages'] or 0 for r in real):.0f} page-equivalents")


if __name__ == "__main__":
    main()
