"""Interactive result picker for qsearch.

Browse search results, press Enter to add one to Transmission
(transmission-remote -w <dir> -a <link>), with tab-completing path entry
for the download directory. Returns to the list after each add.
Press / to type a new search — run_tui returns it so the caller can rerun.
"""

import curses
import os
import subprocess
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "qsearch"
LAST_DIR_FILE = STATE_DIR / "last_dir"

HELP = "↑/↓ move   PgUp/PgDn page   Enter add to Transmission   / new search   q quit"
PROMPT = "Download dir (Tab completes, empty = default, Esc cancels): "
SEARCH_PROMPT = "New search (Enter runs, Esc cancels): "


# ── persisted last-used download dir ─────────────────────────────────────────

def _load_last_dir() -> str:
    try:
        return LAST_DIR_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _save_last_dir(path: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_DIR_FILE.write_text(path, encoding="utf-8")
    except OSError:
        pass


# ── path tab-completion ──────────────────────────────────────────────────────

def complete_path(text: str) -> tuple[str, list[str]]:
    """Complete `text` against directories on disk.

    Returns (new_text, candidates). candidates is non-empty only when the
    completion is ambiguous, so the caller can display the options.
    """
    slash = text.rfind("/")
    head, tail = (text[: slash + 1], text[slash + 1:]) if slash >= 0 else ("", text)
    base = os.path.expanduser(head) if head else "."
    try:
        entries = os.listdir(base)
    except OSError:
        return text, []
    show_hidden = tail.startswith(".")
    dirs = sorted(
        e for e in entries
        if e.startswith(tail)
        and (show_hidden or not e.startswith("."))
        and os.path.isdir(os.path.join(base, e))
    )
    if not dirs:
        return text, []
    if len(dirs) == 1:
        return head + dirs[0] + "/", []
    common = os.path.commonprefix(dirs)
    return head + common, dirs


# ── transmission-remote invocation ───────────────────────────────────────────

def add_torrent(link: str, download_dir: str) -> tuple[bool, str]:
    """Run transmission-remote to add the torrent, optionally with a download dir."""
    cmd = ["transmission-remote"]
    if download_dir:
        cmd += ["-w", os.path.abspath(os.path.expanduser(download_dir))]
    cmd += ["-a", link]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return False, "transmission-remote not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "transmission-remote timed out"
    out = " ".join((proc.stdout + " " + proc.stderr).split())
    if proc.returncode == 0:
        return True, out or "added"
    return False, out or f"transmission-remote exited with {proc.returncode}"


# ── curses UI ────────────────────────────────────────────────────────────────

def _safe_addstr(scr, y: int, x: int, text: str, attr: int = 0) -> None:
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    try:
        scr.addstr(y, x, text[: w - x - 1], attr)
    except curses.error:
        pass


def _prompt_line(stdscr, prompt: str, initial: str = "", complete: bool = False) -> str | None:
    """Edit a line of text on the bottom line. Returns the text, or None if cancelled.

    With complete=True, Tab completes the text as a filesystem path.
    """
    curses.curs_set(1)
    buf = list(initial)
    pos = len(buf)
    candidates: list[str] = []
    try:
        while True:
            h, w = stdscr.getmaxyx()
            stdscr.move(h - 2, 0)
            stdscr.clrtoeol()
            if candidates:
                _safe_addstr(stdscr, h - 2, 0, "  ".join(candidates), curses.A_DIM)
            stdscr.move(h - 1, 0)
            stdscr.clrtoeol()
            text = "".join(buf)
            # Keep the cursor visible when the text outgrows the line
            avail = max(1, w - len(prompt) - 2)
            start = max(0, pos - avail)
            _safe_addstr(stdscr, h - 1, 0, prompt, curses.A_BOLD)
            _safe_addstr(stdscr, h - 1, len(prompt), text[start:start + avail])
            try:
                stdscr.move(h - 1, min(w - 2, len(prompt) + pos - start))
            except curses.error:
                pass
            stdscr.refresh()

            ch = stdscr.get_wch()
            if isinstance(ch, str):
                if ch in ("\n", "\r"):
                    return "".join(buf).strip()
                if ch == "\x1b":  # Esc
                    return None
                if ch == "\t":
                    if complete:
                        new_text, candidates = complete_path("".join(buf))
                        buf = list(new_text)
                        pos = len(buf)
                    continue
                if ch in ("\x7f", "\b"):  # backspace
                    if pos > 0:
                        del buf[pos - 1]
                        pos -= 1
                elif ch == "\x15":  # Ctrl-U
                    buf = []
                    pos = 0
                elif ch == "\x01":  # Ctrl-A
                    pos = 0
                elif ch == "\x05":  # Ctrl-E
                    pos = len(buf)
                elif ch.isprintable():
                    buf.insert(pos, ch)
                    pos += 1
            else:
                if ch == curses.KEY_BACKSPACE and pos > 0:
                    del buf[pos - 1]
                    pos -= 1
                elif ch == curses.KEY_DC and pos < len(buf):
                    del buf[pos]
                elif ch == curses.KEY_LEFT:
                    pos = max(0, pos - 1)
                elif ch == curses.KEY_RIGHT:
                    pos = min(len(buf), pos + 1)
                elif ch == curses.KEY_HOME:
                    pos = 0
                elif ch == curses.KEY_END:
                    pos = len(buf)
            candidates = []
    finally:
        curses.curs_set(0)


def _draw(stdscr, results, query, sel, top, added, status_msg, status_ok):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    _safe_addstr(stdscr, 0, 0, f" qsearch — {query}   ({len(results)} results)", curses.A_BOLD | curses.A_REVERSE)
    _safe_addstr(stdscr, 1, 0, f"   {'Seeds':>6} {'Leech':>6} {'Size':>10}  Name", curses.A_DIM)

    list_h = max(1, h - 4)
    for row, i in enumerate(range(top, min(len(results), top + list_h))):
        r = results[i]
        mark = "✓" if i in added else " "
        seeds = r["seeds"] if r["seeds"] >= 0 else "?"
        leech = r["leech"] if r["leech"] >= 0 else "?"
        size = r.get("size_h", r.get("size", ""))
        line = f" {mark} {seeds:>6} {leech:>6} {size:>10}  {r['name']}"
        attr = curses.A_REVERSE if i == sel else 0
        if i in added and i != sel:
            attr |= curses.A_DIM
        _safe_addstr(stdscr, 2 + row, 0, line, attr)

    if status_msg:
        attr = curses.A_BOLD
        if curses.has_colors():
            attr |= curses.color_pair(1 if status_ok else 2)
        _safe_addstr(stdscr, h - 2, 0, status_msg, attr)
    _safe_addstr(stdscr, h - 1, 0, HELP, curses.A_DIM)
    stdscr.refresh()


def _tui_main(stdscr, results, query) -> str | None:
    curses.curs_set(0)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)

    sel = 0
    top = 0
    added: set[int] = set()
    status_msg = ""
    status_ok = True
    last_dir = _load_last_dir()

    while True:
        h, _ = stdscr.getmaxyx()
        list_h = max(1, h - 4)
        sel = max(0, min(sel, len(results) - 1))
        if sel < top:
            top = sel
        elif sel >= top + list_h:
            top = sel - list_h + 1
        _draw(stdscr, results, query, sel, top, added, status_msg, status_ok)

        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return None
        elif ch == ord("/"):
            term = _prompt_line(stdscr, SEARCH_PROMPT)
            if term:
                return term
            status_msg = ""
        elif ch in (curses.KEY_UP, ord("k")):
            sel -= 1
        elif ch in (curses.KEY_DOWN, ord("j")):
            sel += 1
        elif ch == curses.KEY_PPAGE:
            sel -= list_h
        elif ch == curses.KEY_NPAGE:
            sel += list_h
        elif ch in (curses.KEY_HOME, ord("g")):
            sel = 0
        elif ch in (curses.KEY_END, ord("G")):
            sel = len(results) - 1
        elif ch in (curses.KEY_ENTER, 10, 13):
            path = _prompt_line(stdscr, PROMPT, last_dir, complete=True)
            if path is None:
                status_msg = "Cancelled."
                status_ok = True
                continue
            name = results[sel]["name"]
            status_msg = f"Adding: {name} …"
            _draw(stdscr, results, query, sel, top, added, status_msg, True)
            ok, msg = add_torrent(results[sel]["link"], path)
            if ok:
                added.add(sel)
                if path:
                    last_dir = path
                    _save_last_dir(path)
                dest = path or "default location"
                status_msg = f"✓ Added to {dest}: {name}"
            else:
                status_msg = f"✗ Failed: {msg}"
            status_ok = ok


def run_tui(results: list, query: str) -> str | None:
    """Show the picker. Returns a new search string if the user pressed /, else None."""
    if not results:
        return None
    os.environ.setdefault("ESCDELAY", "25")
    return curses.wrapper(_tui_main, results, query)
