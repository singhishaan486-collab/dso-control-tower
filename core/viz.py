"""Data preparation for the richer charts and views. No model logic: this only reshapes and labels results
that other modules already computed, so pages and core/charts.py can show them in plain English."""
import pandas as pd

# Association rule items in plain words. Tone: "risk" for conditions that go wrong, "good" for clean
# conditions, "info" for descriptors such as client type or attendance method.
_FIXED_ITEMS = {
    "HC_GAP>5": ("Headcount gap over 5%", "risk", "the headcount gap is over 5%"),
    "OT_UNAPPROVED": ("OT not pre-approved", "risk", "OT is not pre-approved"),
    "VAR>20h": ("Hours mismatch over 20 h", "risk", "our hours and the client's differ by more than 20"),
    "DOCS_MISSING": ("Documents missing", "risk", "documents are missing"),
    "RATE_MISMATCH": ("Rate mismatch", "risk", "the billed rate does not match the contract"),
    "TS=Signed": ("Timesheet signed", "good", "the timesheet is signed"),
    "TS=Remarks": ("Signed with remarks", "risk", "the timesheet is signed with remarks"),
    "TS=Unsigned": ("Timesheet unsigned", "risk", "the timesheet is unsigned"),
}
_LPO_CLAUSES = {"Valid": "the LPO is valid", "Not yet renewed": "the LPO is not yet renewed",
                "Insufficient balance": "the LPO balance is insufficient", "Missing": "the LPO is missing"}
_ATTENDANCE_CLAUSES = {"Paper": "attendance is on paper", "Biometric": "attendance is biometric",
                       "App": "attendance is by app"}
_OWNERSHIP_CLAUSES = {"Government": "the client is a government entity",
                      "Semi-government": "the client is a semi-government entity",
                      "Private large": "the client is a large private company", "Private SME": "the client is a private SME"}

OUTCOMES = {
    "DISPUTE": dict(label="Dispute", style="filled", clause="end in a dispute", short="a dispute"),
    "LATE": dict(label="Paid late", style="outline", clause="are paid late", short="paying late"),
    "LATE_30+": dict(label="Over 30 days late", style="outline", clause="are paid more than 30 days late",
                     short="paying over 30 days late"),
}

# Dispute reason codes in plain words. Every reason is something that went wrong, so all are risk chips.
REASON_LABELS = {
    "TS_MISMATCH": "Hours mismatch", "OT_UNAPPROVED": "OT not pre-approved", "HC_DISCREPANCY": "Headcount gap",
    "LPO_ISSUE": "LPO problem", "DOCS_MISSING": "Documents missing", "RATE_DISPUTE": "Rate dispute",
    "SLA_PENALTY": "SLA penalty", "SERVICE_QUALITY": "Service quality",
}


def lower(text: str) -> str:
    """Public name for the acronym-safe lower case below."""
    return _lower(text)


def _lower(text: str) -> str:
    """Lower case except acronyms, so 'Private SME' becomes 'private SME'."""
    return " ".join(w if w.isupper() and len(w) > 1 else w.lower() for w in str(text).split())


def item_info(item: str) -> tuple[str, str, str]:
    """(chip label, tone, sentence clause) for one rule item."""
    if item in _FIXED_ITEMS:
        return _FIXED_ITEMS[item]
    prefix, _, value = item.partition("=")
    if prefix == "LPO":
        tone = "good" if value == "Valid" else "risk"
        return f"LPO: {value}", tone, _LPO_CLAUSES.get(value, f"the LPO status is {_lower(value)}")
    if prefix == "ATT":
        return f"Attendance: {value}", "info", _ATTENDANCE_CLAUSES.get(value, f"attendance is {_lower(value)}")
    if prefix == "OWN":
        return f"Client: {value}", "info", _OWNERSHIP_CLAUSES.get(value, f"the client is {_lower(value)}")
    return item.replace("_", " ").capitalize(), "info", item.replace("_", " ").lower()


def _join(clauses: list[str]) -> str:
    return clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + " and " + clauses[-1]


def rules_frame(rules: pd.DataFrame) -> pd.DataFrame:
    """Adds plain-English columns to dg.outcome_rules output. The normal rate is confidence divided by lift,
    which is the outcome's base rate, so nothing is recalculated from the data."""
    out = rules.copy()
    items = out["if"].str.split(" + ", regex=False)
    out["items"] = items
    out["outcome_label"] = out["then"].map(lambda t: OUTCOMES.get(t, {}).get("label", t))
    out["normal_rate"] = out["confidence"] / out["lift"]
    out["plain_if"] = items.map(lambda xs: " + ".join(item_info(x)[0] for x in xs))
    out["sentence"] = [
        f"When {_join([item_info(x)[2] for x in xs])}, {conf:.1%} of invoices "
        f"{OUTCOMES.get(then, {}).get('clause', 'have this outcome')}. Normal is {normal:.1%}."
        for xs, then, conf, normal in zip(items, out["then"], out["confidence"], out["normal_rate"])]
    out["has_ownership"] = items.map(lambda xs: any(x.startswith("OWN=") for x in xs))
    return out


def ownership_insight(rules: pd.DataFrame) -> str | None:
    """How many late rules name a client ownership type, against the dispute rules. Built from the live rules."""
    frame = rules_frame(rules) if "has_ownership" not in rules else rules
    late = frame[frame["then"] == "LATE"]
    dispute = frame[frame["then"] == "DISPUTE"]
    if late.empty or dispute.empty:
        return None
    late_share, dispute_share = late["has_ownership"].mean(), dispute["has_ownership"].mean()
    text = (f"{int(late['has_ownership'].sum())} of {len(late)} late payment rules name a client ownership type, "
            f"against {int(dispute['has_ownership'].sum())} of {len(dispute)} dispute rules.")
    if late_share - dispute_share >= 0.2:
        text += (" Paying late follows who the client is, while disputes follow what went wrong on the invoice, "
                 "which is something the team can fix before sending.")
    elif dispute_share - late_share >= 0.2:
        text += " Disputes lean more on client type than late payment does."
    return text


# Descriptive: days to pay distribution ------------------------------------------------------------------------

BOX_GROUPS = {"Client ownership": "client_ownership", "Sector": "sector", "Service line": "service_line",
              "Emirate": "emirate"}


def paid_days(inv: pd.DataFrame) -> pd.DataFrame:
    """Paid invoices with the columns the days to pay box plot needs."""
    paid = inv[inv["invoice_status"] == "Paid"]
    return paid[["invoice_id", "client_id", *BOX_GROUPS.values(), "dispute_raised", "days_to_pay"]].copy()


def box_stats(paid: pd.DataFrame, by: str, split: bool) -> pd.DataFrame:
    """Median, quartiles and mean days to pay per group (and per dispute status when split). Sorted by median."""
    keys = [by, "dispute_raised"] if split else [by]
    stats = paid.groupby(keys)["days_to_pay"].agg(
        invoices="size", mean_days="mean", q1_days=lambda s: s.quantile(0.25), median_days="median",
        q3_days=lambda s: s.quantile(0.75)).reset_index()
    order = paid.groupby(by)["days_to_pay"].median().sort_values(ascending=False).index
    stats[by] = pd.Categorical(stats[by], categories=order, ordered=True)
    return stats.sort_values(keys).reset_index(drop=True)


# Descriptive: receivables hierarchy ---------------------------------------------------------------------------

SUNBURST_MEASURES = {"Open receivables": "open_aed", "Overdue": "overdue_aed", "Invoiced (AED)": "invoiced_aed"}


def sunburst_frame(inv: pd.DataFrame, snapshot: pd.Timestamp, measure: str, names=None) -> pd.DataFrame:
    """Ownership, then sector, then client, with the chosen amount as the size. Open and overdue follow the same
    rule as the KPIs: open means unpaid, overdue means open and past the due date on the snapshot date.
    overdue_share (overdue over open) colours each node. Parents carry the sum of their children."""
    is_open = inv["invoice_status"] == "Open"
    df = inv.assign(invoiced_aed=inv["invoice_amount_aed"],
                    open_aed=inv["invoice_amount_aed"].where(is_open, 0.0),
                    overdue_aed=inv["invoice_amount_aed"].where(is_open & (inv["due_date"] < snapshot), 0.0))
    amounts = ["invoiced_aed", "open_aed", "overdue_aed"]
    leaf = df.groupby(["client_ownership", "sector", "client_id"], observed=True)[amounts].sum().reset_index()
    leaf = leaf[leaf[measure] > 0]
    rows = []
    for level, keys in enumerate([["client_ownership"], ["client_ownership", "sector"],
                                  ["client_ownership", "sector", "client_id"]]):
        part = leaf.groupby(keys, observed=True)[amounts].sum().reset_index()
        for _, r in part.iterrows():
            path = [str(r[k]) for k in keys]
            label = path[-1]
            rows.append(dict(id="/".join(path), parent="/".join(path[:-1]), label=label,
                             parent_label=path[-2] if len(path) > 1 else "all clients", level=level,
                             client_name=(names.get(path[-1], "") if level == 2 and names is not None else ""),
                             invoiced_aed=r["invoiced_aed"], open_aed=r["open_aed"], overdue_aed=r["overdue_aed"]))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["value"] = out[measure]
    out["overdue_share"] = (out["overdue_aed"] / out["open_aed"]).where(out["open_aed"] > 0, 0.0)
    return out


# Explorer: settled months only ---------------------------------------------------------------------------------

OWNERSHIP_ORDER = ["Government", "Semi-government", "Private large", "Private SME"]
MIX_GROUPS = {"on_time_share": "On time, no dispute", "late_share": "Late, no dispute",
              "disputed_share": "Disputed"}


def settled(inv: pd.DataFrame, end_month: str) -> pd.DataFrame:
    """Paid invoices from service months up to end_month, so recent unpaid invoices do not bias the picture."""
    return inv[(inv["service_month"].astype(str) <= end_month) & (inv["invoice_status"] == "Paid")].copy()


def client_summary(df: pd.DataFrame, names=None) -> pd.DataFrame:
    """One row per client: invoices, late rate, average days to pay, dispute rate and invoiced AED."""
    out = df.groupby("client_id").agg(
        client_ownership=("client_ownership", "first"), sector=("sector", "first"),
        invoices=("invoice_id", "size"), late_rate=("paid_late", "mean"), mean_days_to_pay=("days_to_pay", "mean"),
        dispute_rate=("dispute_raised", "mean"), invoiced_aed=("invoice_amount_aed", "sum")).reset_index()
    out.insert(1, "client_name", out["client_id"].map(names) if names is not None else "")
    return out


def outcome_mix(df: pd.DataFrame, names=None) -> pd.DataFrame:
    """Each client's invoices split into three groups that never overlap: disputed; late and not disputed;
    on time and not disputed. The three shares add up to 1."""
    disputed = df["dispute_raised"] == 1
    late = (df["paid_late"] == 1) & ~disputed
    on_time = ~disputed & ~late
    mix = df.assign(on_time=on_time, late=late, disputed=disputed).groupby("client_id").agg(
        client_ownership=("client_ownership", "first"), invoices=("invoice_id", "size"),
        invoiced_aed=("invoice_amount_aed", "sum"), on_time_share=("on_time", "mean"),
        late_share=("late", "mean"), disputed_share=("disputed", "mean")).reset_index()
    mix.insert(1, "client_name", mix["client_id"].map(names) if names is not None else "")
    return mix


def client_monthly(df: pd.DataFrame, window: int = 3, min_invoices: int = 3) -> tuple[pd.DataFrame, int]:
    """Rolling window of service months per client: late rate, average days to pay and invoiced AED.
    Months a client did not bill count as empty, so the window is always calendar months. A client-month is
    kept only when the window holds at least min_invoices settled invoices. Returns the frame and how many
    client-months were skipped."""
    months = sorted(df["service_month"].astype(str).unique())
    monthly = (df.assign(service_month=df["service_month"].astype(str))
               .groupby(["client_id", "service_month"])
               .agg(invoices=("invoice_id", "size"), late=("paid_late", "sum"), days=("days_to_pay", "sum"),
                    invoiced_aed=("invoice_amount_aed", "sum")))
    owners = df.groupby("client_id")["client_ownership"].first()
    rows, skipped = [], 0
    for client in monthly.index.get_level_values(0).unique():
        part = monthly.loc[client].reindex(months, fill_value=0)
        rolled = part.rolling(window, min_periods=window).sum()
        first_billed = part.index[part["invoices"] > 0][0]
        for month, r in rolled.iterrows():
            if month < first_billed or pd.isna(r["invoices"]):
                continue
            if r["invoices"] < min_invoices:
                skipped += 1
                continue
            rows.append(dict(client_id=client, client_ownership=owners[client], month=month,
                             invoices=int(r["invoices"]), late_rate=r["late"] / r["invoices"],
                             mean_days_to_pay=r["days"] / r["invoices"], invoiced_aed=r["invoiced_aed"]))
    return pd.DataFrame(rows), skipped


def reason_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Dispute reasons on the given invoices, in plain words. An invoice can carry more than one reason."""
    reasons = df.loc[df["dispute_raised"] == 1, "dispute_reasons"].dropna().str.split("; ").explode()
    reasons = reasons[reasons.fillna("") != ""]
    counts = reasons.map(lambda r: REASON_LABELS.get(r, r)).value_counts().rename_axis("reason")
    return counts.rename("disputes").reset_index()


def sector_mix(df: pd.DataFrame) -> pd.DataFrame:
    """Share of invoiced AED by sector."""
    mix = df.groupby("sector")["invoice_amount_aed"].sum()
    return (mix / mix.sum()).rename("share").rename_axis("sector").reset_index()


# Prescriptive: two levers together ------------------------------------------------------------------------------

GRID_STEPS = (0.0, 0.25, 0.5, 0.75, 1.0)
_WORKER: dict = {}


def _init_worker(inv, dispute_model, days_model) -> None:
    _WORKER.update(inv=inv, dispute_model=dispute_model, days_model=days_model)


def _grid_cell(args) -> dict:
    """One cell of the grid: the existing what-if simulator, unchanged, with two levers adopted."""
    from core import prescriptive as pr
    lever_a, share_a, lever_b, share_b, signoff_days = args
    sim = pr.simulate(_WORKER["inv"], _WORKER["dispute_model"], _WORKER["days_model"],
                      {lever_a: share_a, lever_b: share_b}, signoff_days)
    return dict(lever_a=lever_a, adoption_a=share_a, lever_b=lever_b, adoption_b=share_b,
                dso_change_days=sim["dso_change"], cash_released_aed=sim["cash_released"],
                disputes_per_month_change=sim["after"]["disputes_per_month"] - sim["before"]["disputes_per_month"])


def _grid_cell_with_data(args) -> dict:
    inv, dispute_model, days_model, *cell = args
    _init_worker(inv, dispute_model, days_model)
    return _grid_cell(tuple(cell))


def lever_grid(inv: pd.DataFrame, dispute_model, days_model, lever_a: str, lever_b: str,
               signoff_days: int = 3, parallel: bool = False) -> pd.DataFrame:
    """Runs pr.simulate for every pair of adoption shares in GRID_STEPS. Nothing is calculated differently
    from the simulator. parallel=True spreads the cells over local processes and is only used from
    core/lever_grid.py, never inside the Streamlit server; if the pool fails the cells run one by one."""
    cells = [(lever_a, a, lever_b, b, signoff_days) for a in GRID_STEPS for b in GRID_STEPS]
    if parallel:
        import os
        from concurrent.futures import ProcessPoolExecutor
        workers = max(1, min(8, (os.cpu_count() or 2) - 1))
        try:
            # Each task carries the data and models with it. Measured on this project this runs about twice
            # as fast as loading them once per worker through an initializer.
            with ProcessPoolExecutor(workers) as pool:
                return pd.DataFrame(list(pool.map(_grid_cell_with_data,
                                                  [(inv, dispute_model, days_model, *cell) for cell in cells])))
        except Exception:  # noqa: BLE001 - any pool failure falls back to the plain loop
            pass
    _init_worker(inv, dispute_model, days_model)
    return pd.DataFrame([_grid_cell(cell) for cell in cells])


def lever_grid_fast(inv: pd.DataFrame, dispute_model, days_model, lever_a: str, lever_b: str,
                    signoff_days: int = 3, timeout: int = 600) -> pd.DataFrame:
    """Runs core/lever_grid.py as a separate local Python process so the cells can use several cores. If that
    process fails or times out, the grid is worked out here one cell at a time with the same simulator."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "grid.csv"
        try:
            subprocess.run([sys.executable, "-m", "core.lever_grid", lever_a, lever_b, str(signoff_days), str(out)],
                           cwd=root, timeout=timeout, check=True, capture_output=True)
            return pd.read_csv(out)
        except Exception:  # noqa: BLE001 - fall back to the in-process loop
            return lever_grid(inv, dispute_model, days_model, lever_a, lever_b, signoff_days)


# Descriptive: DSO inside each month -----------------------------------------------------------------------------

def daily_dso(inv: pd.DataFrame, end: pd.Timestamp, window_days: int) -> pd.DataFrame:
    """DSO on every day from the first full month with a complete window up to end, using data.dso unchanged."""
    from core import data
    first_valid = inv["invoice_date"].min() + pd.Timedelta(days=window_days)
    start = (first_valid + pd.offsets.MonthBegin(1)).normalize()
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"date": days, "dso": [data.dso(inv, day, window_days) for day in days]})


def monthly_ohlc(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily DSO grouped by calendar month: first day (open), highest, lowest and last day (close)."""
    grouped = daily.dropna().groupby(daily["date"].dt.to_period("M"))["dso"]
    out = grouped.agg(open="first", high="max", low="min", close="last", days="size").reset_index()
    out["month"] = out["date"].dt.to_timestamp()
    out["swing"] = out["high"] - out["low"]
    return out.drop(columns="date")[["month", "open", "high", "low", "close", "swing", "days"]]
