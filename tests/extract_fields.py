"""
tv_fields_scraper.py
====================
Fetch the TradingView “Stocks fields” page and extract:
    code  – the machine‑readable field name
    label – the human‑readable description
    dtype – one of: text | bool | number | percent | price | fundamental_price
            | time | map | set | num_slice

Usage:
    python tv_fields_scraper.py             # prints a preview
    python tv_fields_scraper.py csv fields.csv   # saves to CSV
    python tv_fields_scraper.py json fields.json # saves to JSON
"""

import sys, re, csv, json, requests
from bs4 import BeautifulSoup

URL   = "https://shner-elmo.github.io/TradingView-Screener/fields/stocks.html"
TYPES = {
    "text", "bool", "number", "percent", "price", "fundamental_price",
    "time", "map", "set", "num_slice"
}

def fetch_page(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_fields(html: str):
    soup   = BeautifulSoup(html, "html.parser")
    raw    = soup.get_text("\n")                # strip all tags
    fields = []

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("*"):    # skip empties & bullet repeats
            continue
        if line.lower().startswith(("name ", "fields ", "deduplicated", "last updated")):
            continue

        # Detect “… code  display‑words  dtype”
        tokens = line.split()
        dtype  = tokens[-1]
        if dtype not in TYPES:
            continue                            # not a row we want

        code        = tokens[0]
        display     = " ".join(tokens[1:-1]) or code
        fields.append({"code": code, "label": display, "dtype": dtype})

    return fields

def main():
    html   = fetch_page(URL)
    fields = parse_fields(html)

    if len(sys.argv) == 1:  # just run → print all rows
        print(f"Extracted {len(fields):,} rows\n")
        for row in fields:
            print(row)
    else:
        mode, outfile = sys.argv[1:3]
        if mode.lower() == "csv":
            with open(outfile, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["code", "label", "dtype"])
                w.writeheader(); w.writerows(fields)
        elif mode.lower() == "json":
            with open(outfile, "w", encoding="utf-8") as f:
                json.dump(fields, f, ensure_ascii=False, indent=2)
        else:
            raise SystemExit("Mode must be csv or json")
        print(f"Saved {len(fields):,} rows → {outfile}")



if __name__ == "__main__":
    main()
