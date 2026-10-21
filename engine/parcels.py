"""Greene County parcel index.

Joins three free county/state layers by tax map number:
  1. County blight survey (2024): owner, mailing address, land use, blight status, polygon -> centroid
  2. County owner snapshot (Nov 2023): deed book/page, acreage
  3. PA DEP statewide parcels: a second owner name to cross-check (may be newer)
Writes data/parcels.json (compact rows) used by every board and the lookup tab.
Severed coal accounts (map 00-00-000) are not in any GIS layer; engine/coal.py adds them.
"""
import sys
from engine.common import ARCGIS, arcgis_all, norm_tax_id, save, absentee

BLIGHT = ARCGIS + "/GRC_Blight_Mapping_06_05_2024_WFL1/FeatureServer/1"
SNAP = ARCGIS + "/GreeneParcels111423/FeatureServer/0"
DEP = "https://gis.dep.pa.gov/depgisprd/rest/services/Parcels/PA_Parcels/MapServer/0"
MIN_PARCELS = 25000


def centroid(geom):
    rings = (geom or {}).get("rings") or []
    pts = [p for r in rings for p in r]
    if not pts:
        return None, None, None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return round(sum(ys) / len(ys), 5), round(sum(xs) / len(xs), 5), [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]


def run():
    print("blight layer…", flush=True)
    rows = {}
    for f in arcgis_all(BLIGHT, geometry=True):
        a = f["attributes"]
        tid = norm_tax_id(a.get("Tax_ID"))
        if not tid:
            continue
        lat, lon, bbox = centroid(f.get("geometry"))
        rows[tid] = {
            "id": tid, "ctrl": a.get("Control") or "", "pid": a.get("REMPID"),
            "owner": (a.get("Owner_1") or "").strip(), "owner2": (a.get("Owner_2") or "").strip(),
            "mail": ", ".join(x.strip() for x in [a.get("Address_1") or "", a.get("Address_2") or ""] if x and x.strip()),
            "city": (a.get("City") or "").strip(), "st": (a.get("State") or "").strip(), "zip": (a.get("ZIP") or "").strip(),
            "lu": a.get("Land_Use") or "", "blight": a.get("Blight_Status") or "", "flood": (a.get("Floodzone") or "").strip(),
            "lat": lat, "lon": lon, "bbox": bbox,
        }
    print(" ", len(rows), flush=True)
    print("2023 snapshot…", flush=True)
    for f in arcgis_all(SNAP):
        a = f["attributes"]
        tid = norm_tax_id(a.get("Tax_ID_Num"))
        r = rows.get(tid)
        if r is None:
            continue
        r["deed"] = (a.get("Deed_Book_") or "").strip()
        r["acres"] = a.get("Acreage")
        if not r.get("ctrl"):
            r["ctrl"] = a.get("Account") or ""
    print("DEP statewide owners…", flush=True)
    try:
        for f in arcgis_all(DEP, where="COUNTY_NAME='GREENE'", fields="PARCEL_ID,ACCOUNT,OWNER_NAME,ACREAGE"):
            a = f["attributes"]
            r = rows.get(norm_tax_id(a.get("PARCEL_ID")))
            if r and a.get("OWNER_NAME") and a["OWNER_NAME"].strip() != r["owner"]:
                r["owner_dep"] = a["OWNER_NAME"].strip()
            if r and not r.get("acres") and a.get("ACREAGE"):
                r["acres"] = a["ACREAGE"]
    except Exception as e:  # noqa: BLE001
        print("  DEP layer skipped:", e)
    for r in rows.values():
        r["abs"] = absentee(r["st"], r["zip"])
    if len(rows) < MIN_PARCELS:
        sys.exit(f"only {len(rows)} parcels; refusing to overwrite")
    save("parcels.json", {"source": "Greene County GIS (blight survey 2024, owner snapshot 2023) + PA DEP parcels",
                          "count": len(rows), "rows": list(rows.values())})
    print("wrote", len(rows))


if __name__ == "__main__":
    run()
