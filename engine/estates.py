"""Estate notices from The Greene Reports (county legal journal) -> data/estates.json

palegalads.org search (county=33) lists each weekly issue; each issue page links its
PDF. Notices: decedent (CAPS), "Late of <place>", Executor/Administrator with mailing
address, Attorney. Keeps a running history (first-published date per decedent).
"""
import datetime as dt, os, re, subprocess, tempfile
from engine.common import get, post, save, load

SEARCH = "https://www.palegalads.org/search"
ROLE = r"(Co-Executors?|Executors?|Executrix|Co-Executrix|Administrators?|Administratrix|Co-Administrators?|Personal Representatives?|Administrator C\.?T\.?A\.?|Administrator D\.?B\.?N\.?)"


def issues(months=3):
    """One query per month (the search shows ~10 results per page)."""
    today = dt.date.today()
    y, m = today.year, today.month
    found = set()
    for _ in range(months):
        h = post(SEARCH, data={"county": "33", "keywords": "estate", "post_month": m, "post_year": y,
                               "post_month2": m, "post_year2": y}).text
        found |= set(re.findall(r'href="(https://www\.palegalads\.org/legal-ads/greene-county/[^"?]+)', h))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return sorted(found)


def issue_pdf(url):
    h = get(url).text
    m = re.search(r'(journals/pdf/[\w\-]+\.pdf)', h)
    return "https://www.palegalads.org/" + m.group(1) if m else None


def pdf_date(pdf_url):
    m = re.search(r"_(\d{1,2})_(\d{1,2})_(\d\d)\.pdf", pdf_url)
    return dt.date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat() if m else ""


def parse(txt):
    """Reading-order text (pdftotext without -layout). Returns notices."""
    s = txt.replace("’", "'")
    i = s.find("ESTATE NOTICES")
    if i < 0:
        return []
    j = s.find("FIRST AND FINAL", i)
    block = s[i:j if j > 0 else i + 60000]
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    out, cur = [], None
    for k, l in enumerate(lines):
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if re.match(r"^[A-Z][A-Z'\-. ]+,\s+[A-Z][A-Z .'\-/,()0-9]*$", l) and len(l) < 120 and not l.startswith("NOTICE"):
            if cur:
                out.append(cur)
            cur = {"name": l.rstrip(","), "late_of": "", "reps": [], "attorney": ""}
            continue
        if cur is None:
            continue
        if cur["name"].endswith(("A/K/A", "A/K/A PATRICIA")) or (re.match(r"^[A-Z .'/]+$", l) and not cur["late_of"] and len(l) < 60 and "Late of" not in l):
            cur["name"] += " " + l
            continue
        m = re.match(r"^Late of (.+?)(,\s*Greene County.*)?$", l)
        if m:
            cur["late_of"] = m.group(1).strip()
            continue
        m = re.match(r"^" + ROLE + r":\s*(.+)$", l, re.I)
        if m:
            rest = m.group(2)
            if re.search(r"\b(PA|[A-Z]{2})$", rest) and re.match(r"^\d{5}", nxt):
                rest += " " + nxt
            cur["reps"].append({"role": m.group(1), "text": rest.strip()})
            continue
        m = re.match(r"^Attorneys?:\s*(.+)$", l)
        if m:
            cur["attorney"] = m.group(1).strip()
            continue
        if cur["reps"] and not cur["attorney"] and not re.match(r"^(Attorney|Late of)", l) and len(l) < 80 and re.search(r"\d", l):
            cur["reps"][-1]["text"] += " " + l   # wrapped address line
    if cur:
        out.append(cur)
    for n in out:
        n["name"] = re.sub(r"\s+", " ", n["name"]).strip(" ,")
        n["surname"] = n["name"].split(",")[0].strip()
        rest = n["name"].split(",", 1)[1] if "," in n["name"] else ""
        n["given"] = re.split(r"\bA/K/A\b", rest)[0].strip(" ,.")
    return [n for n in out if n["late_of"] or n["reps"]]


def run(months=3):
    prev = load("estates.json", {"rows": []}) or {"rows": []}
    have = {(r["name"], r.get("first_pub")): r for r in prev["rows"]}
    names = {r["name"] for r in prev["rows"]}
    seen_pdfs = set(prev.get("pdfs", []))
    new = 0
    for iu in issues(months):
        pdf = issue_pdf(iu)
        if not pdf or pdf in seen_pdfs:
            continue
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.pdf")
            open(p, "wb").write(get(pdf).content)
            txt = subprocess.run(["pdftotext", p, "-"], capture_output=True, text=True).stdout
        for n in parse(txt):
            if n["name"] in names:
                continue
            names.add(n["name"])
            n.update({"first_pub": pdf_date(pdf), "pdf": pdf})
            prev["rows"].append(n)
            new += 1
        seen_pdfs.add(pdf)
    prev["pdfs"] = sorted(seen_pdfs)
    prev["rows"].sort(key=lambda r: r.get("first_pub", ""), reverse=True)
    prev["source"] = "The Greene Reports via palegalads.org"
    save("estates.json", prev)
    print("new notices:", new, "total:", len(prev["rows"]))


if __name__ == "__main__":
    import sys
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
