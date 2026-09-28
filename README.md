# Open Library Collector

Collect book metadata from the [Open Library Public Search API](https://openlibrary.org/developers/api) and export it to a clean, Excel-ready CSV file.

The script fetches **55 books** for a search query, keeps only the titles whose **first publication year is strictly greater than 2000**, and writes the result to a CSV file encoded with `utf-8-sig` (UTF-8 with a byte-order mark), so the file opens without mojibake in Microsoft Excel.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Command Line Options](#command-line-options)
- [Output Format](#output-format)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- Fetches book metadata from `https://openlibrary.org/search.json` using a single third-party dependency (`requests`).
- Filters results on `first_publish_year > 2000` (strictly greater, so a book from 2000 is excluded).
- Handles pagination transparently (the API returns at most 100 documents per page).
- Retries transient network failures with exponential backoff before giving up.
- Skips malformed records instead of crashing on a missing or ill-typed field.
- Writes UTF-8-with-BOM CSV (`utf-8-sig`) for seamless Excel compatibility.
- Ships a command line interface with sensible, overridable defaults.

## Prerequisites

| Requirement | Version |
| ----------- | ------- |
| Python      | 3.8 or newer (developed and tested on 3.14) |
| `requests`  | 2.31.0 or newer |

No other third-party packages are required — the standard library provides `csv`, `argparse`, `logging`, `dataclasses` and `json` handling. There is no API key to register for.

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/<your-username>/open-library-collector.git
cd open-library-collector
```

**2. Create and activate a virtual environment**

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install the dependencies**

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The script also runs without the `requirements.txt` step if `requests` is already present in your environment (`pip install requests`).

## Usage

Run with the defaults — query `programming`, fetch 55 books, keep those first published after 2000, write `openlibrary_books.csv`:

```bash
python openlibrary_collector.py
```

Expected console output:

```text
INFO: Fetched 55 book(s) for query 'programming'.
INFO: 52 of 55 book(s) were first published after 2000.
INFO: Wrote 52 row(s) to 'openlibrary_books.csv'.
```

Common variations:

```bash
# Different topic, larger sample
python openlibrary_collector.py --query science --limit 200

# Keep only books first published after 2015
python openlibrary_collector.py --min-year 2015

# Choose the output file
python openlibrary_collector.py --output data/science_books.csv

# Debug logging (shows records skipped and every retry)
python openlibrary_collector.py --verbose
```

## Command Line Options

| Option | Default | Description |
| ------ | ------- | ----------- |
| `--query` | `programming` | Search query sent to Open Library. |
| `--limit` | `55` | Maximum number of valid books to fetch. |
| `--min-year` | `2000` | Keep books whose `first_publish_year` is **strictly greater** than this value. |
| `--output` | `openlibrary_books.csv` | Destination CSV file, written with `utf-8-sig`. |
| `--timeout` | `30` | Per-request HTTP timeout, in seconds. |
| `--verbose` | off | Enable debug level logging. |
| `-h`, `--help` | — | Show the help message and exit. |

The script is also importable as a library:

```python
from openlibrary_collector import fetch_books, filter_books, write_csv

books = fetch_books(query="science", limit=55)
recent = filter_books(books, min_year=2000)
write_csv(recent, "science_books.csv")
```

## Output Format

A single CSV file with one header row followed by one row per book.

| Column | Type | Description |
| ------ | ---- | ----------- |
| `title` | text | Book title. |
| `author` | text | Author name(s), comma separated, or `Unknown`. |
| `first_publish_year` | integer | The year of the first publication; the field filtered on. |
| `edition_count` | integer | Number of editions known to Open Library (`0` if unknown). |
| `language` | text | Language code(s), comma separated, or `Unknown`. |
| `ratings_average` | text | Average reader rating with two decimals, or empty if unrated. |
| `isbn` | text | Up to three ISBNs, comma separated. |
| `openlibrary_key` | text | Open Library work key, e.g. `/works/OL45804W`. |

Sample output:

```csv
title,author,first_publish_year,edition_count,language,ratings_average,isbn,openlibrary_key
The Pragmatic Programmer,Andrew Hunt and David Thomas,1999,32,eng,4.20,9780135957059,/works/OL1164653W
Clean Code,Robert C. Martin,2008,45,eng,4.31,9780132350884,/works/OL17593266W
Design Patterns,Erich Gamma and Richard Helm,1994,54,eng,4.24,9780201633610,/works/OL17981919W
```

A real run over the `programming` query is dominated by titles such as *Clean Code*, *Refactoring*, *Python Crash Course* and *Learning Python*, since the pre-2001 programming classics are filtered out.

Encoding details:

- The file is written with `encoding="utf-8-sig"`, so it begins with the three bytes `EF BB BF` (the UTF-8 BOM). Excel uses this to detect UTF-8 and renders accented and non-Latin titles correctly; `pandas.read_csv()` and other tools also handle it transparently.
- Rows are written with `\r\n` line terminators (via `csv.DictWriter` and `newline=""`), which is the format Excel expects.
- The output directory must already exist; a missing path is reported as an error rather than being created silently.

## Project Structure

```text
open-library-collector/
├── openlibrary_collector.py   # Entry point: fetching, filtering, CSV export, CLI
├── requirements.txt           # Pinned dependency (requests)
├── README.md                  # This file
└── openlibrary_books.csv      # Generated output (not tracked by git)
```

## How It Works

1. **Fetch** — `fetch_books()` builds a `requests.Session` with a descriptive `User-Agent`, requests only the fields it needs via the `fields` parameter, and pages through the result set (page size capped at the API maximum of 100) until `--limit` valid records are collected or `numFound` is reached.
2. **Normalise** — each raw document is converted into a frozen `Book` dataclass. Records without a usable title, and records whose `first_publish_year` is missing or not an integer, are skipped and logged at debug level.
3. **Filter** — `filter_books()` keeps only records where `first_publish_year > min_year`, a strict comparison so the threshold year itself is excluded.
4. **Export** — `write_csv()` writes the `Book` fields with `csv.DictWriter` into a `utf-8-sig` file, guaranteeing a header row and correct quoting for titles containing commas or quotes.

## Error Handling

| Situation | Behaviour |
| --------- | --------- |
| Connection error or timeout | Retried up to 3 times with exponential backoff (2s, 4s), then reported as `ApiError` and exit code `1`. |
| HTTP 4xx/5xx response | `raise_for_status()` raises; HTTP 400 aborts immediately since a retry cannot help. |
| Malformed or non-JSON body | Detected, retried, then reported as `ApiError`. |
| Top-level JSON is not an object | Reported as `ApiError`. |
| Missing or empty `docs` key | Treated as an empty result set; the run ends cleanly with exit code `1`. |
| Missing/invalid `first_publish_year` or `title` | Record skipped, logged at debug level, remaining records still exported. |
| Filter matches zero books | Exits `1` with a hint to lower `--min-year` or change `--query`; no empty file is written. |
| Output path not writable | `OSError` is caught and reported; exit code `1`. |
| Invalid `--limit` (zero or negative) | `ValueError` is caught and reported; exit code `2`. |

Exit codes: `0` success, `1` runtime or API failure, `2` invalid arguments.

## Troubleshooting

**`requests.exceptions.ConnectionError` / timeouts** — Open Library throttles bursts of traffic and may be unreachable from some networks. The script already retries three times; re-run later or increase `--timeout`.

**`ERROR: No book matched the filter`** — every result was published in or before the threshold year. Try a broader `--query` or a lower `--min-year`.

**Garbled characters in Excel** — make sure you open the generated `.csv` directly rather than importing it with a legacy code page. The BOM already tells Excel to use UTF-8.

**Too few rows** — `--limit` counts *valid* records after malformed entries are dropped, so a very small result set may produce fewer rows than requested.

## License

Released under the MIT License.
