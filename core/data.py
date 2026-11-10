"""Loading and cleaning. Every fix is written to a cleaning log so the report can show it."""
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
DATE_COLS = ["month_end_date", "signoff_date", "invoice_date", "due_date", "wps_pay_date", "client_ack_date",
             "dispute_raised_date", "dispute_resolved_date", "first_followup_date", "payment_date"]
SECTOR_FIX = {"mall": "Mall", "office": "Office", "residential": "Residential", "hosp.": "Hospital",
              "hospital": "Hospital", "govt": "Government", "government": "Government", "hospitality": "Hospitality"}


def read_raw(path=None):
    df = pd.read_csv(path or DATA / "invoices.csv")
    for c in DATE_COLS:
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def clean(df):
    """Return (clean dataframe, list of log dicts)."""
    log = []
    df = df.copy()

    n = len(df)
    df = df.drop_duplicates()
    log.append(dict(step="Remove exact duplicate rows", rows_affected=n - len(df),
                    why="The same invoice entered twice would double count revenue and receivables."))

    before = df["sector"].copy()
    df["sector"] = df["sector"].astype(str).str.strip().str.lower().map(SECTOR_FIX).fillna(df["sector"].str.strip())
    log.append(dict(step="Standardise sector labels (Govt, Hosp., mall, trailing spaces)",
                    rows_affected=int((before != df["sector"]).sum()),
                    why="One sector written five ways would be split into separate groups."))

    # attendance method is a client attribute: fill from the client's other invoices
    miss = df["attendance_method"].isna().sum()
    mode = df.groupby("client_id")["attendance_method"].agg(lambda s: s.mode().iat[0] if s.notna().any() else np.nan)
    df["attendance_method"] = df["attendance_method"].fillna(df["client_id"].map(mode))
    log.append(dict(step="Fill missing attendance method from the same client's other invoices", rows_affected=int(miss),
                    why="Attendance method is fixed per contract, so the client's own value is the right fill."))

    for col in ["ot_hours", "absence_rate", "timesheet_variance_hours"]:
        miss = df[col].isna().sum()
        df[col] = df[col].fillna(df.groupby("client_id")[col].transform("median")).fillna(df[col].median())
        log.append(dict(step=f"Fill missing {col} with the client's median", rows_affected=int(miss),
                        why="Median per client keeps each client's normal level and ignores outliers."))

    # amount entry errors: invoice far above what headcount x rate could produce
    ratio = df["invoice_amount_aed"] / (df["heads_deployed"] * df.groupby("client_id")["invoice_amount_aed"].transform("median")
                                         / df.groupby("client_id")["heads_deployed"].transform("median"))
    bad = ratio > 4
    df.loc[bad, "invoice_amount_aed"] = (df.loc[bad, "invoice_amount_aed"] / 10).round(2)
    log.append(dict(step="Fix invoice amounts with an extra zero (more than 4x what headcount implies)",
                    rows_affected=int(bad.sum()),
                    why="A typed extra zero inflates DSO weighting and revenue. Checked against heads x the client's usual rate."))

    # transformations
    df["service_period"] = pd.PeriodIndex(df["service_month"], freq="M")
    df["is_new_client"] = (df["prev_invoices_paid"] == 0).astype(int)
    for col in ["prev_avg_days_to_pay", "prev_late_rate", "prev_dispute_rate", "last_paid_invoice_late"]:
        df[col + "_missing"] = df[col].isna().astype(int)
    df["ot_hours_per_head"] = (df["ot_hours"] / df["heads_deployed"]).round(2)
    df["log_amount"] = np.log1p(df["invoice_amount_aed"])
    df["stage_signoff_days"] = (df["signoff_date"] - df["month_end_date"]).dt.days
    df["stage_invoice_days"] = (df["invoice_date"] - df["month_end_date"]).dt.days
    df["stage_ack_days"] = (df["client_ack_date"] - df["invoice_date"]).dt.days
    df["stage_dispute_resolution_days"] = (df["dispute_resolved_date"] - df["dispute_raised_date"]).dt.days
    df["days_overdue"] = (df["payment_date"] - df["due_date"]).dt.days.clip(lower=0)
    df["cash_gap_days"] = (df["payment_date"] - df["wps_pay_date"]).dt.days
    log.append(dict(step="Create derived columns (OT per head, stage durations, cash gap, history-missing flags, log amount)",
                    rows_affected=len(df), why="Stage durations feed the diagnostic waterfall. Missing-history flags let models treat new clients separately."))
    return df.reset_index(drop=True), log


def load_all(invoice_path=None):
    raw = read_raw(invoice_path)
    df, log = clean(raw)
    cur = pd.read_csv(DATA / "current_batch.csv", parse_dates=[c for c in DATE_COLS if c in pd.read_csv(DATA / "current_batch.csv", nrows=0).columns])
    cur, _ = clean_current(cur)
    return dict(raw=raw, inv=df, log=log, current=cur,
                clients=pd.read_csv(DATA / "clients.csv"), lpos=pd.read_csv(DATA / "lpos.csv"),
                payroll=pd.read_csv(DATA / "payroll.csv", parse_dates=["wps_due_date", "pay_date"]))


def load_emails():
    return pd.read_csv(DATA / "dispute_emails.csv", parse_dates=["received_date"])


def clean_current(cur):
    cur = cur.copy()
    cur["is_new_client"] = (cur["prev_invoices_paid"] == 0).astype(int)
    for col in ["prev_avg_days_to_pay", "prev_late_rate", "prev_dispute_rate", "last_paid_invoice_late"]:
        cur[col + "_missing"] = cur[col].isna().astype(int)
    cur["ot_hours_per_head"] = (cur["ot_hours"] / cur["heads_deployed"]).round(2)
    cur["log_amount"] = np.log1p(cur["invoice_amount_aed"])
    return cur, []


def dso(df, period_end, days=90):
    """Countback-free standard DSO: AR open at period_end / credit sales in last `days` x days."""
    sales = df[(df["invoice_date"] > period_end - pd.Timedelta(days=days)) & (df["invoice_date"] <= period_end)]["invoice_amount_aed"].sum()
    open_ar = df[(df["invoice_date"] <= period_end) &
                 (df["payment_date"].isna() | (df["payment_date"] > period_end))]["invoice_amount_aed"].sum()
    return (open_ar / sales * days) if sales else np.nan
