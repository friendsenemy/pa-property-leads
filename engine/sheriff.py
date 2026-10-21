"""Greene County sheriff sales (Teleosoft CountySuite) -> data/sheriff.json

SalesForCategory (id=8 Real Estate) lists sale dates; SaleListingDetails returns an
HTML table per date. Keeps every upcoming sale plus the last 120 days of past ones.
"""
import datetime as dt, re
from html import unescape
from engine.common import get, post, save, COUNTY_SITE, norm_tax_id

BASE = COUNTY_SITE + "/SaleListing/PropertySales"


def cells(tr):
    return [re.sub(r"\s+", " ", unescape(re.sub(r"<br\s*/?>", " | ", c) if False else re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def parse_listing(html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    if not rows:
        return []
    head = [h.lower() for h in cells(rows[0])]
    out = []
    for tr in rows[1:]:
        c = cells(tr)
        if len(c) < 3:
            continue
        rec = dict(zip(head, c)) if len(head) == len(c) else {"cols": c}
        poster = re.search(r'href="([^"]*Poster/\d+[^"]*)"', tr)
        if poster:
            rec["handbill"] = COUNTY_SITE + poster.group(1) if poster.group(1).startswith("/") else poster.group(1)
        out.append(rec)
    return out


def norm(rec, sale):
    parts = rec.get("case participants", "")
    pl, _, df = parts.partition(" vs. ")
    addr = rec.get("property address", "")
    upi = (re.search(r"UPI#?:?\s*([\w/ .-]+)", addr) or [None, ""])[1].strip(" /")
    muni = (re.search(r"([A-Z][\w ]+ (?:Township|Borough))", addr) or [None, ""])[1]
    amt = re.sub(r"[^\d.]", "", rec.get("judgment", ""))
    return {"sale_id": sale["SaleId"], "sale_date": sale["date"], "case": rec.get("case no.", ""),
            "plaintiff": pl.strip(), "defendant": df.strip(), "attorney": rec.get("attorney", ""),
            "address": re.sub(r"\s*UPI#?:.*$", "", addr).strip(), "muni": muni, "id": norm_tax_id(upi), "upi": upi,
            "judgment": float(amt) if amt else None, "status": rec.get("status", ""), "handbill": rec.get("handbill", ""),
            "estate": bool(re.search(r"ESTATE|DECEASED|HEIRS|ADMINISTRAT|EXECUT", df.upper()))}


def run():
    sales = post(BASE + "/SalesForCategory", data={"id": 8}, county=True).json()
    today = dt.date.today()
    keep = []
    for s in sales:
        m = re.search(r"/Date\((\d+)", str(s.get("SaleDate")))
        d = dt.datetime.fromtimestamp(int(m.group(1)) / 1000, dt.timezone.utc).date() if m else None
        if d is None:
            try:
                d = dt.datetime.fromisoformat(str(s.get("SaleDate"))[:10]).date()
            except Exception:
                continue
        if (today - d).days <= 120 and (d - today).days <= 400:
            keep.append({**s, "date": d.isoformat()})
    out = []
    for s in sorted(keep, key=lambda x: x["date"]):
        h = get(BASE + "/SaleListingDetails", {"activeOnly": "false", "crierSort": "false", "id": s["SaleId"],
                                               "searchAllSales": "false", "searchText": ""}, county=True).text
        out += [norm(r, s) for r in parse_listing(h)]
    save("sheriff.json", {"source": BASE, "count": len(out), "rows": out})
    print(len(keep), "sale dates,", len(out), "listings")


if __name__ == "__main__":
    run()
