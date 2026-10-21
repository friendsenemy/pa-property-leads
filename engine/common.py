"""Shared helpers: HTTP with polite pauses, the county TLS root, name/address parsing."""
import json, os, re, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache")
UA = "pa-property-leads/1.0 (+https://github.com/friendsenemy/pa-property-leads)"
ARCGIS = "https://services7.arcgis.com/0JhPFgxDlwicqVHq/arcgis/rest/services"
COUNTY_SITE = "https://www.greenecountypa.gov"
# greenecountypa.gov chains to Starfield TLS Root CA - R1, missing from some trust stores.
STARFIELD = os.path.join(ROOT, "certs", "starfield-r1.pem")

_s = requests.Session()
_s.headers["User-Agent"] = UA


def county_verify():
    """certifi bundle + the Starfield root, written once to .cache."""
    import certifi
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "ca-bundle.pem")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(open(certifi.where()).read() + "\n" + open(STARFIELD).read())
    return p


def get(url, params=None, county=False, tries=4, pause=0.5, **kw):
    for i in range(tries):
        try:
            r = _s.get(url, params=params, timeout=90, verify=county_verify() if county else True, **kw)
            r.raise_for_status()
            time.sleep(pause)
            return r
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def post(url, data=None, county=False, tries=4, pause=0.5, **kw):
    for i in range(tries):
        try:
            r = _s.post(url, data=data, timeout=90, verify=county_verify() if county else True, **kw)
            r.raise_for_status()
            time.sleep(pause)
            return r
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def arcgis_all(layer_url, where="1=1", fields="*", geometry=False, page=None, extra=None):
    """Every feature of an ArcGIS layer, paged by objectid offset."""
    meta = get(layer_url, {"f": "json"}).json()
    page = page or int(meta.get("maxRecordCount") or 1000)
    out, off = [], 0
    while True:
        p = {"where": where, "outFields": fields, "f": "json", "resultOffset": off, "resultRecordCount": page,
             "returnGeometry": "true" if geometry else "false", "orderByFields": meta.get("objectIdField") or "OBJECTID"}
        if geometry:
            p.update({"outSR": 4326, "geometryPrecision": 5})
        if extra:
            p.update(extra)
        d = get(layer_url + "/query", p).json()
        feats = d.get("features") or []
        out.extend(feats)
        if len(feats) < page and not d.get("exceededTransferLimit"):
            break
        off += len(feats)
        if not feats:
            break
    return out


def norm_tax_id(s):
    """'06-05-124', '06/05/124', '06/05/124 ' -> '06-05-124' (upper, no spaces)."""
    if not s:
        return ""
    return re.sub(r"[\s/]+", "-", str(s).strip().upper()).strip("-")


def save(name, obj):
    path = os.path.join(DATA, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    return path


def load(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    return json.load(open(path))


IN_COUNTY_ZIPS = {"15310", "15315", "15316", "15320", "15322", "15325", "15327", "15334", "15337", "15338",
                  "15341", "15344", "15346", "15349", "15351", "15352", "15353", "15357", "15359", "15362",
                  "15364", "15370", "15380"}


def absentee(state, zipc):
    st = (state or "").strip().upper()
    z = (zipc or "").strip()[:5]
    if st and st != "PA":
        return "out_of_state"
    if z and z not in IN_COUNTY_ZIPS:
        return "out_of_county"
    return ""


ESTATE_RE = re.compile(r"(?<!REAL )\b(ESTATE|ESTATE OF|EST OF|HEIRS?|DECD|DECEASED|EXR|EXECUT|ADMR|ADMINISTRAT|C/O .*ESTATE|UNKNOWN HEIRS)\b")
LIFE_RE = re.compile(r"\b(LIFE ESTATE|L/E|LIFE TENANT)\b")
COAL_RE = re.compile(r"\b(COAL|MINING|CONSOL|CONRHEIN|NINEVEH|CUMBERLAND COAL|EMERALD COAL|RIVER HILL COAL|ALPHA|FOUNDATION COAL)\b")
GAS_RE = re.compile(r"\b(EQT|CNX|RANGE RESOURCES|CHESAPEAKE|ANTERO|SOUTHWESTERN|SWN|EQUITRANS|DOMINION|COLUMBIA GAS|PEOPLES|ENERGY|PETROLEUM|OIL|GAS|MINERALS?|ROYALT)\b")
ENTITY_RE = re.compile(r"\b(LLC|L L C|INC|CORP|CORPORATION|COMPANY|CO|LP|L P|LTD|TRUST|TR|TRUSTEE|PARTNERSHIP|ASSOC|BANK|CHURCH|TOWNSHIP|BOROUGH|COUNTY|COMMONWEALTH|AUTHORITY|SCHOOL|CEMETERY)\b")
