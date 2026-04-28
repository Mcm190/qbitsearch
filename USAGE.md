# qsearch

Search torrent sites using qBittorrent search plugins.

## Usage

```
python qsearch.py [TERMS...] [OPTIONS]
```

## Arguments

| Argument | Description |
|---|---|
| `TERMS` | One or more search terms, joined into a single query |

## Options

| Flag | Default | Description |
|---|---|---|
| `-n N`, `--count N` | `20` | Show top N results sorted by seeders |
| `-r DURATION`, `--recent DURATION` | off | Only show results released within a time window |
| `-f`, `--file` | off | Also write results to a dated `.txt` file |
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
