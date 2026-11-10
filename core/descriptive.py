"""Descriptive analytics: what is happening to DSO, receivables and the cash gap."""
import numpy as np
import pandas as pd

from core import data
from core.config import load_config

AGING_LABELS = ["Current", "1 to 30", "31 to 60", "61 to 90", "91 to 120", "120+"]


def snapshot_date() -> pd.Timestamp:
    return pd.Timestamp(load_config()["snapshot_date"])


def last_month_end(snapshot: pd.Timestamp) -> pd.Timestamp:
    """The last complete month end before the snapshot, where DSO is measured."""
    return (snapshot.to_period("M") - 1).to_timestamp(how="end").normalize()


def kpis(inv: pd.DataFrame, snapshot: pd.Timestamp) -> dict:
    """Headline numbers. Rates use paid invoices, receivables use invoices open on the snapshot date."""
    days = load_config()["dso_window_days"]
    period_end = last_month_end(snapshot)
    paid = inv[inv["invoice_status"] == "Paid"]
    open_ = inv[inv["invoice_status"] == "Open"]
    overdue = open_[open_["due_date"] < snapshot]
    return dict(
        dso=data.dso(inv, period_end, days), dso_period_end=period_end, dso_window_days=days,
        mean_days_to_pay=paid["days_to_pay"].mean(), late_rate=paid["paid_late"].mean(),
        dispute_rate=paid["dispute_raised"].mean(), open_ar=open_["invoice_amount_aed"].sum(),
        open_count=len(open_), overdue_ar=overdue["invoice_amount_aed"].sum(), overdue_count=len(overdue),
    )


def dso_trend(inv: pd.DataFrame) -> pd.DataFrame:
    """DSO at every month end once a full window of invoicing exists, plus that month's late rate."""
    days = load_config()["dso_window_days"]
    first = inv["invoice_date"].min() + pd.Timedelta(days=days)
    month_ends = pd.date_range(first, last_month_end(snapshot_date()), freq="ME")
    paid = inv[inv["invoice_status"] == "Paid"]
    late_by_month = paid.groupby(paid["invoice_date"].dt.to_period("M"))["paid_late"].mean()
    return pd.DataFrame({
        "month_end": month_ends,
        "dso": [data.dso(inv, end, days) for end in month_ends],
        "late_rate_of_invoices_raised": [late_by_month.get(end.to_period("M"), np.nan) for end in month_ends],
    })


def breakdown(inv: pd.DataFrame, by: str) -> pd.DataFrame:
    """Late rate, days to pay, dispute rate, revenue and DSO for each value of a profile column."""
    days = load_config()["dso_window_days"]
    period_end = last_month_end(snapshot_date())
    paid = inv[inv["invoice_status"] == "Paid"]
    table = paid.groupby(by).agg(paid_invoices=("invoice_id", "size"), late_rate=("paid_late", "mean"),
                                 mean_days_to_pay=("days_to_pay", "mean"),
                                 dispute_rate=("dispute_raised", "mean"))
    table["revenue_aed"] = inv.groupby(by)["invoice_amount_aed"].sum()
    table["dso"] = [data.dso(inv[inv[by] == value], period_end, days) for value in table.index]
    return table.reset_index().sort_values("dso", ascending=False)


def aging(inv: pd.DataFrame, snapshot: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open receivables by days past due, and the open invoices with their bucket."""
    open_ = inv[inv["invoice_status"] == "Open"].copy()
    open_["days_past_due"] = (snapshot - open_["due_date"]).dt.days
    open_["bucket"] = pd.cut(open_["days_past_due"], [-np.inf, 0, 30, 60, 90, 120, np.inf], labels=AGING_LABELS)
    buckets = (open_.groupby("bucket", observed=False)
               .agg(invoices=("invoice_id", "size"), amount_aed=("invoice_amount_aed", "sum"))
               .reindex(AGING_LABELS, fill_value=0).reset_index())
    return buckets, open_


def top_overdue_clients(inv: pd.DataFrame, snapshot: pd.Timestamp, n: int = 10) -> pd.DataFrame:
    _, open_ = aging(inv, snapshot)
    overdue = open_[open_["days_past_due"] > 0]
    return (overdue.groupby("client_id")
            .agg(overdue_aed=("invoice_amount_aed", "sum"), overdue_invoices=("invoice_id", "size"),
                 oldest_days_past_due=("days_past_due", "max"))
            .sort_values("overdue_aed", ascending=False).head(n).reset_index())


def cash_gap(inv: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Days between paying staff through WPS and receiving the client's money."""
    paid = inv[inv["invoice_status"] == "Paid"]
    gap = paid["cash_gap_days"]
    summary = dict(mean=gap.mean(), median=gap.median(), share_over_60=(gap > 60).mean())
    by_client = (paid.groupby("client_id")
                 .agg(paid_invoices=("invoice_id", "size"), mean_cash_gap_days=("cash_gap_days", "mean"),
                      revenue_aed=("invoice_amount_aed", "sum"))
                 .sort_values("mean_cash_gap_days", ascending=False).reset_index())
    return summary, by_client
