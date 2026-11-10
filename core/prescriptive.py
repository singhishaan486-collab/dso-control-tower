"""Prescriptive analytics: a policy per client segment and a what-if simulator on the saved models.

The simulator changes invoice features as if a process change had been adopted, then asks the trained
models what they would now predict. These are associations learned from synthetic data, not proven causes.
"""
import numpy as np
import pandas as pd

from core.config import load_config
from core.descriptive import last_month_end, snapshot_date
from core.features import FEATURES, add_invoice_month, modelling_frame

LEVERS = ["Automated attendance", "OT pre-approval enforced", "LPO guard", "Invoice QA", "Faster sign-off"]
LEVER_CHANGES = {
    "Automated attendance": "Attendance on the app, timesheet variance cut by 80%, every timesheet signed",
    "OT pre-approval enforced": "Every OT hour approved by the client before it is worked",
    "LPO guard": "Every invoice carries a valid LPO with enough balance",
    "Invoice QA": "Documents attached and the contract rate applied on every invoice",
    "Faster sign-off": "Invoice raised a set number of days sooner after month end (at least 1 day)",
}
POLICIES = {
    "Fast and clean": ("Keep current terms. Consider them for growth and longer terms.", "Account manager",
                       "Share paid late stays low"),
    "Slow but clean": ("Price the wait into the rate, submit through the client portal, track every approval "
                       "layer, and consider receivables financing.", "Finance and account manager",
                       "Days to pay and DSO"),
    "Dispute prone": ("Get the timesheet signed before invoicing, enforce OT pre-approval, run the LPO guard and "
                      "confirm attendance weekly.", "Operations and billing", "Dispute rate"),
    "Average": ("Standard reminders at 10 days before due, 1 day after and 15 days after.", "Collections",
                "Share paid late"),
}


def policy_table(segments: pd.DataFrame) -> pd.DataFrame:
    """One row per segment: who is in it, how they behave and what to do about it."""
    table = segments.groupby("segment").agg(
        clients=("client_id", "size"), revenue_share=("revenue_share", "sum"),
        mean_days_to_pay=("mean_days_to_pay", "mean"), dispute_rate=("dispute_rate", "mean"),
        late_rate=("late_rate", "mean")).reset_index()
    base = table["segment"].str.split(" (", regex=False).str[0]
    table["policy"] = base.map(lambda s: POLICIES[s][0])
    table["owner"] = base.map(lambda s: POLICIES[s][1])
    table["metric_to_watch"] = base.map(lambda s: POLICIES[s][2])
    return table


def simulation_frame(inv: pd.DataFrame) -> pd.DataFrame:
    """Paid invoices from the latest 12 service months that have had time to settle."""
    frame = modelling_frame(inv)
    period = pd.PeriodIndex(frame["service_month"], freq="M")
    return add_invoice_month(frame[period > period.max() - 12]).reset_index(drop=True)


def daily_credit_sales(inv: pd.DataFrame) -> float:
    """Average AED invoiced per day over the 12 months to the last month end."""
    end = last_month_end(snapshot_date())
    recent = inv[(inv["invoice_date"] > end - pd.DateOffset(years=1)) & (inv["invoice_date"] <= end)]
    return float(recent["invoice_amount_aed"].sum() / 365)


def apply_lever(df: pd.DataFrame, lever: str, mask: np.ndarray, signoff_days: int) -> pd.DataFrame:
    """Change the features of the adopting invoices as the lever describes."""
    out = df.copy()
    if lever == "Automated attendance":
        out.loc[mask, "attendance_method"] = "App"
        out.loc[mask, "timesheet_variance_hours"] = out.loc[mask, "timesheet_variance_hours"] * 0.2
        out.loc[mask, "timesheet_status"] = "Signed"
    elif lever == "OT pre-approval enforced":
        out.loc[mask, "ot_preapproved"] = 1
    elif lever == "LPO guard":
        out.loc[mask, "lpo_status"] = "Valid"
        out.loc[mask, "lpo_valid"] = 1
    elif lever == "Invoice QA":
        out.loc[mask, "docs_attached"] = 1
        out.loc[mask, "rate_matches_contract"] = 1
    elif lever == "Faster sign-off":
        out.loc[mask, "days_monthend_to_invoice"] = (out.loc[mask, "days_monthend_to_invoice"]
                                                     - signoff_days).clip(lower=1)
    return out


def _score(df: pd.DataFrame, dispute_model, days_model) -> dict:
    p_dispute = dispute_model.predict_proba(df[FEATURES])[:, 1]
    days = days_model.predict(df[FEATURES])
    return dict(mean_p_dispute=float(p_dispute.mean()),
                weighted_days_to_pay=float(np.average(days, weights=df["invoice_amount_aed"])))


def _add_disputes(scored: dict, scale: float) -> dict:
    """The forest's scores run higher than the real dispute rate, so counts are scaled to the actual rate."""
    return dict(scored, disputes_per_month=scored["mean_p_dispute"] * scale)


def dispute_ceiling_days(inv: pd.DataFrame, dispute_cost_days: float) -> float:
    """The most DSO that disputes can explain: dispute rate times the days a dispute adds."""
    paid = simulation_frame(inv)
    return float(paid["dispute_raised"].mean() * dispute_cost_days)


def simulate(inv: pd.DataFrame, dispute_model, days_model, adoption: dict, signoff_days: int = 3) -> dict:
    """Apply the levers one after another and record what each adds.

    Adoption picks a random share of invoices with a fixed seed per lever, so a higher share always
    contains the invoices of a lower one.
    """
    frame = simulation_frame(inv)
    months = frame["service_month"].nunique()
    seed = load_config()["random_state"]
    cash_per_day = daily_credit_sales(inv)
    before = _score(frame, dispute_model, days_model)
    scale = frame["dispute_raised"].sum() / months / before["mean_p_dispute"]
    before = _add_disputes(before, scale)
    current, previous, steps = frame, before, []
    for i, lever in enumerate(LEVERS):
        share = adoption.get(lever, 0.0)
        mask = np.random.default_rng(seed + i).random(len(frame)) < share
        current = apply_lever(current, lever, mask, signoff_days)
        scored = _add_disputes(_score(current, dispute_model, days_model), scale)
        dso_change = scored["weighted_days_to_pay"] - previous["weighted_days_to_pay"]
        steps.append(dict(lever=lever, adoption=share, invoices_changed=int(mask.sum()),
                          p_dispute_change=scored["mean_p_dispute"] - previous["mean_p_dispute"],
                          disputes_per_month_change=scored["disputes_per_month"] - previous["disputes_per_month"],
                          dso_change_days=dso_change, cash_released_aed=-dso_change * cash_per_day))
        previous = scored
    steps = pd.DataFrame(steps)
    dso_change = previous["weighted_days_to_pay"] - before["weighted_days_to_pay"]
    return dict(before=before, after=previous, steps=steps, invoices=len(frame), months=months,
                cash_per_day=cash_per_day, dso_change=dso_change, cash_released=-dso_change * cash_per_day)
