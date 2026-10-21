"""Obituaries from the Herald-Standard RSS (covers Greene County Messenger area) -> data/obits.json

Keeps a running history; the board matches decedents to parcel owners. Only items that
mention a Greene County place are kept.
"""
import datetime as dt, re
from email.utils import parsedate_to_datetime
from html import unescape
from engine.common import get, save, load

FEEDS = ["https://www.heraldstandard.com/news/obituaries/feed/"]
GREENE = ["Waynesburg", "Carmichaels", "Greensboro", "Mt. Morris", "Mount Morris", "Rices Landing", "Jefferson", "Clarksville",
          "Bobtown", "Dilliner", "Nemacolin", "Crucible", "Mather", "Brave", "Wind Ridge", "Graysville", "Holbrook", "Rogersville",
          "Spraggs", "Garards Fort", "Greene County", "Aleppo", "Cumberland Township",
          "Dunkard", "Franklin Township", "Morgan Township", "Monongahela Township", "Perry Township", "Richhill", "Whiteley",
          "Center Township", "Gilmore", "Gray Township", "Jackson Township", "Morris Township", "Springhill", "Washington Township",
          "Wayne Township"]


def run():
    prev = load("obits.json", {"rows": []}) or {"rows": []}
    have = {r["link"] for r in prev["rows"]}
    new = 0
    for feed in FEEDS:
        x = get(feed).text
        for it in re.findall(r"<item>(.*?)</item>", x, re.S):
            g = lambda t: unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(rf"<{t}>(.*?)</{t}>", it, re.S) or [None, ""])[1])).strip()
            link = g("link")
            if not link or link in have or any(r["name"] == g("title") for r in prev["rows"]):
                continue
            body = re.sub(r"<[^>]+>", " ", g("content:encoded") or g("description"))
            places = [p for p in GREENE if p.lower() in body.lower()]
            if not places:
                continue
            try:
                pub = parsedate_to_datetime(g("pubDate")).date().isoformat()
            except Exception:
                pub = dt.date.today().isoformat()
            title = g("title")
            prev["rows"].append({"name": title, "link": link, "pub": pub, "places": places[:5], "text": re.sub(r"\s+", " ", body)[:1500]})
            have.add(link); new += 1
    prev["rows"].sort(key=lambda r: r["pub"], reverse=True)
    prev["rows"] = prev["rows"][:2000]
    save("obits.json", prev)
    print("new", new, "total", len(prev["rows"]))


if __name__ == "__main__":
    run()
