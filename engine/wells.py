"""Oil & gas: every Greene County well, its production, and recent permits -> data/wells.json

  PASDA DEP layer 22   every well location (permit, operator, pad, unconventional, plugged)
  DEP GreenPort        monthly production CSV (statewide, filtered to Greene), last 12 months
  DEP SSRS reports     permits issued (24 months), well pads (911 address)
DEP servers drop connections often: every call retries with a fresh session.
"""
import csv, datetime as dt, io, re, time
import requests
from engine.common import arcgis_all, save, UA

WELLS = "https://mapservices.pasda.psu.edu/server/rest/services/pasda/DEP/MapServer/22"
GP = "https://greenport.pa.gov/ReportExtracts/OG/"
SSRS = "http://cedatareporting.pa.gov/ReportServer?/Public/DEP/OG/SSRS/"


def ms_date(v):
    try:
        return dt.datetime.fromtimestamp(int(v) / 1000, dt.timezone.utc).date().isoformat() if v else ""
    except Exception:
        return ""


def greenport(page, action, fields, tries=12):
    for a in range(tries):
        try:
            s = requests.Session(); s.headers["User-Agent"] = UA
            r = s.get(GP + page, timeout=90)
            tok = re.search(r'__RequestVerificationToken" type="hidden" value="([^"]+)', r.text).group(1)
            p = s.post(GP + action, data=list(fields) + [("__RequestVerificationToken", tok)], headers={"Referer": r.url}, timeout=900)
            if p.status_code == 200 and len(p.content) > 500:
                return p.content.decode("utf-8-sig", "replace"), r.text
        except Exception as e:  # noqa: BLE001
            print("  greenport retry", a, e)
        time.sleep(3)
    raise RuntimeError("GreenPort failed: " + action)


def ssrs(report, params, tries=6):
    for a in range(tries):
        try:
            r = requests.get(SSRS + report, params={"rs:Format": "CSV", **params}, timeout=600, headers={"User-Agent": UA})
            if r.status_code == 200 and len(r.content) > 200:
                return r.content.decode("utf-8-sig", "replace")
        except Exception as e:  # noqa: BLE001
            print("  ssrs retry", a, e)
        time.sleep(5)
    raise RuntimeError("SSRS failed: " + report)


def num(v):
    try:
        return float(str(v).replace(",", "")) if str(v).strip() else 0.0
    except Exception:
        return 0.0


def periods(page_html, n=12):
    """Monthly unconventional reporting periods from the report's dropdown, newest first -> [(id, 'Aug 2026')]."""
    opts = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', page_html)
    out = []
    for v, t in opts:
        m = re.match(r"^([A-Z][a-z]{2} 20\d\d) \(PRODUCTION: Unconventional", t.strip())
        if m:
            out.append((v, m.group(1)))
    return out[:n]


def iso(d):
    """'6/12/2025' or '2025-06-12...' -> '2025-06-12'."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", d or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else (d or "")[:10]


def finalize(wells, got, permits):
    """Per-well totals from the months GreenPort actually returned (got = newest first).
    A failed month is filled by averaging, so gas_12mo is always a 12-month estimate."""
    for w in wells:
        p = w.get("prod") or {}
        vals = [p[m] for m in got if m in p]
        w["gas_12mo"] = round(sum(vals) / len(got) * 12, 1) if got and vals else 0
        w["gas_last"] = next((p[m] for m in got if m in p), 0)
        w["producing"] = w["gas_last"] > 0
    for q in permits:
        q["issued"] = iso(q.get("issued"))


def run():
    print("well locations…", flush=True)
    wells = {}
    for f in arcgis_all(WELLS, where="COUNTY='Greene'"):
        a = f["attributes"]
        api = a.get("PERMIT_NUM")
        if not api:
            continue
        wells[api] = {"api": api, "name": a.get("WELL_NAME") or "", "op": a.get("OPERATOR_N") or "", "pad": a.get("WELL_PAD_N") or "",
                      "unconv": a.get("UNCONVENTI") == "Y", "permit": ms_date(a.get("PERMIT_DAT")), "spud": ms_date(a.get("SPUD_DATE")),
                      "plugged": ms_date(a.get("DATE_PLUGG")), "lat": a.get("LATITUDE"), "lon": a.get("LONGITUDE"),
                      "coal": a.get("COAL_IND") or "", "muni": a.get("MUNICIPALI") or a.get("MUNICIPAL") or ""}
    print(" ", len(wells))

    print("production…", flush=True)
    page = requests.get(GP + "OilGasWellProdReport", headers={"User-Agent": UA}, timeout=90).text
    pers = periods(page, 12)
    prod_meta = []
    for pid, label in pers:
        try:
            text, _ = greenport("OilGasWellProdReport", "ExportOGProdReport", [("RptPeriodsid", pid), ("Operator", ""), ("perNum", "")])
        except Exception as e:  # noqa: BLE001
            print("  skip", label, e); continue
        n = 0
        for r in csv.DictReader(io.StringIO(text)):
            if (r.get("COUNTY") or "").strip().lower() != "greene":
                continue
            api = (r.get("PERMIT_NUM") or "").strip()
            w = wells.setdefault(api, {"api": api, "name": r.get("FARM", "") + " " + r.get("WELL_NO", ""), "op": "",
                                       "lat": num(r.get("LATITUDE_DECIMAL")) or None, "lon": num(r.get("LONGITUDE_DECIMAL")) or None})
            w["operator"] = r.get("CLIENT") or w.get("operator", "")
            w["farm"] = (r.get("FARM") or "").strip()
            w["status"] = r.get("WELL_STATUS") or ""
            w["muni"] = r.get("MUNIC") or w.get("muni", "")
            w.setdefault("prod", {})[label] = round(num(r.get("GAS_QUANTITY")) + 0, 1)
            if num(r.get("OIL_QUANTITY")) or num(r.get("CONDENSATE_QUANTITY")):
                w.setdefault("liquids", {})[label] = round(num(r.get("OIL_QUANTITY")) + num(r.get("CONDENSATE_QUANTITY")), 1)
            n += 1
        prod_meta.append({"period": label, "id": pid, "greene_rows": n})
        print(" ", label, n, flush=True)

    print("permits…", flush=True)
    today = dt.date.today()
    permits = []
    try:
        text = ssrs("Permits_Issued_Detail", {"P_START_DATE": (today - dt.timedelta(days=730)).strftime("%m/%d/%Y"),
                                             "P_END_DATE": today.strftime("%m/%d/%Y")})
        for r in csv.DictReader(io.StringIO(text)):
            if (r.get("COUNTY") or "").strip().lower() == "greene":
                permits.append({"api": r.get("WELL_API"), "issued": r.get("PERMIT_ISSUED_DATE"), "op": r.get("OPERATOR"),
                                "type": r.get("APPLICATION_TYPE"), "unconv": r.get("UNCONVENTIONAL"), "farm": r.get("FARM_NAME"),
                                "muni": r.get("MUNICIPALITY"), "lat": num(r.get("LATITUDE_DECIMAL")), "lon": num(r.get("LONGITUDE_DECIMAL")),
                                "spud": r.get("SPUD_DATE")})
    except Exception as e:  # noqa: BLE001
        print("  permits skipped", e)
    pads = []
    try:
        text = ssrs("Well_Pads", {})
        for r in csv.DictReader(io.StringIO(text)):
            if (r.get("COUNTY") or r.get("COUNTY_NAME") or "").strip().lower() == "greene":
                pads.append({k.lower(): v for k, v in r.items() if v})
    except Exception as e:  # noqa: BLE001
        print("  pads skipped", e)

    finalize(wells.values(), [m["period"] for m in prod_meta], permits)
    if len(wells) < 5000 or len(prod_meta) < 3:
        raise SystemExit(f"too little data (wells {len(wells)}, months {len(prod_meta)}) - keeping the last wells.json")
    save("wells.json", {"generated": today.isoformat(), "periods": [m["period"] for m in prod_meta], "prod_meta": prod_meta,
                        "count": len(wells), "rows": list(wells.values()), "permits": permits, "pads": pads})
    print("wells", len(wells), "producing", sum(w["producing"] for w in wells.values()), "permits", len(permits), "pads", len(pads))


if __name__ == "__main__":
    run()
