"""Small table helpers so every script prints and writes tables the same way."""


def _cells(rows):
    return [["" if x is None else str(x) for x in r] for r in rows]


def text_table(headers, rows, right=()):
    """Boxed plain-text table for the terminal. `right` = indexes of right-aligned (numeric) columns."""
    headers, rows = [str(h) for h in headers], _cells(rows)
    widths = [max(len(x) for x in col) for col in zip(headers, *rows)] if rows else [len(h) for h in headers]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(r):
        return "| " + " | ".join(x.rjust(w) if i in right else x.ljust(w) for i, (x, w) in enumerate(zip(r, widths))) + " |"
    return "\n".join([line, fmt(headers), line] + [fmt(r) for r in rows] + [line])


def md_table(headers, rows, right=()):
    """GitHub-flavoured Markdown table with padded columns, so it is also readable as plain text."""
    esc = lambda x: x.replace("|", "\\|").replace("\n", " ")
    headers, rows = [esc(str(h)) for h in headers], [[esc(x) for x in r] for r in _cells(rows)]
    widths = [max(3, *(len(x) for x in col)) for col in zip(headers, *rows)] if rows else [max(3, len(h)) for h in headers]

    def fmt(r):
        return "| " + " | ".join(x.rjust(w) if i in right else x.ljust(w) for i, (x, w) in enumerate(zip(r, widths))) + " |"
    sep = "| " + " | ".join("-" * (w - 1) + ":" if i in right else "-" * w for i, w in enumerate(widths)) + " |"
    return "\n".join([fmt(headers), sep] + [fmt(r) for r in rows])
