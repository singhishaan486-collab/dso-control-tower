"""Feature lists, the leakage guard, the time split and the shared preprocessor.

Only columns known on the day an invoice is raised (known_at Contract or Invoice) may be features.
Everything learned after the invoice goes out is listed in LEAKY and must never be a feature.
"""
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from core.config import load_config

CATEGORICAL = ["sector", "client_ownership", "emirate", "service_line", "billing_basis",
               "attendance_method", "submission_channel", "timesheet_status", "lpo_status"]
NUMERIC = ["payment_terms_days", "approval_layers", "heads_contracted", "sla_penalty_clause",
           "prev_invoices_paid", "prev_avg_days_to_pay", "prev_late_rate", "prev_dispute_rate",
           "last_paid_invoice_late", "open_invoices_count", "open_amount_aed", "is_new_client",
           "prev_avg_days_to_pay_missing", "prev_late_rate_missing",
           "heads_deployed", "headcount_gap_pct", "relief_worker_share", "absence_rate",
           "ot_hours", "ot_hours_per_head", "ot_preapproved", "timesheet_variance_hours",
           "days_monthend_to_invoice", "lpo_valid", "rate_matches_contract", "docs_attached",
           "sla_deduction_aed", "log_amount", "invoice_month"]
FEATURES = CATEGORICAL + NUMERIC
LEAKY = ["client_ack_date", "dispute_raised", "dispute_reasons", "dispute_raised_date",
         "dispute_resolved_date", "disputed_amount_aed", "dispute_resolution", "first_followup_date",
         "short_paid_aed", "payment_date", "invoice_status", "days_to_pay", "paid_late",
         "stage_ack_days", "stage_dispute_resolution_days", "days_overdue", "cash_gap_days"]
BINARY_TARGETS = ["paid_late", "dispute_raised"]


def add_invoice_month(df: pd.DataFrame) -> pd.DataFrame:
    """Add invoice_month (1 to 12), the calendar month the invoice was raised."""
    out = df.copy()
    out["invoice_month"] = pd.to_datetime(out["invoice_date"]).dt.month
    return out


def _service_period(df: pd.DataFrame) -> pd.Series:
    return pd.Series(pd.PeriodIndex(df["service_month"], freq="M"), index=df.index)


def modelling_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Paid invoices up to test_end_month. Later months have not had time to settle (censoring)."""
    split = load_config()["split"]
    period = _service_period(df)
    keep = (df["invoice_status"] == "Paid") & (period <= pd.Period(split["test_end_month"], freq="M"))
    return df[keep]


def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on earlier service months, test on later ones. Never shuffled across time."""
    split = load_config()["split"]
    frame = modelling_frame(df)
    period = _service_period(frame)
    train = frame[period <= pd.Period(split["train_end_month"], freq="M")]
    test = frame[period >= pd.Period(split["test_start_month"], freq="M")]
    return train.sort_values("invoice_date"), test.sort_values("invoice_date")


def get_xy(df: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series]:
    """Return the allowed features and the target. Leaky columns can never reach X."""
    if target not in LEAKY:
        raise ValueError(f"{target} is not an outcome column")
    data = add_invoice_month(df)
    y = data[target].astype(int) if target in BINARY_TARGETS else data[target]
    return data[FEATURES], y


def build_preprocessor(numeric: list[str] | None = None) -> ColumnTransformer:
    """Impute and scale numbers, impute and one-hot encode categories. Fit on training rows only.

    `numeric` is only overridden by the labelled leakage demo.
    """
    numeric_steps = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    return ColumnTransformer([("num", numeric_steps, numeric or NUMERIC), ("cat", categorical, CATEGORICAL)])
