"""Book-store sales analysis (Task 4).

For every data/STORE* folder:
  * load users.csv, orders.parquet, books.yaml and clean them;
  * add paid_price (USD, EUR converted at 1.2) and date;
  * compute daily revenue, unique users, author sets, top author, best buyer;
  * save a matplotlib chart and a JSON summary consumed by the dashboard.

Usage:  python analysis/pipeline.py [data_dir] [out_dir]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

EUR_TO_USD = 1.2

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def parse_price(raw: str) -> float:
    """'$ 35', '30.0USD', 'EUR 26.50', '€22¢25', '46$99¢', 'USD 43.' -> USD float."""
    if raw is None or pd.isna(raw):
        return float("nan")
    s = str(raw).strip()
    is_eur = "EUR" in s.upper() or "€" in s
    parts = re.findall(r"\d+", s)
    if not parts:
        return float("nan")
    whole = parts[0]
    frac = parts[1] if len(parts) > 1 else "0"
    value = float(f"{whole}.{frac}")
    return value * EUR_TO_USD if is_eur else value


_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?")


def parse_timestamp(raw: str) -> pd.Timestamp:
    """Parse the ~100 mixed timestamp layouts found in orders.parquet."""
    if raw is None or pd.isna(raw):
        return pd.NaT
    s = str(raw).strip().lower()
    s = s.replace("a.m.", "am").replace("p.m.", "pm")
    s = re.sub(r"(\d)t(\d)", r"\1 \2", s)  # ISO 'T' separator

    m = _TIME_RE.search(s)
    if not m:
        return pd.NaT
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    rest = s[: m.start()] + " " + s[m.end():]
    ampm = re.search(r"\b(am|pm)\b", rest)
    if ampm:
        if ampm.group(1) == "pm" and hh < 12:
            hh += 12
        elif ampm.group(1) == "am" and hh == 12:
            hh = 0
        rest = rest[: ampm.start()] + rest[ampm.end():]

    if d := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", rest):            # 2025-06-25
        y, mo, dd = int(d.group(1)), int(d.group(2)), int(d.group(3))
    elif d := re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", rest):        # 06/25/25 (US)
        mo, dd, y = int(d.group(1)), int(d.group(2)), int(d.group(3))
    elif d := re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", rest):        # 25.06.2025 (EU)
        dd, mo, y = int(d.group(1)), int(d.group(2)), int(d.group(3))
    elif d := re.search(r"(\d{1,2})-([a-z]+)-(\d{4})", rest):           # 25-Jun-2025
        dd, mo, y = int(d.group(1)), MONTHS[d.group(2)[:3]], int(d.group(3))
    elif d := re.search(r"([a-z]{3})[a-z]*\s+(\d{1,2})\s+(\d{4})", rest):  # Wed Jun 25 2025
        mo, dd, y = MONTHS[d.group(1)], int(d.group(2)), int(d.group(3))
    else:
        return pd.NaT
    if y < 100:
        y += 2000
    try:
        return pd.Timestamp(year=y, month=mo, day=dd, hour=hh, minute=mm, second=ss)
    except ValueError:
        return pd.NaT


def norm_text(s) -> str | None:
    if s is None or pd.isna(s):
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


def norm_phone(s) -> str | None:
    if s is None or pd.isna(s):
        return None
    digits = re.sub(r"\D", "", str(s))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def author_set(raw) -> tuple[str, ...]:
    if raw is None or pd.isna(raw):
        return ()
    names = {norm_text(a) for a in str(raw).split(",")}
    return tuple(sorted(n for n in names if n))


# --------------------------------------------------------------------------- #
# Loading & cleaning
# --------------------------------------------------------------------------- #
def load_users(path: Path) -> pd.DataFrame:
    u = pd.read_csv(path, dtype={"phone": "string"})
    u["id"] = pd.to_numeric(u["id"], errors="coerce").astype("Int64")
    u = u.dropna(subset=["id"]).drop_duplicates()
    u["name"] = u["name"].map(norm_text)
    u["address"] = u["address"].map(norm_text)
    u["email"] = u["email"].map(norm_text).str.lower()
    u["phone"] = u["phone"].map(norm_phone)
    return u.drop_duplicates(subset="id").reset_index(drop=True)


def load_books(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    b = pd.DataFrame(raw)
    b.columns = [str(c).lstrip(":") for c in b.columns]
    b["id"] = pd.to_numeric(b["id"], errors="coerce").astype("Int64")
    b["year"] = pd.to_numeric(b["year"], errors="coerce").astype("Int64")
    for c in ("title", "author", "genre", "publisher"):
        b[c] = b[c].map(norm_text)
    b = b.dropna(subset=["id"]).drop_duplicates(subset="id")
    b["authors"] = b["author"].map(author_set)
    return b.reset_index(drop=True)


def load_orders(path: Path) -> pd.DataFrame:
    o = pd.read_parquet(path)
    for c in ("id", "user_id", "book_id", "quantity"):
        o[c] = pd.to_numeric(o[c], errors="coerce").astype("Int64")
    o["unit_price"] = o["unit_price"].map(parse_price).round(2)
    o["timestamp"] = pd.to_datetime(o["timestamp"].map(parse_timestamp))
    o["shipping"] = o["shipping"].map(lambda s: None if norm_text(s) in (None, "NULL", "nan") else norm_text(s))

    o = o.drop_duplicates()
    o = o.drop_duplicates(subset="id")
    o = o.dropna(subset=["id", "user_id", "book_id", "quantity", "unit_price", "timestamp"])
    o = o[(o["quantity"] > 0) & (o["unit_price"] > 0)]

    o["paid_price"] = (o["quantity"] * o["unit_price"]).astype(float).round(2)
    o["date"] = o["timestamp"].dt.normalize()
    o["year"] = o["timestamp"].dt.year
    o["month"] = o["timestamp"].dt.month
    o["day"] = o["timestamp"].dt.day
    return o.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# User reconciliation
# --------------------------------------------------------------------------- #
class DSU:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def reconcile_users(u: pd.DataFrame) -> pd.Series:
    """Map user id -> canonical person id.

    Two records belong to one person when at most one of the four fields
    (name, address, phone, email) differs, i.e. any three fields match.
    """
    fields = ["name", "address", "phone", "email"]
    dsu = DSU(u["id"].tolist())
    for skip in fields:
        key = [f for f in fields if f != skip]
        for _, grp in u.dropna(subset=key).groupby(key)["id"]:
            ids = grp.tolist()
            for other in ids[1:]:
                dsu.union(ids[0], other)
    return pd.Series({i: dsu.find(i) for i in u["id"]}, name="person_id")


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def analyse_store(store_dir: Path, out_dir: Path) -> dict:
    name = store_dir.name
    users = load_users(store_dir / "users.csv")
    books = load_books(store_dir / "books.yaml")
    orders_raw_n = len(pd.read_parquet(store_dir / "orders.parquet", columns=["id"]))
    orders = load_orders(store_dir / "orders.parquet")

    # 1. daily revenue
    daily = orders.groupby("date")["paid_price"].sum().round(2).sort_index()
    top5 = daily.sort_values(ascending=False).head(5)

    # 2. real unique users
    person = reconcile_users(users)
    users["person_id"] = users["id"].map(person)
    unique_users = int(users["person_id"].nunique())

    # 3. unique author sets
    author_sets = books["authors"][books["authors"].map(len) > 0]
    unique_author_sets = int(author_sets.nunique())

    # 4. most popular author set (by number of sold books)
    sold = orders.merge(books[["id", "authors"]], left_on="book_id", right_on="id",
                        suffixes=("", "_book"))
    by_set = sold.groupby("authors")["quantity"].sum().sort_values(ascending=False)
    best_count = int(by_set.iloc[0])
    top_authors = [list(a) for a, q in by_set.items() if q == best_count]

    # 5. best buyer across aliases
    orders["person_id"] = orders["user_id"].map(person)
    spend = orders.groupby("person_id")["paid_price"].sum().sort_values(ascending=False)
    best_person = spend.index[0]
    best_ids = sorted(int(i) for i in users.loc[users["person_id"] == best_person, "id"])
    best_profile = users[users["person_id"] == best_person][["id", "name", "address", "phone", "email"]]

    # 6. chart
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(daily.index, daily.values, color="#2a6fdb", linewidth=1.2)
    ax.set_title(f"{name} — daily revenue (USD)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Revenue, $")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / f"{name}_daily_revenue.png", dpi=110)
    plt.close(fig)

    return {
        "store": name,
        "quality": {
            "orders_raw": orders_raw_n,
            "orders_clean": len(orders),
            "users": len(users),
            "books": len(books),
            "users_missing_address": int(users["address"].isna().sum()),
            "books_missing_year": int(books["year"].isna().sum()),
            "books_missing_publisher": int(books["publisher"].isna().sum()),
        },
        "total_revenue": round(float(orders["paid_price"].sum()), 2),
        "total_orders": int(len(orders)),
        "books_sold": int(orders["quantity"].sum()),
        "date_range": [daily.index.min().strftime("%Y-%m-%d"), daily.index.max().strftime("%Y-%m-%d")],
        "top5_days": [{"date": d.strftime("%Y-%m-%d"), "revenue": round(float(v), 2)} for d, v in top5.items()],
        "unique_users": unique_users,
        "user_records": int(len(users)),
        "unique_author_sets": unique_author_sets,
        "top_authors": top_authors,
        "top_authors_sold": best_count,
        "top_author_sets_ranking": [
            {"authors": list(a), "sold": int(q)} for a, q in by_set.head(10).items()],
        "best_buyer": {
            "ids": best_ids,
            "total_spent": round(float(spend.iloc[0]), 2),
            "orders": int((orders["person_id"] == best_person).sum()),
            "profiles": best_profile.astype(object).where(best_profile.notna(), None).to_dict("records"),
        },
        "daily_revenue": [{"date": d.strftime("%Y-%m-%d"), "revenue": round(float(v), 2)} for d, v in daily.items()],
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "data"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "docs" / "data"
    stores = sorted(p for p in data_dir.iterdir() if p.is_dir())
    results = []
    for store in stores:
        r = analyse_store(store, out_dir)
        results.append(r)
        print(f"\n=== {r['store']} ===")
        print("Top 5 days:", ", ".join(f"{d['date']} (${d['revenue']:,.2f})" for d in r["top5_days"]))
        print("Unique users:", r["unique_users"], f"(from {r['user_records']} records)")
        print("Unique author sets:", r["unique_author_sets"])
        print("Most popular:", r["top_authors"], f"({r['top_authors_sold']} books)")
        print("Best buyer:", r["best_buyer"]["ids"], f"${r['best_buyer']['total_spent']:,.2f}")
    with open(out_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    # also a JS copy so the dashboard works when opened from file://
    with open(out_dir / "results.js", "w", encoding="utf-8") as f:
        f.write("window.STORE_RESULTS = ")
        json.dump(results, f, ensure_ascii=False)
        f.write(";\n")


if __name__ == "__main__":
    main()
