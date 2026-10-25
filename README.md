# Bookstore Sales Analytics — Itransition Task 4

Data cleaning pipeline and BI-style dashboard for five bookstore datasets (`STORE1` … `STORE5`).

**Live dashboard:** https://alibek2007.github.io/itransition_task4/

---

## What it does

For every `data/STORE*` folder the pipeline:

1. Loads `orders.parquet`, `users.csv` and `books.yaml` into pandas.
2. Cleans the data — proper types, parsed dates, duplicates, missing and malformed values.
3. Adds `paid_price = quantity × unit_price` in USD (€1 = $1.2) and extracts `date` (year, month, day) from `timestamp`.
4. Computes:
   - top 5 days by revenue;
   - number of real unique users (after reconciling aliases);
   - number of unique author sets;
   - the most popular author (or author set);
   - the best buyer with all of their user ids;
   - a daily revenue chart.
5. Writes the results to `docs/data/` for the dashboard.

## Project structure

```
├── analysis/
│   └── pipeline.py        # loading, cleaning, analysis, charts
├── data/
│   └── STORE1 … STORE5/   # orders.parquet, users.csv, books.yaml
├── worker/                # Cloudflare Worker: AI chat backend (Gemini)
├── docs/                  # static dashboard (GitHub Pages)
│   ├── index.html
│   └── data/              # results.json, results.js, *_daily_revenue.png
├── requirements.txt
└── README.md
```

## How to run

```bash
pip install -r requirements.txt
python analysis/pipeline.py
```

This prints the answers for every store and regenerates `docs/data/`.
To view the dashboard locally, open `docs/index.html` in a browser.

Optional arguments: `python analysis/pipeline.py <data_dir> <out_dir>`

## Data cleaning

| Table | Problem | Solution |
|---|---|---|
| orders | `unit_price` is text in ~50 formats: `$ 35`, `30.0USD`, `EUR 26.50`, `€22¢25`, `46$99¢`, `USD 43.` | Regex parser: detect currency (`$`/`USD` or `€`/`EUR`), read dollars and cents, convert EUR × 1.2 |
| orders | `timestamp` is text in 130+ layouts: ISO, `A.M./pm`, month names, `;` and `,` separators, time before or after the date | Custom parser: extract time and AM/PM, then the date by pattern |
| orders | `shipping` contains `""`, `NULL`, NaN | Normalized to missing |
| users | Phones in 4 formats: `(313) 970-1817`, `313.970.1817`, `313-970-1817`, `313 970 1817` | Digits only |
| users | Blank addresses (`""`, `" "`), extra spaces, mixed-case emails | Trimmed, blanks → missing, emails lower-cased |
| books | `year` contains `-1`, `0`, `-`, `NULL`, blanks | Converted to number; invalid years → missing |
| books | `author` is a comma-separated list | Split into a sorted tuple of names |
| all | Possible duplicates | `drop_duplicates()` on rows and ids |

All orders parse successfully — no rows are dropped in any store.

## Assumptions

- **Currency:** €1 = $1.2. `paid_price` is calculated from the exact converted price and rounded to cents.
- **Dates:** slash dates are US `MM/DD/YY`; dot dates are European `DD.MM.YYYY`. Verified from the data: in slash dates the first number never exceeds 12, in dot dates the first number goes up to 31.
- **Same user:** two records belong to one person when **at least 3 of the 4 fields** (name, address, phone, email) match after normalization — i.e. only one field was changed. Chains (A ~ B, B ~ C) are merged with a Union-Find (disjoint set) structure.
- **Author sets:** `John, Paul` and `Paul, John` are the same set; `John` alone and `Paul` alone are different sets.
- **Popularity:** total number of copies sold (`quantity`), not number of orders. Ties are reported in full.
- **Best buyer:** total spending is summed per reconciled person, so spending under different aliases is combined.

## Results

| | STORE1 | STORE2 | STORE3 | STORE4 | STORE5 |
|---|---|---|---|---|---|
| Orders | 10,493 | 9,181 | 9,280 | 10,877 | 9,714 |
| Total revenue | $739,353.52 | $668,103.35 | $681,625.41 | $778,289.22 | $704,421.69 |
| User records | 3,394 | 3,319 | 3,107 | 3,008 | 3,158 |
| **Unique users** | **3,221** | **3,166** | **2,955** | **2,850** | **2,987** |
| **Unique author sets** | **324** | **281** | **307** | **299** | **311** |
| **Most popular** | Darron Ernser & Miss Lorina Kertzmann | Kenneth Hamill & Marcus McKenzie | Loreta Metz | Emil Rempel & Heriberto Kutch & Merle Rice | Dulcie Bode |
| Copies sold | 173 | 176 | 155 | 198 | 169 |
| **Best buyer ids** | `[48403, 48904, 50056]` | `[51014]` | `[52881, 53869, 54846]` | `[53347, 54809]` | `[52895, 53969]` |
| Best buyer spent | $1,317.59 | $1,131.07 | $1,398.65 | $1,265.65 | $1,365.91 |

### Top 5 days by revenue

| # | STORE1 | STORE2 | STORE3 | STORE4 | STORE5 |
|---|---|---|---|---|---|
| 1 | 2025-08-20 — $3,719.35 | 2025-11-16 — $3,789.61 | 2025-10-09 — $3,551.19 | 2025-11-24 — $4,372.46 | 2025-10-20 — $3,491.85 |
| 2 | 2025-09-22 — $3,587.94 | 2025-12-12 — $3,127.15 | 2025-09-21 — $3,243.00 | 2025-11-17 — $3,818.29 | 2025-11-28 — $3,268.26 |
| 3 | 2026-01-15 — $3,307.38 | 2025-12-10 — $3,024.52 | 2025-09-04 — $3,041.39 | 2025-11-28 — $3,444.83 | 2025-09-27 — $3,190.50 |
| 4 | 2025-09-03 — $3,263.25 | 2025-09-19 — $2,938.86 | 2025-09-30 — $3,017.60 | 2025-11-13 — $3,401.07 | 2025-10-17 — $3,165.18 |
| 5 | 2025-10-17 — $3,252.32 | 2025-11-19 — $2,915.20 | 2025-09-01 — $2,937.42 | 2025-09-21 — $3,303.44 | 2025-12-05 — $3,121.92 |

Daily revenue charts: `docs/data/STORE*_daily_revenue.png` and the interactive charts on the dashboard.

## Dashboard

A static page built with [Tabler](https://tabler.io/) (UI template) and [ApexCharts](https://apexcharts.com/), hosted on GitHub Pages:

- one tab per store;
- KPI cards: unique users, unique author sets, revenue, orders;
- top 5 days table, most popular author(s), best buyer ids;
- interactive daily revenue chart;
- **AI chat area** (Google Gemini) — ask anything about the stores; see [AI chat](#ai-chat-parts-2--3).

## AI chat (parts 2 & 3)

The chat area on the dashboard is answered by **Google Gemini**.

```
Dashboard (GitHub Pages)  ──POST {question, store, history}──►  Cloudflare Worker  ──►  Gemini API
          ▲                                                    (holds API key)              │
          └─────────────────────────────── answer ──────────────────────────────────────────┘
```

- `worker/worker.js` — a Cloudflare Worker that loads `docs/data/results.json`, turns it into a compact data summary and sends it to Gemini together with the question and recent chat history.
- **Grounded answers:** the system prompt tells the model to answer only from this data and never invent numbers; it can still calculate (comparisons, monthly totals, averages).
- **Security:** the Gemini API key is stored as a Worker secret, not in the public page. CORS allows only the dashboard origin.
- **Fallback:** if the AI is unavailable, the chat answers with the built-in rule-based responses.

Deploy the Worker:

```bash
cd worker
npx wrangler login
npx wrangler secret put GEMINI_API_KEY
npx wrangler deploy
```

## Tech stack

Python · pandas · PyArrow · PyYAML · matplotlib · HTML/JS · Tabler · ApexCharts · GitHub Pages · Cloudflare Workers · Google Gemini