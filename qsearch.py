#!/usr/bin/env python3

import argparse
import importlib
import os
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ENGINES_DIR = Path(__file__).parent / "engines"

OFFICIAL_ENGINES = [
    "piratebay",
    "eztv",
    "solidtorrents",
    "limetorrents",
    "torrentscsv",
    "torlock",
]

OFFICIAL_URLS = {
    name: f"https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/{name}.py"
    for name in OFFICIAL_ENGINES
}


# ── engine loader ────────────────────────────────────────────────────────────

def load_engines():
    """Import all .py files in engines/ (excluding helpers/novaprinter) as engine modules."""
    sys.path.insert(0, str(ENGINES_DIR))

    skip = {"__init__", "helpers", "novaprinter", "jackett"}
    engines = []
    for path in sorted(ENGINES_DIR.glob("*.py")):
        if path.stem in skip:
            continue
        try:
            mod = importlib.import_module(path.stem)
            cls = getattr(mod, path.stem, None)
            if cls and callable(getattr(cls, "search", None)):
                engines.append((path.stem, cls()))
        except Exception as exc:
            print(f"  [!] Could not load {path.stem}: {exc}", file=sys.stderr)
    return engines


# ── search runner ────────────────────────────────────────────────────────────

ENGINE_TIMEOUT = 30  # seconds per engine before it's abandoned
ENGINE_TIMEOUT_RECENT = 60  # longer wait when -r filter is active


def run_search(engines, query: str, status: dict, timeout: int = ENGINE_TIMEOUT):
    """Run all engine searches concurrently, updating status dict as each finishes."""
    import novaprinter

    novaprinter.results.clear()
    result_counts: dict[str, int] = {}
    counts_lock = threading.Lock()

    def worker(name, engine):
        encoded = urllib.parse.quote_plus(query)
        before = len(novaprinter.results)
        try:
            engine.search(encoded, "all")
            after = len(novaprinter.results)
            count = after - before
            with counts_lock:
                result_counts[name] = count
            status[name] = "done"
        except Exception as exc:
            status[name] = f"error: {exc}"

    threads = []
    for name, engine in engines:
        status[name] = "searching"
        t = threading.Thread(target=worker, args=(name, engine), daemon=True)
        threads.append((name, t))
        t.start()

    engine_names = {name: getattr(engine, "name", name) for name, engine in engines}
    done_shown = set()
    deadline = time.time() + timeout

    while time.time() < deadline:
        all_done = all(status[n] != "searching" for n, _ in threads)
        for name, state in list(status.items()):
            if state != "searching" and name not in done_shown:
                icon = "✓" if state == "done" else "✗"
                count = result_counts.get(name, 0)
                label = f"{count} results" if state == "done" else state
                print(f"  [{icon}] {engine_names.get(name, name)}: {label}")
                done_shown.add(name)
        if all_done:
            break
        time.sleep(0.3)

    # Mark anything still running as timed out and show it
    for name, t in threads:
        if status.get(name) == "searching":
            status[name] = f"timeout (>{timeout}s)"
        if name not in done_shown:
            state = status[name]
            icon = "✓" if state == "done" else "✗"
            count = result_counts.get(name, 0)
            label = f"{count} results" if state == "done" else state
            print(f"  [{icon}] {engine_names.get(name, name)}: {label}")

    return novaprinter.results


# ── output formatting ────────────────────────────────────────────────────────

def _human_size(raw: str) -> str:
    try:
        b = float(raw.split()[0])
    except (ValueError, IndexError):
        return raw if raw and raw != "-1" else "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _info_hash(link: str) -> str:
    """Extract btih hash from magnet link for deduplication."""
    import re
    m = re.search(r"urn:btih:([a-fA-F0-9]{32,40})", link, re.I)
    return m.group(1).lower() if m else link


def deduplicate(results: list) -> list:
    seen: set[str] = set()
    out = []
    for r in results:
        key = _info_hash(r["link"]) if r["link"].startswith("magnet:") else r["link"]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def parse_duration(s: str) -> int:
    """Parse a duration string like '7d', '2w', '24h', '90m' into seconds."""
    units = {'m': 60, 'h': 3600, 'd': 86400, 'w': 604800}
    s = s.strip().lower()
    if not s:
        raise ValueError("empty duration")
    suffix = s[-1]
    if suffix not in units:
        raise ValueError(f"unknown unit '{suffix}' — use m, h, d, or w (e.g. 7d, 2w, 24h)")
    try:
        value = int(s[:-1])
    except ValueError:
        raise ValueError(f"invalid duration '{s}' — expected a number followed by m/h/d/w")
    if value <= 0:
        raise ValueError("duration must be positive")
    return value * units[suffix]


def filter_recent(results: list, since_seconds: int) -> list:
    cutoff = int(datetime.now(timezone.utc).timestamp()) - since_seconds
    return [r for r in results if isinstance(r.get("pub_date"), int) and r["pub_date"] > cutoff]


def build_query(terms: list[str]) -> str:
    """Quote each CLI term so multi-part searches stay exact."""
    return " ".join(f'"{term.replace(chr(34), r"\\\"")}"' for term in terms)


def format_results(results: list, top_n: int, sort_by_date: bool = False) -> list[str]:
    results = deduplicate(results)
    if sort_by_date:
        dated = [r for r in results if isinstance(r.get("pub_date"), int) and r["pub_date"] > 0]
        undated = [r for r in results if not (isinstance(r.get("pub_date"), int) and r["pub_date"] > 0)]
        sorted_results = sorted(dated, key=lambda r: r["pub_date"], reverse=True) + undated
    else:
        valid = [r for r in results if r["seeds"] >= 0]
        no_seed = [r for r in results if r["seeds"] < 0]
        sorted_results = sorted(valid, key=lambda r: r["seeds"], reverse=True) + no_seed
    top = sorted_results[:top_n]

    lines = []
    for i, r in enumerate(top, 1):
        seeds = r["seeds"] if r["seeds"] >= 0 else "?"
        leech = r["leech"] if r["leech"] >= 0 else "?"
        size = _human_size(r["size"])
        lines.append(f"{'─' * 72}")
        lines.append(f"#{i}  {r['name']}")
        lines.append(f"    Seeds: {seeds}  Leechers: {leech}  Size: {size}")
        if r.get("desc_link"):
            lines.append(f"    Info: {r['desc_link']}")
        lines.append(f"    {r['link']}")
    lines.append(f"{'─' * 72}")
    return lines


# ── file output ──────────────────────────────────────────────────────────────

def write_file(query: str, lines: list[str]):
    safe = query.replace(" ", "_").replace("/", "-")[:60]
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date}_{safe}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Search: {query}\n")
        f.write(f"Date:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("\n".join(lines))
        f.write("\n")
    print(f"\nResults saved to: {filename}")


# ── engine updater ───────────────────────────────────────────────────────────

def update_engines():
    import urllib.request
    print("Downloading engine plugins from qbittorrent/search-plugins...")
    for name, url in OFFICIAL_URLS.items():
        dest = ENGINES_DIR / f"{name}.py"
        try:
            urllib.request.urlretrieve(url, dest)
            print(f"  ✓ {name}")
        except Exception as exc:
            print(f"  ✗ {name}: {exc}")
    print("Done.")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    usage_path = Path(__file__).parent / "USAGE.md"
    epilog = f"Full documentation: {usage_path}"

    parser = argparse.ArgumentParser(
        prog="qsearch",
        description="Search torrent sites using qBittorrent search plugins.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument("terms", nargs="*", help="Search term(s). Each term is quoted in the final query.")
    parser.add_argument("-n", "--count", type=int, default=20, metavar="N",
                        help="Number of results to show, sorted by seeders (default: 20)")
    parser.add_argument("-r", "--recent", metavar="DURATION",
                        help="Only show results released within a time window (e.g. 7d, 2w, 24h, 90m)")
    parser.add_argument("-f", "--file", action="store_true",
                        help="Write results to a dated .txt file in addition to terminal output")
    parser.add_argument("--update-engines", action="store_true",
                        help="Re-download all official engine plugins and exit")
    parser.add_argument("--list-engines", action="store_true",
                        help="List available engine plugins and exit")

    args = parser.parse_args()

    if args.update_engines:
        update_engines()
        return

    if args.list_engines:
        engines = load_engines()
        if not engines:
            print("No engines found. Run with --update-engines to download them.")
        else:
            for name, eng in engines:
                print(f"  {getattr(eng, 'name', name):30s}  {getattr(eng, 'url', '')}")
        return

    if not args.terms:
        parser.print_help()
        print(f"\nSee {usage_path} for more examples.")
        sys.exit(1)

    recent_seconds = None
    if args.recent:
        try:
            recent_seconds = parse_duration(args.recent)
        except ValueError as exc:
            parser.error(str(exc))

    query = build_query(args.terms)

    engines = load_engines()
    if not engines:
        print("No engines found. Run: python qsearch.py --update-engines")
        sys.exit(1)

    engine_names = [getattr(e, "name", n) for n, e in engines]
    print(f'\nSearching {len(engines)} engines for "{query}"')
    print(f"Engines: {', '.join(engine_names)}\n")

    timeout = ENGINE_TIMEOUT_RECENT if recent_seconds is not None else ENGINE_TIMEOUT
    status = {}
    results = run_search(engines, query, status, timeout=timeout)

    total = len(results)
    print(f"\nTotal results collected: {total}")

    sort_by_date = False
    if recent_seconds is not None:
        filtered = filter_recent(results, recent_seconds)
        print(f"After -{args.recent} filter: {len(filtered)} results")
        if filtered:
            results = filtered
            sort_by_date = True
        else:
            print(f"No results within {args.recent} — engines likely returned only older popular results.")
            print(f"Showing most recent from full result set instead:\n")
            sort_by_date = True

    if not results:
        print("No results found.")
        return

    total = len(results)
    if sort_by_date:
        print(f"Showing top {min(args.count, total)} by most recent:\n")
    else:
        print(f"Showing top {min(args.count, total)} by seeders:\n")
    lines = format_results(results, args.count, sort_by_date=sort_by_date)
    print("\n".join(lines))

    if args.file:
        write_file(query, lines)


if __name__ == "__main__":
    main()
