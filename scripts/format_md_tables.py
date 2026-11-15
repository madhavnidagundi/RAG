"""Re-align every Markdown table in the given files: padded columns, numeric columns right-aligned.
Cell text is not changed.   python scripts/format_md_tables.py RESEARCH.md WRITEUP.md"""
import re
import sys
from pathlib import Path

SPLIT = re.compile(r"(?<!\\)\|")
NUMERIC = re.compile(r"[~≈]?[-–$₹]?\d[\d.,]*\s*(%|s|ms|/\d+)?(\s*\([\d.]+\))?|[-–]|")


def cells(line):
    return [c.strip() for c in SPLIT.split(line.strip().strip("|"))]


def format_table(block):
    head, rows = cells(block[0]), [cells(l) for l in block[2:]]
    n = len(head)
    rows = [(r + [""] * n)[:n] for r in rows]
    right = [bool(rows) and all(NUMERIC.fullmatch(r[i].strip("*")) for r in rows) and any(r[i] not in ("", "-", "–") for r in rows)
             for i in range(n)]
    widths = [max(3, len(head[i]), *(len(r[i]) for r in rows)) for i in range(n)]
    fmt = lambda r: "| " + " | ".join(r[i].rjust(widths[i]) if right[i] else r[i].ljust(widths[i]) for i in range(n)) + " |"
    sep = "| " + " | ".join(("-" * (widths[i] - 1) + ":") if right[i] else "-" * widths[i] for i in range(n)) + " |"
    return [fmt(head), sep] + [fmt(r) for r in rows]


def format_file(path):
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    out, i, in_code, n_tables = [], 0, False, 0
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            in_code = not in_code
        if not in_code and lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            if out and out[-1].strip():
                out.append("")  # a table needs a blank line before it
            out += format_table(lines[i:j])
            n_tables += 1
            i = j
        else:
            out.append(lines[i])
            i += 1
    Path(path).write_text("\n".join(out), encoding="utf-8", newline="")
    print(f"{path}: {n_tables} tables formatted")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        format_file(p)
