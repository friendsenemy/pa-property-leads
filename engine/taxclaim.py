"""Greene County Tax Claim Bureau lists -> data/taxclaim.json

The bureau posts each year's Upset Sale listing (scanned PDF, OCR'd) and Judicial
Sale listing (text PDF) as /resources/<id> links on its page; ids change yearly, so
the page is read to find them. Upset = delinquent 2+ years, exposed to the
September upset sale. Judicial = didn't sell at upset; next stop is a court-ordered
sale free of most liens, then the repository.
"""
import io, os, re, subprocess, tempfile
from engine.common import get, save, load, COUNTY_SITE, norm_tax_id

PAGE = COUNTY_SITE + "/department-tax-claim-bureau"


def links():
    h = get(PAGE, county=True).text
    out = {}
    for m in re.finditer(r'href="([^"]*resources/\d+)"[^>]*>(.*?)</a>', h, re.S):
        label = re.sub(r"<[^>]+>|&nbsp;|\s+", " ", m.group(2)).strip()
        y = re.search(r"(20\d\d)", label)
        kind = "upset" if re.search(r"upset sale listing", label, re.I) else "judicial" if re.search(r"judicial\s*sale listing", label, re.I) \
            else "repository" if re.search(r"repository", label, re.I) else None
        if kind:
            url = m.group(1) if m.group(1).startswith("http") else COUNTY_SITE + "/" + m.group(1).lstrip("/")
            out[kind] = {"url": url, "label": label, "year": int(y.group(1)) if y else None}
    return out


def pdf_text(url, ocr=False):
    pdf = get(url, county=True).content
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.pdf")
        open(p, "wb").write(pdf)
        txt = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True).stdout
        if len(txt.strip()) > 200 or not ocr:
            return txt
        subprocess.run(["pdftoppm", "-r", "300", "-png", p, os.path.join(d, "pg")], check=True)
        pages = sorted(x for x in os.listdir(d) if x.startswith("pg"))
        return "\n".join(subprocess.run(["tesseract", os.path.join(d, x), "-", "--psm", "6"], capture_output=True, text=True).stdout for x in pages)


CTRL = r"(\d\d-\d{6})"
TAXID = r"(\d\d-\d\d-\d{3,4}(?:[- ]?[A-Z0-9]{1,3})?|00-00-000)"


def parse_judicial(txt):
    recs = []
    lines = txt.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"\s*" + TAXID + r"\s+" + CTRL + r"\s+(.*)$", l)
        if not m:
            m2 = re.match(r"\s*(\S{1,6})?\s+" + CTRL + r"\s+(.*)$", l)   # trailer accounts: map number wraps onto other lines
            if not m2:
                continue
            m = type("M", (), {"group": lambda self, i, a=("", m2.group(2), m2.group(3)): a[i - 1]})()
        rest = m.group(3)
        bp = re.search(r"(\d{3,4}/\d{3,4})\s+(20\d\d)\s*$", rest)
        acres = re.search(r"\s(\d+\.\d+)\s+\d{3,4}/", rest)
        lu = re.search(r"(Vacant Land|Land & Building|Land &|Mobile Home|Building|Coal|Pittsburgh Coal|Land)", rest, re.I)
        recs.append({"id": norm_tax_id(m.group(1)), "ctrl": m.group(2), "acres": float(acres.group(1)) if acres else None,
                     "deed": bp.group(1) if bp else "", "exposed": int(bp.group(2)) if bp else None,
                     "use": lu.group(1) if lu else "", "raw": re.sub(r"\s{2,}", " | ", rest.strip())[:200]})
    return recs


def parse_upset(txt):
    recs, muni = [], ""
    for l in txt.splitlines():
        s = re.sub(r"^O(\d\d)\s", r"0\1 ", l.strip())
        s = re.sub(r"(\d)\s+\.(\w)", r"\1.\2", s)
        if re.match(r"^[A-Z][A-Z .']+(TOWNSHIP|BOROUGH|TWP|BORO)$", s):
            muni = s.title()
            continue
        m = re.match(r"^(\d{3})\s+(\d{6})\s+(.+?)\s+([0O0-9S]{2}-\S+?)[.,]?\s+\$?\s?([\d,]+\.\d\d)\b", s)
        if not m:
            continue
        mp = m.group(4).upper().replace("O", "0").replace("S", "5", 1) if re.match(r"^[0-9OS]{2}-", m.group(4).upper()) else m.group(4).upper()
        mp = re.sub(r"[.,]", "-", mp).replace("CCT", "CT")
        recs.append({"ctrl": f"{m.group(1)[-2:]}-{m.group(2)}", "id": norm_tax_id(mp), "muni": muni,
                     "owner_desc": m.group(3), "amount": float(m.group(5).replace(",", ""))})
    return recs


def run():
    found = links()
    out = {"source": PAGE, "lists": {}, "rows": []}
    prev = load("taxclaim.json", {}) or {}
    if "judicial" in found:
        recs = parse_judicial(pdf_text(found["judicial"]["url"]))
        out["lists"]["judicial"] = {**found["judicial"], "count": len(recs)}
        out["rows"] += [{**r, "list": "judicial", "year": found["judicial"]["year"]} for r in recs]
    if "upset" in found:
        recs = parse_upset(pdf_text(found["upset"]["url"], ocr=True))
        out["lists"]["upset"] = {**found["upset"], "count": len(recs)}
        out["rows"] += [{**r, "list": "upset", "year": found["upset"]["year"]} for r in recs]
    if not out["rows"] and prev.get("rows"):
        print("nothing parsed; keeping previous file")
        return
    save("taxclaim.json", out)
    print({k: v["count"] for k, v in out["lists"].items()})


if __name__ == "__main__":
    run()
