"""Coal: which parcels sit over mined-out coal, active underground mine permits, or
longwall panels (PA DEP District Mining Operations layers) -> data/coal.json

Parcels are tested by centroid. Mined-out ground matters for two reasons: subsidence
risk for any building, and the coal is gone, so the remaining value under the parcel
is gas (and the surface).
"""
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from engine.common import arcgis_all, save, load

BASE = "https://gis.dep.pa.gov/depgisprd/rest/services/DistrictMiningOperations/{}/MapServer/0"
BOX = {"geometry": "-80.53,39.71,-79.90,40.01", "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
LAYERS = {
    "mined_out": ("DMO_MinedOutAreaCoalUnderground", ["OPERATION", "COAL_SEAM", "LASTMINED"]),
    "active_mine": ("DMO_MiningPermitsBituminousUndergroundActive", ["MINE_NAME", "OPERATOR", "PERMIT", "STATUS", "SEAM"]),
    "longwall": ("DMO_LongwallMiningPanels", ["MINE_NAME", "PANEL_ID", "YEAR_COMPLETED", "PANEL_STATUS"]),
}


def esri_to_geojson(g):
    if not g:
        return None
    if "rings" in g:
        return {"type": "Polygon", "coordinates": g["rings"]}
    return None


def run():
    parcels = load("parcels.json")["rows"]
    pts = [(r["id"], Point(r["lon"], r["lat"])) for r in parcels if r.get("lat")]
    out = {}
    summary = {}
    for key, (svc, keep) in LAYERS.items():
        feats = arcgis_all(BASE.format(svc), geometry=True, extra=BOX)
        geoms, attrs = [], []
        for f in feats:
            gj = esri_to_geojson(f.get("geometry"))
            if not gj:
                continue
            try:
                g = shape(gj).buffer(0)
            except Exception:
                continue
            geoms.append(g); attrs.append({k.lower(): v for k, v in f["attributes"].items() if any(x.lower() in k.lower() for x in keep)})
        tree = STRtree(geoms)
        hits = 0
        for pid, p in pts:
            for i in tree.query(p):
                if geoms[i].contains(p):
                    out.setdefault(pid, {})[key] = attrs[i]
                    hits += 1
                    break
        summary[key] = {"features": len(geoms), "parcels": hits}
        print(key, summary[key], flush=True)
    save("coal.json", {"summary": summary, "parcels": out})


if __name__ == "__main__":
    run()
