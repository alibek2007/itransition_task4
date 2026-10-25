# Task 4 — Bookstore sales analysis

Cleans and analyses the five book-store datasets in `data/STORE1 … STORE5`
(`users.csv`, `orders.parquet`, `books.yaml`) and publishes the results as a
static BI dashboard (`docs/`, served by GitHub Pages).

## Run

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # or: uv pip install -r requirements.txt
python analysis/pipeline.py          # writes docs/data/results.json, results.js and STOREn_daily_revenue.png
python -m http.server 8000 -d docs   # open http://localhost:8000
```

## Cleaning

| Field | Problem | Handling |
|---|---|---|
| `unit_price` | `$ 35`, `30.0USD`, `EUR 26.50`, `€22¢25`, `46$99¢`, `USD 43.` | currency detected (USD/`$` or EUR/`€`), first digit group = whole, second = cents; EUR × 1.2; rounded to cents |
| `timestamp` | ~100 layouts: ISO, `MM/DD/YY`, `DD.MM.YYYY`, `25-Jun-2025`, `Fri Apr 10 … 2026`, 12h `am/A.M.`, time before or after date, `,` `;` separators | regex tokeniser → `datetime64`; slash dates are US (2nd part > 12 occurs, 1st never), dot dates are EU (1st part > 12 occurs) |
| `shipping` | `NULL`, empty, NaN | normalised to null (not used in metrics) |
| ids / quantity | — | coerced to integers; rows with unparseable keys, non-positive qty/price, duplicate rows or ids are dropped |
| users | phone formats `(xxx) xxx-xxxx`, `xxx.xxx.xxxx`, …; missing addresses | phone → digits, e-mail lower-cased, whitespace collapsed, missing address kept as null |
| books | YAML `:key` symbols, missing year/publisher | keys stripped, year → nullable int, authors split on `,` into a sorted set |

`paid_price = quantity × unit_price` (USD), `date/year/month/day` derived from `timestamp`.

## Method

* **Unique users** — union-find over user records: two records are the same person if any
  three of *name, address, phone, e-mail* match (only one field may change between records).
  Matching is transitive, so a person who changed e-mail and later phone is still one person.
* **Author sets** — the distinct sorted tuples of authors per book.
* **Most popular author set** — sum of `quantity` sold per author set.
* **Best buyer** — total `paid_price` per reconciled person; all their `user_id`s are listed.

## Results

| Store | Top 5 days by revenue | Unique users | Author sets | Most popular | Best buyer |
|---|---|---|---|---|---|
| STORE1 | 2025-08-20, 2025-09-22, 2026-01-15, 2025-09-03, 2025-10-17 | 3221 | 324 | Darron Ernser & Miss Lorina Kertzmann | [48403, 48904, 50056] |
| STORE2 | 2025-11-16, 2025-12-12, 2025-12-10, 2025-09-19, 2025-11-19 | 3166 | 281 | Kenneth Hamill & Marcus McKenzie | [51014] |
| STORE3 | 2025-10-09, 2025-09-21, 2025-09-04, 2025-09-30, 2025-09-01 | 2955 | 307 | Loreta Metz | [52881, 53869, 54846] |
| STORE4 | 2025-11-24, 2025-11-17, 2025-11-28, 2025-11-13, 2025-09-21 | 2850 | 299 | Emil Rempel & Heriberto Kutch & Merle Rice | [53347, 54809] |
| STORE5 | 2025-10-20, 2025-11-28, 2025-09-27, 2025-10-17, 2025-12-05 | 2987 | 311 | Dulcie Bode | [52895, 53969] |

Matplotlib charts: `docs/data/STOREn_daily_revenue.png`.

## Dashboard

`docs/index.html` — Tabler (Bootstrap) + ApexCharts. One tab per store with KPI tiles
(unique users, author sets, most popular author, best buyer ids), interactive daily revenue
chart, top-5 days table, author ranking, reconciled best-buyer profiles and a data-quality note.
The right-hand **Data assistant** chat area answers questions about the data and is the
placeholder for the chat features of parts 2 and 3.
