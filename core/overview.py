"""Numbers for the Overview page: filters, KPI cards, monthly activity, best and worst payers, leaderboards."""
import pandas as pd

from core import data
from core.config import load_config
from core.descriptive import dso_trend, last_month_end, snapshot_date
from core.features import modelling_frame

TIMEFRAMES = {"All time": None, "Last 12 months": 12, "Last 6 months": 6}


def apply_filters(inv: pd.DataFrame, timeframe: str, ownership: str, sector: str) -> pd.DataFrame:
    out = inv
    months = TIMEFRAMES[timeframe]
    if months:
        end = last_month_end(snapshot_date())
        out = out[out["invoice_date"] > end - pd.DateOffset(months=months)]
    if ownership != "All":
        out = out[out["client_ownership"] == ownership]
    if sector != "All":
        out = out[out["sector"] == sector]
    return out


def settled_monthly_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Late and dispute rate per service month, only for months that have had time to settle."""
    settled = modelling_frame(df)
    return (settled.groupby("service_month")
            .agg(late_rate=("paid_late", "mean"), dispute_rate=("dispute_raised", "mean"),
                 invoices=("invoice_id", "size"))
            .reset_index().sort_values("service_month"))


def _change(series: pd.Series, window: int = 3) -> float | None:
    """Average of the latest months minus the average of the months before them."""
    values = series.dropna()
    if len(values) < 2 * window:
        return None
    return float(values.iloc[-window:].mean() - values.iloc[-2 * window:-window].mean())


def kpi_cards(filtered: pd.DataFrame, inv: pd.DataFrame, rate_scope: pd.DataFrame) -> dict:
    days = load_config()["dso_window_days"]
    period_end = last_month_end(snapshot_date())
    paid = filtered[filtered["invoice_status"] == "Paid"]
    trend = dso_trend(filtered)
    rates = settled_monthly_rates(rate_scope)
    return dict(
        clients=filtered["client_id"].nunique(), clients_total=inv["client_id"].nunique(),
        invoices=len(filtered), open_invoices=int((filtered["invoice_status"] == "Open").sum()),
        mean_days_to_pay=paid["days_to_pay"].mean(), dso=data.dso(filtered, period_end, days),
        dso_series=trend["dso"].dropna().tail(12).round(1).tolist(), dso_change=_change(trend["dso"]),
        late_rate=paid["paid_late"].mean(), late_series=(rates["late_rate"] * 100).round(1).tail(12).tolist(),
        late_change=_change(rates["late_rate"]),
        dispute_rate=paid["dispute_raised"].mean(),
        dispute_series=(rates["dispute_rate"] * 100).round(1).tail(12).tolist(),
        dispute_change=_change(rates["dispute_rate"]),
    )


def monthly_activity(df: pd.DataFrame, measure: str) -> pd.DataFrame:
    """The last 12 months of invoicing or collections."""
    end = last_month_end(snapshot_date())
    months = pd.period_range(end.to_period("M") - 11, end.to_period("M"), freq="M")
    if measure == "Collected (AED)":
        values = df.dropna(subset=["payment_date"]).groupby(df["payment_date"].dt.to_period("M"))[
            "invoice_amount_aed"].sum()
    elif measure == "Invoices raised":
        values = df.groupby(df["invoice_date"].dt.to_period("M"))["invoice_id"].size()
    else:
        values = df.groupby(df["invoice_date"].dt.to_period("M"))["invoice_amount_aed"].sum()
    return pd.DataFrame({"month": [m.strftime("%b") for m in months], "period": [str(m) for m in months],
                         "value": [float(values.get(m, 0)) for m in months]})


DAYS_SCALE = 120


def payer_extremes(df: pd.DataFrame, names: pd.Series, n: int = 3, min_invoices: int = 6):
    """The clients with the longest and shortest average days to pay."""
    paid = df[df["invoice_status"] == "Paid"]
    table = paid.groupby("client_id").agg(invoices=("invoice_id", "size"), late=("paid_late", "mean"),
                                          days=("days_to_pay", "mean"))
    table = table[table["invoices"] >= min_invoices]
    table["on_time"] = 1 - table["late"]
    table["fill"] = (table["days"] / DAYS_SCALE).clip(upper=1)
    table["name"] = names.reindex(table.index).fillna(table.index.to_series())
    ranked = table.sort_values("days", ascending=False)
    return ranked.head(n).reset_index(), ranked.tail(n).iloc[::-1].reset_index()


def _windows(df: pd.DataFrame, months: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The latest settled service months and the same number of months before them."""
    settled = modelling_frame(df)
    period = pd.PeriodIndex(settled["service_month"], freq="M")
    last = period.max() if len(period) else None
    if last is None:
        return settled, settled
    recent = settled[period > last - months]
    before = settled[(period <= last - months) & (period > last - 2 * months)]
    return recent, before


def leaderboard(df: pd.DataFrame, by: str, names: pd.Series | None = None, n: int = 5,
                min_invoices: int = 3) -> pd.DataFrame:
    """Rank by share paid on time in the latest settled months, with the change in rank since before."""
    recent, before = _windows(df)

    def rank(part: pd.DataFrame) -> pd.DataFrame:
        table = part.groupby(by).agg(invoices=("invoice_id", "size"), on_time=("paid_late", lambda s: 1 - s.mean()),
                                     days=("days_to_pay", "mean"), revenue=("invoice_amount_aed", "sum"))
        table = table[table["invoices"] >= min_invoices].sort_values(["on_time", "days"], ascending=[False, True])
        table["rank"] = range(1, len(table) + 1)
        return table

    now, then = rank(recent), rank(before)
    now["change"] = (then["rank"].reindex(now.index) - now["rank"]).fillna(0).astype(int)
    now["name"] = names.reindex(now.index).fillna(now.index.to_series()) if names is not None else now.index
    return now.head(n).reset_index()
