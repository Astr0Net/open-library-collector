# Open Library Collector

**Language / زبان:** [English](#english) | [فارسی](#persian)

---

<a id="english"></a>

# 🇬🇧 English

Collect book metadata from the [Open Library Public Search API](https://openlibrary.org/developers/api) and export it to a clean, Excel-ready CSV file.

The script fetches **50 books** for a search query, keeps only the titles whose **first publication year is strictly greater than 2000**, and writes the result to a CSV file encoded with `utf-8-sig` (UTF-8 with a byte-order mark), so the file opens without mojibake in Microsoft Excel.

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

Run with the defaults — query `programming`, fetch 50 books, keep those first published after 2000, write `openlibrary_books.csv`:

```bash
python openlibrary_collector.py
```

Expected console output:

```text
INFO: Fetched 50 book(s) for query 'programming'.
INFO: 52 of 50 book(s) were first published after 2000.
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
| `--limit` | `50` | Maximum number of valid books to fetch. |
| `--min-year` | `2000` | Keep books whose `first_publish_year` is **strictly greater** than this value. |
| `--output` | `openlibrary_books.csv` | Destination CSV file, written with `utf-8-sig`. |
| `--timeout` | `30` | Per-request HTTP timeout, in seconds. |
| `--verbose` | off | Enable debug level logging. |
| `-h`, `--help` | — | Show the help message and exit. |

The script is also importable as a library:

```python
from openlibrary_collector import fetch_books, filter_books, write_csv

books = fetch_books(query="science", limit=50)
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

---

<a id="persian"></a>

<div dir="rtl" align="right">

# 🇮🇷 فارسی

# جمع‌آورنده‌ی کتاب‌های Open Library

اطلاعات متادیتای کتاب‌ها را از [API عمومی جستجوی Open Library](https://openlibrary.org/developers/api) دریافت می‌کند و آن را به یک فایل CSV تمیز و آماده‌ی اکسل خروجی می‌دهد.

این اسکریپت برای یک عبارت جستجو **۵۰ کتاب** دریافت می‌کند، فقط کتاب‌هایی را نگه می‌دارد که **سال اولین انتشارشان به‌طور دقیق بزرگ‌تر از ۲۰۰۰** است، و نتیجه را در فایل CSV با انکودینگ `utf-8-sig` (یعنی UTF-8 همراه با BOM) ذخیره می‌کند تا فایل در Microsoft Excel بدون کاراکترهای خراب (mojibake) باز شود.

---

## فهرست مطالب

- [ویژگی‌ها](#fa-features)
- [پیش‌نیازها](#fa-prerequisites)
- [نصب](#fa-installation)
- [نحوه‌ی استفاده](#fa-usage)
- [گزینه‌های خط فرمان](#fa-options)
- [قالب خروجی](#fa-output)
- [ساختار پروژه](#fa-structure)
- [نحوه‌ی کار](#fa-how)
- [مدیریت خطا](#fa-errors)
- [عیب‌یابی](#fa-troubleshooting)
- [مجوز](#fa-license)

---

<a id="fa-features"></a>

## ویژگی‌ها

- دریافت اطلاعات کتاب‌ها از `https://openlibrary.org/search.json` تنها با یک وابستگی خارجی (`requests`).
- فیلتر نتایج بر اساس `first_publish_year > 2000` (بزرگ‌تر اکید؛ یعنی کتابی که در سال ۲۰۰۰ منتشر شده حذف می‌شود).
- مدیریت خودکار صفحه‌بندی (API در هر صفحه حداکثر ۱۰۰ سند برمی‌گرداند).
- تلاش مجدد برای خطاهای گذرای شبکه با backoff نمایی، پیش از تسلیم شدن.
- رد کردن رکوردهای معیوب به‌جای کرش کردن هنگام نبود یا نادرست بودن نوع یک فیلد.
- نوشتن CSV با UTF-8 همراه BOM (`utf-8-sig`) برای سازگاری کامل با اکسل.
- ارائه‌ی رابط خط فرمان با مقادیر پیش‌فرض منطقی و قابل تغییر.

<a id="fa-prerequisites"></a>

## پیش‌نیازها

| نیازمندی | نسخه |
| -------- | ---- |
| Python   | ۳.۸ یا بالاتر (توسعه و تست روی ۳.۱۴) |
| `requests` | ۲.۳۱.۰ یا بالاتر |

هیچ بسته‌ی خارجی دیگری لازم نیست — کتابخانه‌ی استاندارد پایتون ماژول‌های `csv`، `argparse`، `logging`، `dataclasses` و `json` را فراهم می‌کند. ثبت‌نام برای دریافت کلید API هم لازم نیست.

<a id="fa-installation"></a>

## نصب

**۱. کلون کردن مخزن**

```bash
git clone https://github.com/<your-username>/open-library-collector.git
cd open-library-collector
```

**۲. ساخت و فعال‌سازی محیط مجازی**

ویندوز (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / لینوکس:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**۳. نصب وابستگی‌ها**

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

اگر `requests` از قبل در محیط شما نصب باشد، اسکریپت بدون مرحله‌ی `requirements.txt` هم اجرا می‌شود (`pip install requests`).

<a id="fa-usage"></a>

## نحوه‌ی استفاده

اجرا با مقادیر پیش‌فرض — عبارت جستجوی `programming`، دریافت ۵۵ کتاب، نگه داشتن کتاب‌هایی که اولین انتشارشان بعد از ۲۰۰۰ بوده و نوشتن در `openlibrary_books.csv`:

```bash
python openlibrary_collector.py
```

خروجی مورد انتظار در کنسول:

```text
INFO: Fetched 50 book(s) for query 'programming'.
INFO: 52 of 50 book(s) were first published after 2000.
INFO: Wrote 52 row(s) to 'openlibrary_books.csv'.
```

حالت‌های رایج:

```bash
# موضوع متفاوت، نمونه‌ی بزرگ‌تر
python openlibrary_collector.py --query science --limit 200

# فقط کتاب‌هایی که اولین انتشارشان بعد از ۲۰۱۵ است
python openlibrary_collector.py --min-year 2015

# انتخاب فایل خروجی
python openlibrary_collector.py --output data/science_books.csv

# لاگ دیباگ (رکوردهای ردشده و هر تلاش مجدد را نشان می‌دهد)
python openlibrary_collector.py --verbose
```

<a id="fa-options"></a>

## گزینه‌های خط فرمان

| گزینه | پیش‌فرض | توضیح |
| ----- | ------- | ----- |
| `--query` | `programming` | عبارت جستجو که به Open Library ارسال می‌شود. |
| `--limit` | `50` | حداکثر تعداد کتاب‌های معتبر برای دریافت. |
| `--min-year` | `2000` | کتاب‌هایی نگه داشته می‌شوند که `first_publish_year` آن‌ها **به‌طور اکید بزرگ‌تر** از این مقدار باشد. |
| `--output` | `openlibrary_books.csv` | فایل CSV مقصد که با `utf-8-sig` نوشته می‌شود. |
| `--timeout` | `30` | مهلت هر درخواست HTTP بر حسب ثانیه. |
| `--verbose` | خاموش | فعال‌سازی لاگ در سطح debug. |
| `-h`, `--help` | — | نمایش راهنما و خروج. |

این اسکریپت به‌عنوان کتابخانه هم قابل import است:

```python
from openlibrary_collector import fetch_books, filter_books, write_csv

books = fetch_books(query="science", limit=50)
recent = filter_books(books, min_year=2000)
write_csv(recent, "science_books.csv")
```

<a id="fa-output"></a>

## قالب خروجی

یک فایل CSV شامل یک ردیف هدر و به‌دنبال آن یک ردیف برای هر کتاب.

| ستون | نوع | توضیح |
| ---- | --- | ----- |
| `title` | متن | عنوان کتاب. |
| `author` | متن | نام نویسنده(ها) با جداکننده‌ی کاما، یا `Unknown`. |
| `first_publish_year` | عدد صحیح | سال اولین انتشار؛ فیلدی که فیلتر روی آن انجام می‌شود. |
| `edition_count` | عدد صحیح | تعداد ویرایش‌های شناخته‌شده در Open Library (اگر نامعلوم باشد `0`). |
| `language` | متن | کد زبان(ها) با جداکننده‌ی کاما، یا `Unknown`. |
| `ratings_average` | متن | میانگین امتیاز خوانندگان با دو رقم اعشار، یا خالی اگر امتیازی ثبت نشده باشد. |
| `isbn` | متن | حداکثر سه ISBN با جداکننده‌ی کاما. |
| `openlibrary_key` | متن | کلید اثر در Open Library، مثلاً `/works/OL45804W`. |

نمونه‌ی خروجی:

```csv
title,author,first_publish_year,edition_count,language,ratings_average,isbn,openlibrary_key
The Pragmatic Programmer,Andrew Hunt and David Thomas,1999,32,eng,4.20,9780135957059,/works/OL1164653W
Clean Code,Robert C. Martin,2008,45,eng,4.31,9780132350884,/works/OL17593266W
Design Patterns,Erich Gamma and Richard Helm,1994,54,eng,4.24,9780201633610,/works/OL17981919W
```

در یک اجرای واقعی با عبارت `programming`، عناوینی مانند *Clean Code*، *Refactoring*، *Python Crash Course* و *Learning Python* غالب هستند، چون کتاب‌های کلاسیک برنامه‌نویسی قبل از ۲۰۰۱ فیلتر می‌شوند.

جزئیات انکودینگ:

- فایل با `encoding="utf-8-sig"` نوشته می‌شود، بنابراین با سه بایت `EF BB BF` (همان BOM در UTF-8) شروع می‌شود. اکسل با استفاده از آن UTF-8 را تشخیص می‌دهد و عناوین دارای اعراب و غیر لاتین را درست نمایش می‌دهد؛ `pandas.read_csv()` و ابزارهای دیگر هم آن را به‌صورت شفاف مدیریت می‌کنند.
- ردیف‌ها با پایان‌دهنده‌ی خط `\r\n` نوشته می‌شوند (از طریق `csv.DictWriter` و `newline=""`) که قالب مورد انتظار اکسل است.
- پوشه‌ی خروجی باید از قبل وجود داشته باشد؛ مسیر ناموجود به‌صورت خطا گزارش می‌شود و بی‌سروصدا ساخته نمی‌شود.

<a id="fa-structure"></a>

## ساختار پروژه

```text
open-library-collector/
├── openlibrary_collector.py   # نقطه‌ی ورود: دریافت، فیلتر، خروجی CSV، رابط خط فرمان
├── requirements.txt           # وابستگی پین‌شده (requests)
├── README.md                  # همین فایل
└── openlibrary_books.csv      # خروجی تولیدشده (در git ردیابی نمی‌شود)
```

<a id="fa-how"></a>

## نحوه‌ی کار

1. **دریافت (Fetch)** — تابع `fetch_books()` یک `requests.Session` با `User-Agent` توصیفی می‌سازد، از طریق پارامتر `fields` فقط فیلدهای لازم را درخواست می‌کند و صفحه‌به‌صفحه نتایج را می‌خواند (اندازه‌ی صفحه حداکثر ۱۰۰، سقف API) تا زمانی که `--limit` رکورد معتبر جمع شود یا به `numFound` برسد.
2. **نرمال‌سازی (Normalise)** — هر سند خام به یک dataclass ثابت (frozen) با نام `Book` تبدیل می‌شود. رکوردهای بدون عنوان قابل‌استفاده، و رکوردهایی که `first_publish_year` آن‌ها وجود ندارد یا عدد صحیح نیست، رد می‌شوند و در سطح debug لاگ می‌شوند.
3. **فیلتر (Filter)** — تابع `filter_books()` فقط رکوردهایی را نگه می‌دارد که `first_publish_year > min_year` باشد؛ مقایسه‌ی اکید است، پس خود سال آستانه حذف می‌شود.
4. **خروجی (Export)** — تابع `write_csv()` فیلدهای `Book` را با `csv.DictWriter` در فایل `utf-8-sig` می‌نویسد و وجود ردیف هدر و quoting درست برای عناوین دارای کاما یا نقل‌قول را تضمین می‌کند.

<a id="fa-errors"></a>

## مدیریت خطا

| وضعیت | رفتار |
| ----- | ----- |
| خطای اتصال یا timeout | تا ۳ بار با backoff نمایی (۲ و ۴ ثانیه) تلاش مجدد می‌شود، سپس به‌صورت `ApiError` گزارش شده و با کد خروج `1` پایان می‌یابد. |
| پاسخ HTTP با کد 4xx/5xx | `raise_for_status()` خطا می‌دهد؛ کد HTTP 400 بلافاصله متوقف می‌شود چون تلاش مجدد بی‌فایده است. |
| بدنه‌ی معیوب یا غیر JSON | تشخیص داده می‌شود، تلاش مجدد انجام می‌شود، سپس به‌صورت `ApiError` گزارش می‌شود. |
| JSON سطح بالا از نوع object نباشد | به‌صورت `ApiError` گزارش می‌شود. |
| نبود کلید `docs` یا خالی بودن آن | مجموعه‌ی نتایج خالی در نظر گرفته می‌شود؛ اجرا با کد خروج `1` تمیز پایان می‌یابد. |
| نبود یا نامعتبر بودن `first_publish_year` یا `title` | رکورد رد می‌شود، در سطح debug لاگ می‌شود و بقیه‌ی رکوردها همچنان خروجی گرفته می‌شوند. |
| فیلتر هیچ کتابی را نگه ندارد | با کد `1` خارج می‌شود و پیشنهاد می‌دهد `--min-year` را کمتر کنید یا `--query` را عوض کنید؛ هیچ فایل خالی‌ای نوشته نمی‌شود. |
| مسیر خروجی قابل نوشتن نباشد | `OSError` گرفته و گزارش می‌شود؛ کد خروج `1`. |
| مقدار نامعتبر `--limit` (صفر یا منفی) | `ValueError` گرفته و گزارش می‌شود؛ کد خروج `2`. |

کدهای خروج: `0` موفقیت، `1` خطای اجرا یا API، `2` آرگومان نامعتبر.

<a id="fa-troubleshooting"></a>

## عیب‌یابی

**`requests.exceptions.ConnectionError` / timeout** — Open Library ترافیک ناگهانی را محدود می‌کند و ممکن است از برخی شبکه‌ها در دسترس نباشد. اسکریپت از قبل سه بار تلاش مجدد می‌کند؛ بعداً دوباره اجرا کنید یا `--timeout` را افزایش دهید.

**`ERROR: No book matched the filter`** — همه‌ی نتایج در سال آستانه یا قبل از آن منتشر شده‌اند. یک `--query` گسترده‌تر یا `--min-year` کمتر امتحان کنید.

**کاراکترهای خراب در اکسل** — مطمئن شوید فایل `.csv` تولیدشده را مستقیماً باز می‌کنید و آن را با یک code page قدیمی import نمی‌کنید. BOM از قبل به اکسل می‌گوید که از UTF-8 استفاده کند.

**تعداد ردیف‌های کم** — `--limit` تعداد رکوردهای *معتبر* را پس از حذف رکوردهای معیوب می‌شمارد، بنابراین در یک مجموعه‌ی نتایج خیلی کوچک ممکن است ردیف‌های کمتری از تعداد درخواستی تولید شود.

<a id="fa-license"></a>

## مجوز

تحت مجوز MIT منتشر شده است.

</div>