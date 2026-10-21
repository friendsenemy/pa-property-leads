"""Combine every source into the dashboard's boards -> data/board.json + data/lookup.json

One row per parcel that has at least one signal. Signals are additive points; hard
county records (tax claim, sheriff, estate notice, blight survey) outweigh soft hints
(absentee, old deed). Gas/coal context is attached to every row and drives the
Minerals board.
"""
import datetime as dt, math, re
from collections import defaultdict
from engine.common import load, save, ESTATE_RE, LIFE_RE, COAL_RE, GAS_RE, ENTITY_RE, norm_tax_id

MI = 1609.34
NEAR_MI, UNIT_MI = 0.75, 1.5          # producing well "near" / permit "in the area"
PTS = {"estate_notice": 40, "sheriff": 35, "judicial": 35, "obit": 25, "owner_estate": 30, "upset": 25,
       "unsound": 30, "major_repair": 20, "life_estate": 10, "out_of_state": 15, "out_of_county": 8, "old_deed": 10,
       "gas_near": 15, "pad_on_parcel": 10, "new_permit_near": 10}
LABEL = {"estate_notice": "⚰ Estate opened", "sheriff": "🔨 Sheriff sale", "judicial": "🏛 Judicial tax sale list",
         "upset": "💲 Upset tax sale list", "obit": "📰 Obituary match", "owner_estate": "⚰ Owner is an estate/heirs",
         "unsound": "🏚 Blight: unsound", "major_repair": "🏚 Blight: major repair", "life_estate": "Life estate",
         "out_of_state": "✈ Owner out of state", "out_of_county": "Owner out of county", "old_deed": "📜 Old deed",
         "gas_near": "🔥 Producing gas wells nearby", "pad_on_parcel": "🛢 Well pad on parcel", "new_permit_near": "🆕 New permits nearby"}
HARD = {"estate_notice", "sheriff", "judicial", "upset", "obit", "owner_estate", "unsound", "major_repair"}


def hav(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


class Grid:
    def __init__(self, pts, cell=0.02):
        self.cell, self.g = cell, defaultdict(list)
        for p in pts:
            if p.get("lat") and p.get("lon"):
                self.g[(int(p["lat"] / cell), int(p["lon"] / cell))].append(p)

    def near(self, lat, lon, meters):
        r = int(meters / 111000 / self.cell) + 1
        ci, cj = int(lat / self.cell), int(lon / self.cell)
        for i in range(ci - r, ci + r + 1):
            for j in range(cj - r, cj + r + 1):
                for p in self.g.get((i, j), ()):
                    d = hav(lat, lon, p["lat"], p["lon"])
                    if d <= meters:
                        yield p, d


def owner_tokens(owner):
    o = re.sub(r"\b(ET UX|ET VIR|ET AL|ET CON|JR|SR|II|III|EST|ESTATE|HEIRS)\b", " ", (owner or "").upper())
    t = [x for x in re.split(r"[^A-Z]+", o) if x]
    return t


def name_key(surname, given):
    g = [x for x in re.split(r"[^A-Z]+", (given or "").upper()) if len(x) > 1]
    return (surname.upper().strip(), g[0] if g else "")


def deed_book(deed):
    m = re.match(r"\s*(\d{1,4})\s*/", deed or "")
    return int(m.group(1)) if m else None


def run():
    parcels = load("parcels.json")["rows"]
    by_id = {r["id"]: r for r in parcels}
    by_ctrl = {r["ctrl"]: r for r in parcels if r.get("ctrl")}
    wells = load("wells.json", {"rows": [], "permits": [], "periods": []})
    coal = (load("coal.json", {}) or {}).get("parcels", {})
    tax = load("taxclaim.json", {"rows": []})["rows"]
    sheriff = load("sheriff.json", {"rows": []})["rows"]
    estates = load("estates.json", {"rows": []})["rows"]
    obits = load("obits.json", {"rows": []})["rows"]
    today = dt.date.today()

    unconv = [w for w in wells["rows"] if w.get("lat") and w.get("lon") and (w.get("unconv") or w.get("gas_12mo"))]
    wgrid = Grid(unconv)
    since = (today - dt.timedelta(days=730)).isoformat()
    permits = [p for p in wells.get("permits", []) if p.get("lat")]
    pgrid = Grid(permits)

    sig = defaultdict(dict)        # parcel id -> {signal: detail}
    extra = defaultdict(dict)

    # owner text, blight, absentee, deed age
    for r in parcels:
        o = (r.get("owner") or "") + " " + (r.get("owner2") or "")
        if ESTATE_RE.search(o.upper()) and not ENTITY_RE.search(o.upper()):
            sig[r["id"]]["owner_estate"] = r["owner"]
        if LIFE_RE.search(o.upper()):
            sig[r["id"]]["life_estate"] = r["owner"]
        if r.get("blight") == "Unsound":
            sig[r["id"]]["unsound"] = "County blight survey 2024"
        elif r.get("blight") == "Major Repair":
            sig[r["id"]]["major_repair"] = "County blight survey 2024"
        bk = deed_book(r.get("deed"))
        if bk is not None and 0 < bk <= 150 and not ENTITY_RE.search(o.upper()):
            sig[r["id"]]["old_deed"] = f"Deed book {r['deed']}"

    # tax claim
    for t in tax:
        r = by_id.get(t.get("id")) or by_ctrl.get(t.get("ctrl"))
        key = r["id"] if r else ("CTRL:" + t["ctrl"])
        d = f"{t['list'].title()} list {t.get('year')}" + (f" · ${t['amount']:,.2f}" if t.get("amount") else "") + (f" · exposed {t['exposed']}" if t.get("exposed") else "")
        sig[key][t["list"]] = d
        extra[key]["tax"] = t
        if not r:
            extra[key]["orphan"] = {"id": t.get("id") or "", "ctrl": t["ctrl"], "owner": t.get("owner_desc") or t.get("raw", "")[:60], "coal_account": (t.get("id") or "") == "00-00-000"}

    # sheriff
    for s in sheriff:
        if s.get("sale_date", "") < today.isoformat() and not re.search(r"Postponed", s.get("status", ""), re.I):
            continue
        key = s["id"] if s.get("id") in by_id else ("SHERIFF:" + s["case"])
        sig[key]["sheriff"] = f"{s['sale_date']} · {s['plaintiff'][:40]} · ${s['judgment'] or 0:,.0f} · {s['status']}"
        extra[key]["sheriff"] = s
        if key not in by_id:
            extra[key]["orphan"] = {"id": s.get("id"), "owner": s["defendant"], "address": s["address"]}

    # estate notices and obituaries -> owners (surname + first given name)
    owners = defaultdict(list)
    for r in parcels:
        for who in (r.get("owner"), r.get("owner2")):
            t = owner_tokens(who)
            if len(t) >= 2:
                owners[(t[0], t[1])].append(r)
    for e in estates:
        k = name_key(e.get("surname", ""), e.get("given", ""))
        for r in owners.get(k, [])[:6]:
            sig[r["id"]]["estate_notice"] = f"{e['name']} · late of {e.get('late_of','')} · published {e.get('first_pub')}"
            extra[r["id"]]["estate"] = e
    for o in obits:
        parts = [x for x in re.split(r"[^A-Za-z]+", o["name"]) if len(x) > 1]
        if len(parts) >= 2:
            k = (parts[-1].upper(), parts[0].upper())
            for r in owners.get(k, [])[:4]:
                sig[r["id"]]["obit"] = f"{o['name']} · {o['pub']}"
                extra[r["id"]]["obit"] = o

    # gas + coal context for every parcel that has a centroid
    gas = {}
    for r in parcels:
        if not r.get("lat"):
            continue
        near = sorted(wgrid.near(r["lat"], r["lon"], NEAR_MI * MI), key=lambda x: x[1])
        prod = [(w, d) for w, d in near if w.get("gas_last", 0) > 0]
        b = r.get("bbox")
        on = [w for w, d in near if b and b[0] <= w["lon"] <= b[2] and b[1] <= w["lat"] <= b[3]]
        perm = [p for p, d in pgrid.near(r["lat"], r["lon"], UNIT_MI * MI) if (p.get("issued") or "")[:10] >= since]
        if prod:
            sig[r["id"]]["gas_near"] = f"{len(prod)} producing wells within {NEAR_MI} mi · nearest {prod[0][1]/MI:.2f} mi ({prod[0][0].get('operator') or prod[0][0].get('op')})"
        if on:
            sig[r["id"]]["pad_on_parcel"] = f"{len(on)} wells on this parcel ({on[0].get('pad') or on[0].get('name')})"
        newp = [p for p in perm if p.get("type") in ("NEW", None, "")]
        if newp:
            sig[r["id"]]["new_permit_near"] = f"{len(newp)} new permits within {UNIT_MI} mi since {since[:4]}"
        if prod or on or newp:
            gas[r["id"]] = {
                "producing_near": len(prod), "wells_near": len(near), "on_parcel": len(on),
                "gas_12mo_near": round(sum(w.get("gas_12mo", 0) for w, _ in prod)),
                "operators": sorted({(w.get("operator") or w.get("op") or "").strip() for w, _ in prod if (w.get("operator") or w.get("op"))})[:4],
                "nearest": [{"api": w["api"], "name": (w.get("name") or w.get("farm") or "").strip(), "op": w.get("operator") or w.get("op"),
                             "mi": round(d / MI, 2), "gas_12mo": w.get("gas_12mo", 0), "last": w.get("gas_last", 0), "spud": w.get("spud", "")}
                            for w, d in prod[:5]],
                "new_permits": [{"api": p["api"], "op": p["op"], "issued": p["issued"], "farm": p["farm"]} for p in newp[:5]],
            }

    rows = []
    for key, s in sig.items():
        r = by_id.get(key)
        if not s or (set(s) <= {"gas_near", "new_permit_near", "pad_on_parcel", "old_deed", "life_estate"} and not r):
            continue
        base = dict(r) if r else {"id": key, **(extra[key].get("orphan") or {})}
        base.pop("bbox", None)
        if r and r.get("abs"):
            s[r["abs"]] = f"Mail to {r.get('city','')}, {r.get('st','')}"
        score = sum(PTS.get(k, 0) for k in s)
        hard = [k for k in s if k in HARD]
        base.update({"signals": {k: s[k] for k in sorted(s, key=lambda k: -PTS.get(k, 0))}, "score": score, "hard": len(hard),
                     "gas": gas.get(key), "coal": coal.get(key)})
        base.update({k: v for k, v in extra[key].items() if k != "orphan"})
        rows.append(base)

    # a parcel is a "lead" if it has a hard signal, or gas plus a motivation signal
    def is_lead(x):
        s = x["signals"]
        motiv = set(s) & (HARD | {"out_of_state", "out_of_county", "old_deed", "life_estate"})
        return x["hard"] > 0 or (x.get("gas") and motiv)
    leads = [x for x in rows if is_lead(x)]
    leads.sort(key=lambda x: (-x["score"], -(x.get("gas") or {}).get("producing_near", 0)))
    minerals = [x for x in rows if x.get("gas") and (set(x["signals"]) & (HARD | {"out_of_state", "out_of_county", "old_deed", "life_estate"}) or (x.get("acres") or 0) >= 20)]
    minerals.sort(key=lambda x: (-(x["hard"] > 0), -(x["gas"].get("producing_near", 0) > 0), -x["score"], -(x.get("acres") or 0)))

    # Light rows for the boards; well lists, permits, coal and listing text go to details.json
    # (fetched once, the first time a card is opened) so the page loads fast on a phone.
    keep = {x["id"]: x for x in leads + minerals[:3000]}
    details, light = {}, []
    for x in keep.values():
        d = {}
        g = x.get("gas")
        if g:
            d["nearest"], d["new_permits"] = g.pop("nearest"), g.pop("new_permits")
        if x.get("coal"):
            d["coal"] = x.pop("coal")
            x["coal"] = 1
        for k in ("tax", "sheriff", "estate", "obit"):
            if x.get(k):
                d[k] = x[k]
        if x.get("tax"):
            x["tax"] = {k: x["tax"].get(k) for k in ("list", "id", "ctrl", "amount", "acres", "muni", "owner_desc")}
        if x.get("estate"):
            x["estate_name"] = x["estate"]["name"]
        if x.get("sheriff"):
            x["sale_date"] = x["sheriff"].get("sale_date")
        for k in ("estate", "obit", "sheriff", "flood", "zip", "bbox"):
            x.pop(k, None)
        if not x.get("abs"):
            x.pop("abs", None)
        details[x["id"]] = d
        light.append(x)
    save("board.json", {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "labels": LABEL, "points": PTS,
                        "periods": wells.get("periods", []), "counts": {"leads": len(leads), "minerals": len(minerals)},
                        "rows": light, "leads": [x["id"] for x in leads], "minerals": [x["id"] for x in minerals[:3000]],
                        "estates": estates[:400], "sheriff": sheriff, "tax_lists": load("taxclaim.json", {}).get("lists", {})})
    save("details.json", details)
    save("lookup.json", [[r["id"], r.get("ctrl", ""), r.get("pid"), r.get("owner", ""), r.get("owner2", ""), r.get("mail", ""), r.get("city", ""),
                          r.get("st", ""), r.get("lu", ""), r.get("blight", ""), r.get("acres"), r.get("deed", ""), r.get("lat"), r.get("lon")] for r in parcels])
    print("leads", len(leads), "minerals", len(minerals), "stacked(2+ hard)", sum(1 for x in leads if x["hard"] >= 2))


if __name__ == "__main__":
    run()
