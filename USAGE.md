# qsearch

Search torrent sites using qBittorrent search plugins.

## Usage

```
python qsearch.py [TERMS...] [OPTIONS]
```

When run in a terminal, results open in an interactive picker.

Run with no terms (`python qsearch.py`) to get a `Search:` prompt instead of
needing CLI arguments — quotes work like in the shell (`ubuntu "25.04"`), and
any flags you pass apply to every search. Submit an empty line to quit.

## Interactive picker

| Key | Action |
|---|---|
| `↑`/`↓`, `j`/`k` | Move selection |
| `PgUp`/`PgDn`, `g`/`G` | Page / jump to top or bottom |
| `Enter` | Add selected torrent to Transmission |
| `/` | Type a new search and rerun without quitting |
| `q` / `Esc` | Quit |

Pressing `Enter` prompts for a download directory, then runs
`transmission-remote -w DIR -a LINK` (requires `transmission-remote` in PATH —
on Debian/Ubuntu: `sudo apt install transmission-cli`):

- **Tab** autocompletes directories
- The last-used directory is prefilled next time (remembered across runs)
- Leave empty to use Transmission's default download location
- **Esc** cancels
- After adding, you return to the list (added items are marked `✓`) so you can pick more

## Arguments

| Argument | Description |
|---|---|
| `TERMS` | One or more search terms, joined into a single query |

## Options

| Flag | Default | Description |
|---|---|---|
| `-n N`, `--count N` | `40` | Show top N results sorted by seeders |
| `-r DURATION`, `--recent DURATION` | off | Only show results released within a time window |
| `-f`, `--file` | off | Also write results to a dated `.txt` file |
| `-p`, `--plain` | off | Print results as text instead of opening the interactive picker (automatic when output is piped) |
| `-t N`, `--timeout N` | `15` (`40` with `-r`) | Seconds to wait for slow engines |
| `--update-engines` | — | Re-download all official engine plugins and exit |
| `--list-engines` | — | List available engine plugins and exit |

## Duration format for `-r`

| Suffix | Unit |
|---|---|
| `m` | minutes |
| `h` | hours |
| `d` | days |
| `w` | weeks |

Examples: `2h`, `7d`, `2w`, `90m`

Results with no date information are excluded when `-r` is used.

## Examples

```sh
# No arguments: prompts for a search term interactively
python qsearch.py

# Basic search
python qsearch.py "breaking bad"

# Multiple terms joined into one query
python qsearch.py "the boys" "s03e01"

# Top 5 results from the last 3 days
python qsearch.py "the boys" -n 5 -r 3d

# Last week's releases, saved to file
python qsearch.py "house of the dragon" -r 1w -f

# Show available engines
python qsearch.py --list-engines

# Update engine plugins from qbittorrent/search-plugins
python qsearch.py --update-engines
```
