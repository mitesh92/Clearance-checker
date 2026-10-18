"""Daily clearance checker: Home Depot + Lowe's near ZIP 60188, 70%+ off only.
Uses Apify actors (both stores block plain scraping). Writes docs/index.html + docs/results.json.
Setup: set env var APIFY_TOKEN. Run: python clearance_checker.py
"""
import os, json, datetime, html, requests

ZIP = "60188"
MIN_OFF = 70.0
TOKEN = os.environ["APIFY_TOKEN"]

# Check each actor's "Input" tab on apify.com and adjust these inputs if a field name differs.
ACTORS = {
    "Home Depot": {
        "actor": "scrapyspider~home-depot-clearance-scraper",
        "input": {"zipCode": ZIP, "maxItems": 2000},
    },
    "Lowe's": {
        "actor": "memo23~lowes-scraper",
        "input": {"zipCode": ZIP,
                  "startUrls": [{"url": "https://www.lowes.com/pl/Clearance/4294737226"}]},  # confirm the clearance URL
    },
}

def num(v):
    try:
        return float(str(v).replace("$", "").replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None

def pick(item, *needles):
    for k, v in item.items():
        if all(n in k.lower() for n in needles) and num(v) is not None:
            return num(v)

def percent_off(item):
    p = pick(item, "percent") or pick(item, "savings", "pct")
    if p is not None:
        return p * 100 if 0 < p <= 1 else p
    was = pick(item, "original") or pick(item, "was")
    now = pick(item, "current") or pick(item, "price")
    return round((1 - now / was) * 100, 1) if was and now is not None else None

def run(store, cfg):
    url = f"https://api.apify.com/v2/acts/{cfg['actor']}/run-sync-get-dataset-items"
    r = requests.post(url, params={"token": TOKEN}, json=cfg["input"], timeout=900)
    r.raise_for_status()
    deals = []
    for it in r.json():
        off = percent_off(it)
        if off is not None and off >= MIN_OFF:
            deals.append({
                "store": store,
                "name": it.get("title") or it.get("name") or "Unknown",
                "off": round(off),
                "now": pick(it, "current") or pick(it, "price"),
                "was": pick(it, "original") or pick(it, "was"),
                "url": it.get("url") or it.get("productUrl") or "",
                "stock": it.get("quantity") or it.get("storeQuantity") or it.get("availability") or "",
            })
    return deals

def main():
    deals, errors = [], []
    for store, cfg in ACTORS.items():
        try:
            deals += run(store, cfg)
        except Exception as e:
            errors.append(f"{store}: {e}")
    deals.sort(key=lambda d: -d["off"])
    stamp = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")
    os.makedirs("docs", exist_ok=True)
    json.dump({"updated": stamp, "deals": deals, "errors": errors},
              open("docs/results.json", "w"), indent=2)
    rows = "".join(
        f"<div class=c><b>{d['off']}% off</b> · {html.escape(d['store'])}<br>"
        f"<a href='{html.escape(d['url'])}'>{html.escape(d['name'])}</a><br>"
        f"${d['now']} <s>${d['was']}</s> {html.escape(str(d['stock']))}</div>" for d in deals
    ) or "<p>No 70%+ off items found today.</p>"
    err = "".join(f"<p class=e>⚠ {html.escape(e)}</p>" for e in errors)
    open("docs/index.html", "w").write(f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Clearance 70%+ · {ZIP}</title>
<style>body{{font:16px system-ui;max-width:600px;margin:auto;padding:16px}}
.c{{border:1px solid #8884;border-radius:10px;padding:12px;margin:10px 0}}.e{{color:#c00}}</style>
<h2>70%+ off clearance · {ZIP}</h2><small>Updated {stamp}</small>{err}{rows}""")
    print(f"{len(deals)} deals, {len(errors)} errors")

main()
