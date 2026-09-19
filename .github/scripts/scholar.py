#!/usr/bin/env python3
"""Refresh scholar.json from a public Google Scholar profile.

Reads the profile page, pulls the citation table (citations, h-index,
i10-index), the citations-per-year bars and the per-paper counts, and writes
scholar.json at the repository root. index.html loads that file at page load.

If Google serves a block/CAPTCHA page instead of the profile, nothing is
written: the previous scholar.json stays in place and a warning is printed.
"""
import datetime
import json
import pathlib
import sys
import urllib.request

from bs4 import BeautifulSoup

USER = "sIqKWPgAAAAJ"
URL = f"https://scholar.google.com/citations?user={USER}&hl=en&cstart=0&pagesize=100"
OUT = pathlib.Path(__file__).resolve().parents[2] / "scholar.json"

# Site publication id -> a distinctive, lower-case fragment of its Scholar title.
# Add a line here whenever a new paper is added to index.html.
PAPERS = {
    "egyai2021": "numerical investigation of a modified kalina",
    "ecmx2021": "analysis and optimization of a modified kalina",
    "bcb2024": "landfill and sewage treatment plant",
    "wen2026": "techno-economic assessment of incineration-based",
    "hkust2023": "sub-second hkust-1 synthesis",
    "go2026": "synthesis of go@",
    "cnt2026": "synthesis of mwcnt@",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def warn(msg: str) -> None:
    # "::warning::" shows up as an annotation on the GitHub Actions run.
    print(f"::warning::{msg}")
    print(msg, file=sys.stderr)


def fetch() -> str:
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def to_int(text: str) -> int:
    text = (text or "").strip().replace(",", "")
    return int(text) if text.isdigit() else 0


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#gsc_rsb_st")
    if table is None:
        raise RuntimeError("profile table not found (blocked, CAPTCHA, or layout change)")

    cells = [to_int(td.get_text()) for td in table.select("td.gsc_rsb_std")]
    if len(cells) < 6:
        raise RuntimeError(f"unexpected citation table: {cells}")

    # Per-year bars: year labels and bar values are separate absolutely
    # positioned elements. Each has an inline `right:` offset; a bar sits a few
    # px from its label, so pair every bar with the nearest label. A year with
    # no citations may have no bar at all and stays at 0.
    def offset(el) -> float:
        style = el.get("style", "")
        for part in style.split(";"):
            part = part.strip()
            if part.startswith("right:"):
                try:
                    return float(part[6:].strip().rstrip("px"))
                except ValueError:
                    return -1.0
        return -1.0

    labels = [(offset(s), to_int(s.get_text())) for s in soup.select(".gsc_g_t")]
    labels = [(off, y) for off, y in labels if y and off >= 0]
    per_year = {str(y): 0 for _, y in labels}
    for a in soup.select("a.gsc_g_a"):
        off = offset(a)
        if off < 0 or not labels:
            continue
        _, year = min(labels, key=lambda lab: abs(lab[0] - off))
        per_year[str(year)] = to_int(a.get_text())
    per_year = dict(sorted(per_year.items()))

    rows = []
    for tr in soup.select("tr.gsc_a_tr"):
        title = tr.select_one("a.gsc_a_at")
        cites = tr.select_one("a.gsc_a_ac")
        year = tr.select_one(".gsc_a_y span")
        rows.append({
            "title": title.get_text(" ", strip=True) if title else "",
            "cites": to_int(cites.get_text()) if cites else 0,
            "year": to_int(year.get_text()) if year else 0,
        })

    papers = {}
    for pub_id, fragment in PAPERS.items():
        match = next((r for r in rows if fragment in r["title"].lower()), None)
        papers[pub_id] = match["cites"] if match else 0
        if match is None:
            warn(f"no Scholar entry matched site publication '{pub_id}'")

    return {
        "updated": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "source": f"https://scholar.google.com/citations?user={USER}",
        "citations": cells[0],
        "citations_recent": cells[1],
        "h_index": cells[2],
        "h_index_recent": cells[3],
        "i10_index": cells[4],
        "i10_index_recent": cells[5],
        "per_year": per_year,
        "papers": papers,
        "all_entries": [r for r in rows if r["title"]],
    }


def main() -> int:
    try:
        data = parse(fetch())
    except Exception as exc:  # noqa: BLE001 - any failure means "keep the old file"
        warn(f"Scholar refresh skipped, keeping previous scholar.json: {exc}")
        return 0

    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.name}: {data['citations']} citations, "
        f"h-index {data['h_index']}, i10-index {data['i10_index']}, "
        f"per year {data['per_year']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
