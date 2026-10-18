"""Daily clearance checker: two specific stores (HD #1917 Glendale Heights, Lowe's #1821 Carol Stream), 75%+ off only.
Uses Apify actors. Writes docs/index.html, docs/results.json, docs/debug.json.
Needs env var APIFY_TOKEN.
"""
import os, json, datetime, html, requests

ZIP = "60188"
HD_STORE_ID = "1917"      # Home Depot, 295 E Army Trail Rd, Glendale Heights IL 60139
LOWES_STORE_ID = "1821"   # Lowe's, 400 W Army Trail Rd, Carol Stream IL 60188
MIN_OFF = 75.0
HD_MAX_RESULTS = 500   # 0 = unlimited (full scan). Keep 500 for the first test run, then set 0.
LOWES_MAX_ITEMS = 500
# Lowe's has no public clearance page. Add category URLs (must contain /pl/) copied from lowes.com.
LOWES_URLS = [
    "https://www.lowes.com/pl/power-tools/drills-drivers/4294607728",
]

APIFY = "https://api.apify.com/v2/acts/{}/run-sync-get-dataset-items"

def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def pct(now, was):
    return round((1 - now / was) * 100, 1) if now is not None and was and was > 0 else None

def parse_hd(it):
    p = it.get("pricing") or {}
    now, was = to_num(p.get("value")), to_num(p.get("original"))
    off = pct(now, was)
    store, qty = "", ""
    for opt in (it.get("fulfillment") or {}).get("fulfillmentOptions") or []:
        if opt.get("type") == "pickup":
            for svc in opt.get("services") or []:
                for loc in svc.get("locations") or []:
                    store = loc.get("storeName") or store
                    qty = (loc.get("inventory") or {}).get("quantity", qty)
    ident = it.get("identifiers") or {}
    return {
        "id": ident.get("itemId") or it.get("itemId"),
        "store": "Home Depot", "storeName": store, "off": off, "now": now, "was": was,
        "name": ident.get("productLabel") or "Unknown",
        "brand": ident.get("brandName") or "",
        "url": it.get("URL") or "",
        "qty": qty,
        "clearance": bool(it.get("isClearanceItem") or p.get("clearance")),
    }

def parse_lowes(it):
    now, was = to_num(it.get("price")), to_num(it.get("wasPrice"))
    off = to_num(it.get("savingsPercent"))
    if off is None:
        off = pct(now, was)
    return {
        "id": it.get("itemId"), "store": "Lowe's", "storeName": it.get("storeName") or "",
        "off": off, "now": now, "was": was, "name": it.get("title") or "Unknown",
        "brand": it.get("brand") or "", "url": it.get("url") or "",
        "qty": it.get("storeQuantity", ""), "clearance": bool(it.get("onSale")),
    }

def fetch(actor, payload, token):
    r = requests.post(APIFY.format(actor), params={"token": token}, json=payload, timeout=1800)
    r.raise_for_status()
    return r.json()

def main():
    token = os.environ["APIFY_TOKEN"]
    jobs = [
        ("Home Depot", "scrapyspider~home-depot-clearance-scraper",
         {"storeId": HD_STORE_ID, "maxResults": HD_MAX_RESULTS}, parse_hd),
    ]
    deals, errors, debug = {}, [], {}
    os.makedirs("docs", exist_ok=True)
    for name, actor, payload, parser in jobs:
        try:
            items = fetch(actor, payload, token)
            rows = [parser(i) for i in items]
            stores = sorted({r["storeName"] for r in rows if r["storeName"]})
            seen = sorted([r for r in rows if r["off"] is not None], key=lambda r: -r["off"])
            debug[name] = {"scanned": len(rows), "stores": stores,
                           "top_discounts_seen": [(r["off"], r["name"][:60]) for r in seen[:10]],
                           "sample_raw": items[:2]}
            for r in rows:
                if r["off"] is not None and r["off"] >= MIN_OFF:
                    deals[(name, r["id"])] = r
        except Exception as e:
            errors.append(f"{name}: {e}")
    out = sorted(deals.values(), key=lambda d: -d["off"])
    stamp = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")
    json.dump({"updated": stamp, "deals": out, "errors": errors}, open("docs/results.json", "w"), indent=2)
    json.dump(debug, open("docs/debug.json", "w"), indent=2)

    info = " · ".join(f"{k}: {v['scanned']} scanned, store: {', '.join(v['stores'][:2]) or '?'}" for k, v in debug.items())
    best = max((d["top_discounts_seen"][0][0] for d in debug.values() if d["top_discounts_seen"]), default=None)
    cards = "".join(
        f"<div class=c><b>{d['off']:.0f}% off</b> · {html.escape(d['store'])}"
        f"{' · ' + html.escape(d['storeName']) if d['storeName'] else ''}<br>"
        f"<a href='{html.escape(d['url'])}'>{html.escape(d['name'])}</a><br>"
        f"${d['now']} <s>${d['was']}</s> · qty at store: {html.escape(str(d['qty']))}</div>" for d in out
    ) or f"<p>No {MIN_OFF:.0f}%+ off items today." + (f" Biggest discount seen: {best:.0f}%.</p>" if best else "</p>")
    err = "".join(f"<p class=e>⚠ {html.escape(e)}</p>" for e in errors)
    open("docs/index.html", "w").write(f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Clearance {MIN_OFF:.0f}%+ · {ZIP}</title>
<style>body{{font:16px system-ui;max-width:600px;margin:auto;padding:16px}}
.c{{border:1px solid #8884;border-radius:10px;padding:12px;margin:10px 0}}.e{{color:#c00}}</style>
<h2>{MIN_OFF:.0f}%+ off · near {ZIP}</h2><small>Updated {stamp}<br>{html.escape(info)}</small>{err}{cards}""")
    print(f"{len(out)} deals; {info}; errors={errors}")

if __name__ == "__main__":
    main()
