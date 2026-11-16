"""Check every Markdown table in the project: same number of columns on every row,
a valid separator row, and a blank line before the table.   python scripts/check_md_tables.py"""
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "WRITEUP.md"] + sorted(glob.glob("results/*.md", root_dir=ROOT))
SPLIT = re.compile(r"(?<!\\)\|")
SEP = re.compile(r"\|?[\s:\-|]+\|?")

total_bad = 0
for f in FILES:
    lines = (ROOT / f).read_text(encoding="utf-8").split("\n")
    tables = bad = i = 0
    in_code = False
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            in_code = not in_code
        if not in_code and lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            tables += 1
            cols = {len(SPLIT.split(l.strip().strip("|"))) for l in block}
            sep_ok = len(block) > 1 and SEP.fullmatch(block[1].strip()) is not None
            blank_before = i == 0 or lines[i - 1].strip() == ""
            if len(cols) > 1 or not sep_ok or not blank_before:
                bad += 1
                print(f"  BAD {f}:{i + 1}  column counts={sorted(cols)}  separator ok={sep_ok}  blank line before={blank_before}")
            i = j
        else:
            i += 1
    total_bad += bad
    print(f"{f}: {tables} tables, {bad} with problems")
raise SystemExit(1 if total_bad else 0)
