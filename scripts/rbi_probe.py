"""Print title/date/status and main PDF link for RBI notification Ids (helper for corpus building)."""
import re, sys, html, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
for i in sys.argv[1:]:
    page = get(f"https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id={i}&Mode=0")
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    m = re.search(r"tableheader[^>]*>(.*?)</", page, re.S)
    title = re.sub(r"<[^>]+>|\s+", " ", m.group(1)).strip() if m else "?"
    date = re.search(r"Date\s*:\s*([A-Za-z]{3} \d{1,2}, \d{4})", text)
    pdfs = [p for p in re.findall(r"https?://rbidocs[^\"']+\.pdf", page, re.I) if "Accessib" not in p and "Utkarsh" not in p]
    rep = re.search(r"(The Circular has been repealed[^.]*\.[^.]*\.|repealed[^.]{0,150})", text)
    print(f"{i} | {date.group(1) if date else '?'} | {title[:110]} | {pdfs[-1] if pdfs else '-'} | {rep.group(1)[:160] if rep else ''}")
