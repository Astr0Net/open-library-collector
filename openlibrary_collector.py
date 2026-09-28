"""Collect book metadata from the Open Library Public Search API into a CSV file.

The script queries the public search endpoint, keeps only the books whose
``first_publish_year`` is strictly greater than a configurable threshold
(2000 by default) and writes the result to a UTF-8 (BOM) CSV file that opens
cleanly in Microsoft Excel.

Example
-------
    python openlibrary_collector.py
    python openlibrary_collector.py --query science --limit 55 --output science.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import requests
except ImportError:  # pragma: no cover - depends on the local environment
    sys.exit(
        "The 'requests' library is required. Install it with: pip install requests"
    )

__all__ = [
    "Book",
    "ApiError",
    "build_parser",
    "fetch_books",
    "filter_books",
    "main",
    "write_csv",
]

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

API_URL = "https://openlibrary.org/search.json"
USER_AGENT = "open-library-collector/1.0 (https://github.com/; educational use)"
DEFAULT_QUERY = "programming"
DEFAULT_LIMIT = 55
DEFAULT_MIN_YEAR = 2000
DEFAULT_OUTPUT = "openlibrary_books.csv"
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 5
RETRY_BACKOFF = 2.0
# Proxy support - set via environment variables HTTP_PROXY/HTTPS_PROXY or --proxy arg
DEFAULT_PROXY = None
# Disable SSL verification if needed (for corporate proxies with custom CAs)
DEFAULT_VERIFY_SSL = True

# Only ask the API for the fields we actually store.
API_FIELDS: Tuple[str, ...] = (
    "key",
    "title",
    "author_name",
    "first_publish_year",
    "edition_count",
    "language",
    "ratings_average",
    "isbn",
)

LOGGER = logging.getLogger("openlibrary_collector")


# --------------------------------------------------------------------------- #
# Domain model
# --------------------------------------------------------------------------- #


class ApiError(RuntimeError):
    """Raised when the Open Library API cannot be reached or returns junk."""


@dataclass(frozen=True)
class Book:
    """A single book record, normalised to a CSV friendly set of fields."""

    title: str
    author: str
    first_publish_year: int
    edition_count: int
    language: str
    ratings_average: str
    isbn: str
    openlibrary_key: str

    def was_published_after(self, year: int) -> bool:
        """Return ``True`` when the book was first published after ``year``."""
        return self.first_publish_year > year

    @property
    def as_csv_row(self) -> Dict[str, Any]:
        """Return the book as an ordered mapping ready for :mod:`csv`."""
        return {field.name: getattr(self, field.name) for field in fields(self)}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def build_session(proxy: Optional[str] = None, verify_ssl: bool = True) -> requests.Session:
    """Create a :class:`requests.Session` with polite default headers."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=10,
        max_retries=0,  # We handle retries manually
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    session.verify = verify_ssl
    return session


def _get_json(
    session: requests.Session,
    params: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    """GET ``API_URL`` and return the decoded JSON object.

    Retries transient failures with exponential backoff, then raises
    :class:`ApiError` with an actionable message.
    """
    last_error: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(API_URL, params=params, timeout=timeout)
            response.raise_for_status()
        except requests.Timeout:
            last_error = f"request timed out after {timeout}s"
        except requests.ConnectionError as exc:
            last_error = f"could not connect to {API_URL} ({exc})"
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            last_error = f"server responded with HTTP {status}"
            if status == 400:  # A malformed query will never succeed: stop early.
                break
        except requests.RequestException as exc:  # Any other transport problem.
            last_error = str(exc)
        else:
            try:
                payload = response.json()
            except ValueError:  # Includes json.JSONDecodeError.
                last_error = "response body was not valid JSON"
                continue

            if not isinstance(payload, dict):
                last_error = "expected a JSON object at the top level"
            else:
                return payload

        if attempt < MAX_RETRIES:
            delay = RETRY_BACKOFF**attempt
            LOGGER.warning(
                "Attempt %d/%d failed (%s). Retrying in %.0fs...",
                attempt,
                MAX_RETRIES,
                last_error,
                delay,
            )
            time.sleep(delay)

    raise ApiError(f"unable to query the Open Library API: {last_error}")


def _parse_book(document: Any) -> Optional[Book]:
    """Convert a raw API document into a :class:`Book`.

    Returns ``None`` when the document lacks the minimum data required
    (a title and a valid ``first_publish_year``).
    """
    if not isinstance(document, dict):
        LOGGER.debug("Skipping non-object document: %r", document)
        return None

    title = document.get("title")
    raw_year = document.get("first_publish_year")

    if not isinstance(title, str) or not title.strip():
        LOGGER.debug(
            "Skipping document without a usable title: %r", document.get("key")
        )
        return None

    # The API returns a year, but guard against strings, floats and junk values.
    try:
        year = int(raw_year)
    except (TypeError, ValueError):
        LOGGER.debug(
            "Skipping '%s': first_publish_year=%r is not a number", title, raw_year
        )
        return None

    ratings = document.get("ratings_average")

    return Book(
        title=title.strip(),
        author=_join_values(document.get("author_name")) or "Unknown",
        first_publish_year=year,
        edition_count=_as_int(document.get("edition_count")) or 0,
        language=_join_values(document.get("language")) or "Unknown",
        ratings_average=(
            f"{ratings:.2f}" if isinstance(ratings, (int, float)) else ""
        ),
        # Long ISBN lists are truncated to keep the CSV cell readable.
        isbn=_join_values(document.get("isbn"), limit=3),
        openlibrary_key=str(document.get("key") or ""),
    )


def _join_values(value: Any, limit: Optional[int] = None) -> str:
    """Flatten an API list-or-scalar field into a comma separated string."""
    if value is None:
        return ""
    if not isinstance(value, list):
        return str(value)
    if limit is not None:
        value = value[:limit]
    return ", ".join(str(item) for item in value)


def _as_int(value: Any) -> Optional[int]:
    """Best-effort conversion of ``value`` to :class:`int`."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def fetch_books(
    query: str = DEFAULT_QUERY,
    limit: int = DEFAULT_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
    proxy: Optional[str] = DEFAULT_PROXY,
    verify_ssl: bool = DEFAULT_VERIFY_SSL,
) -> List[Book]:
    """Fetch up to ``limit`` books matching ``query``.

    The API caps a single page at 100 documents, so the search is paginated
    until the requested number of records has been collected.

    Raises:
        ApiError: if the API cannot be reached or answers with invalid data.
    """
    if limit <= 0:
        raise ValueError("limit must be a positive integer")

    owns_session = session is None
    session = session or build_session(proxy=proxy, verify_ssl=verify_ssl)

    # The API caps a single page at 100 documents.
    page_size = min(limit, 100)
    params = {"q": query, "limit": page_size, "fields": ",".join(API_FIELDS)}

    books: List[Book] = []
    page = 1

    try:
        while len(books) < limit:
            payload = _get_json(session, {**params, "page": page}, timeout)

            documents = payload.get("docs")
            if not isinstance(documents, list):
                LOGGER.warning("Page %d contained no 'docs' list; stopping.", page)
                break
            if not documents:
                break

            for document in documents:
                book = _parse_book(document)
                if book is not None:
                    books.append(book)
                if len(books) >= limit:
                    break

            num_found = payload.get("numFound")
            if isinstance(num_found, int) and page * page_size >= num_found:
                break  # Reached the end of the result set.

            page += 1
    finally:
        if owns_session:
            session.close()

    LOGGER.info("Fetched %d book(s) for query '%s'.", len(books), query)
    return books


def filter_books(books: Sequence[Book], min_year: int = DEFAULT_MIN_YEAR) -> List[Book]:
    """Keep only books first published *after* ``min_year`` (exclusive)."""
    return [book for book in books if book.was_published_after(min_year)]


def write_csv(books: Sequence[Book], output_path: str) -> str:
    """Write ``books`` to ``output_path`` as UTF-8-with-BOM CSV.

    Returns:
        The number of data rows written.
    """
    fieldnames = [field.name for field in fields(Book)]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(book.as_csv_row for book in books)

    return len(books)


# --------------------------------------------------------------------------- #
# Command line interface
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch books from the Open Library Public Search API, keep those "
            "first published after a given year and export them to CSV."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Search query sent to Open Library.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of books to fetch from the API.",
    )
    parser.add_argument(
        "--min-year",
        type=int,
        default=DEFAULT_MIN_YEAR,
        help="Keep books whose first_publish_year is strictly greater than this value.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Destination CSV file (written with utf-8-sig encoding).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--proxy",
        default=DEFAULT_PROXY,
        help="Proxy URL (e.g., http://proxy:8080). Can also be set via HTTP_PROXY/HTTPS_PROXY env vars.",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL certificate verification (useful for corporate proxies).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug level logging.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        books = fetch_books(
            query=args.query,
            limit=args.limit,
            timeout=args.timeout,
            proxy=args.proxy,
            verify_ssl=not args.no_verify_ssl,
        )
    except ApiError as exc:
        LOGGER.error("%s", exc)
        return 1
    except ValueError as exc:
        LOGGER.error("Invalid argument: %s", exc)
        return 2

    if not books:
        LOGGER.error("No books were returned for query '%s'.", args.query)
        return 1

    filtered = filter_books(books, args.min_year)
    LOGGER.info(
        "%d of %d book(s) were first published after %d.",
        len(filtered),
        len(books),
        args.min_year,
    )

    if not filtered:
        LOGGER.error(
            "No book matched the filter (first_publish_year > %d). "
            "Try lowering --min-year or using a different --query.",
            args.min_year,
        )
        return 1

    try:
        rows = write_csv(filtered, args.output)
    except OSError as exc:
        LOGGER.error("Could not write '%s': %s", args.output, exc)
        return 1

    LOGGER.info("Wrote %d row(s) to '%s'.", rows, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
