"""Diagnostic analytics: where days are lost between month end and cash, and why."""
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules

from core.config import load_config

OUTCOMES = {"DISPUTE", "LATE", "LATE_30+"}
ITEM_MEANINGS = {
    "TS=Signed": "Timesheet signed cleanly",
    "TS=Remarks": "Timesheet signed with remarks",
    "TS=Unsigned": "Invoice sent with an unsigned timesheet",
    "OT_UNAPPROVED": "More than 4 OT hours per head without client pre-approval",
    "LPO=<status>": "LPO status on the invoice (Valid, Not yet renewed, Insufficient balance, Missing)",
    "ATT=<method>": "Attendance captured on Paper, Biometric or App",
    "HC_GAP>5": "Headcount more than 5% below contract",
    "VAR>20h": "Our hours and the client's hours differ by more than 20",
    "DOCS_MISSING": "Signed timesheet and backup not attached",
    "RATE_MISMATCH": "Billed rate differs from the contract rate",
    "OWN=<ownership>": "Client ownership type",
    "DISPUTE": "Outcome: the client disputed the invoice",
    "LATE": "Outcome: paid after the due date",
    "LATE_30+": "Outcome: paid more than 30 days after the due date",
}
VARIANCE_BANDS = [-np.inf, 8, 20, 40, np.inf]
VARIANCE_LABELS = ["0 to 8 h", "9 to 20 h", "21 to 40 h", "Over 40 h"]


def _paid(inv: pd.DataFrame) -> pd.DataFrame:
    return inv[inv["invoice_status"] == "Paid"]


def stage_waterfall(inv: pd.DataFrame) -> pd.DataFrame:
    """Mean days at each stage from month end to cash, for disputed and undisputed paid invoices."""
    paid = _paid(inv)
    clean = paid[paid["dispute_raised"] == 0]
    disputed = paid[(paid["dispute_raised"] == 1) & paid["dispute_resolved_date"].notna()]
    stages = {
        "Not disputed": {
            "Month end to invoice": clean["stage_invoice_days"],
            "Invoice to acknowledgement": clean["stage_ack_days"],
            "Acknowledgement to payment": (clean["payment_date"] - clean["client_ack_date"]).dt.days,
        },
        "Disputed": {
            "Month end to invoice": disputed["stage_invoice_days"],
            "Invoice to acknowledgement": disputed["stage_ack_days"],
            "Acknowledgement to dispute": (disputed["dispute_raised_date"] - disputed["client_ack_date"]).dt.days,
            "Dispute to resolution": disputed["stage_dispute_resolution_days"],
            "Resolution to payment": (disputed["payment_date"] - disputed["dispute_resolved_date"]).dt.days,
        },
    }
    rows = [dict(group=group, stage=stage, mean_days=values.mean(), invoices=len(values))
            for group, parts in stages.items() for stage, values in parts.items()]
    return pd.DataFrame(rows)


def dispute_pareto(inv: pd.DataFrame) -> pd.DataFrame:
    """Disputes by reason code, with resolution time and the extra days to pay versus undisputed invoices."""
    paid = _paid(inv)
    baseline = paid.loc[paid["dispute_raised"] == 0, "days_to_pay"].mean()
    disputed = paid[paid["dispute_raised"] == 1].assign(
        reason=lambda d: d["dispute_reasons"].fillna("").str.split("; ")).explode("reason")
    disputed = disputed[disputed["reason"].fillna("") != ""]
    table = disputed.groupby("reason").agg(
        disputes=("invoice_id", "size"), mean_resolution_days=("stage_dispute_resolution_days", "mean"),
        mean_days_to_pay=("days_to_pay", "mean")).sort_values("disputes", ascending=False)
    table["share"] = table["disputes"] / table["disputes"].sum()
    table["cumulative_share"] = table["share"].cumsum()
    table["extra_days_vs_undisputed"] = table["mean_days_to_pay"] - baseline
    return table.reset_index()


def _transactions(inv: pd.DataFrame) -> pd.DataFrame:
    """One row per paid invoice, one True/False column per item."""
    paid = _paid(inv)
    status = paid["timesheet_status"].map({"Signed": "TS=Signed", "Signed with remarks": "TS=Remarks",
                                           "Unsigned": "TS=Unsigned"})
    items = pd.DataFrame(index=paid.index)
    for value in status.dropna().unique():
        items[value] = status == value
    items["OT_UNAPPROVED"] = (paid["ot_preapproved"] == 0) & (paid["ot_hours_per_head"] > 4)
    for prefix, column in [("LPO", "lpo_status"), ("ATT", "attendance_method"), ("OWN", "client_ownership")]:
        for value in paid[column].dropna().unique():
            items[f"{prefix}={value}"] = paid[column] == value
    items["HC_GAP>5"] = paid["headcount_gap_pct"] > 5
    items["VAR>20h"] = paid["timesheet_variance_hours"] > 20
    items["DOCS_MISSING"] = paid["docs_attached"] == 0
    items["RATE_MISMATCH"] = paid["rate_matches_contract"] == 0
    items["DISPUTE"] = paid["dispute_raised"] == 1
    items["LATE"] = paid["paid_late"] == 1
    items["LATE_30+"] = paid["days_overdue"] > 30
    return items.astype(bool)


def _readable(rules: pd.DataFrame, n_rows: int) -> pd.DataFrame:
    out = pd.DataFrame({
        "if": rules["antecedents"].map(lambda s: " + ".join(sorted(s))),
        "then": rules["consequents"].map(lambda s: " + ".join(sorted(s))),
        "support": rules["support"], "confidence": rules["confidence"], "lift": rules["lift"],
    })
    out["invoices"] = (out["support"] * n_rows).round().astype(int)
    return out.reset_index(drop=True)


def _drop_redundant(rules: pd.DataFrame) -> pd.DataFrame:
    """Drop a rule when a shorter rule with the same outcome already has at least the same lift."""
    keep = []
    for _, rule in rules.iterrows():
        shorter = rules[(rules["consequents"] == rule["consequents"])
                        & rules["antecedents"].map(lambda s: s < rule["antecedents"])
                        & (rules["lift"] >= rule["lift"])]
        keep.append(shorter.empty)
    return rules[keep]


def outcome_rules(inv: pd.DataFrame) -> pd.DataFrame:
    """Rules from conditions known before sending to dispute and late outcomes, sorted by lift."""
    cfg = load_config()["association"]
    items = _transactions(inv)
    frequent = apriori(items, min_support=cfg["min_support"], use_colnames=True)
    rules = association_rules(frequent, num_itemsets=len(items), metric="confidence",
                              min_threshold=cfg["min_confidence"])
    keep = (rules["consequents"].map(lambda s: s <= OUTCOMES) & rules["antecedents"].map(lambda s: not s & OUTCOMES)
            & (rules["lift"] >= cfg["min_lift"]))
    rules = _drop_redundant(rules[keep]).sort_values(["lift", "confidence"], ascending=False)
    return _readable(rules, len(items))


def reason_pairs(inv: pd.DataFrame) -> pd.DataFrame:
    """How often two dispute reasons appear on the same invoice, against what chance would give (lift)."""
    cfg = load_config()["association"]
    reasons = _paid(inv).query("dispute_raised == 1")["dispute_reasons"].dropna().str.split("; ")
    codes = sorted({code for row in reasons for code in row if code})
    items = pd.DataFrame([{code: code in row for code in codes} for row in reasons])
    frequent = apriori(items, min_support=cfg["min_support"], use_colnames=True)
    size = frequent["itemsets"].map(len)
    pairs = frequent[size == 2]
    single = dict(zip(frequent.loc[size == 1, "itemsets"].map(lambda s: next(iter(s))),
                      frequent.loc[size == 1, "support"]))
    rows = []
    for itemset, support in zip(pairs["itemsets"], pairs["support"]):
        first, second = sorted(itemset)
        rows.append(dict(reason_a=first, reason_b=second, invoices=round(support * len(items)), support=support,
                         lift=support / (single[first] * single[second])))
    return pd.DataFrame(rows, columns=["reason_a", "reason_b", "invoices", "support", "lift"]).sort_values(
        "invoices", ascending=False).reset_index(drop=True)


def dispute_rate_by(inv: pd.DataFrame, column: str) -> pd.DataFrame:
    paid = _paid(inv)
    return (paid.groupby(column, observed=True)
            .agg(paid_invoices=("invoice_id", "size"), dispute_rate=("dispute_raised", "mean"),
                 clients=("client_id", "nunique"))
            .reset_index())


def with_variance_band(inv: pd.DataFrame) -> pd.DataFrame:
    out = inv.copy()
    out["variance_band"] = pd.cut(out["timesheet_variance_hours"], VARIANCE_BANDS, labels=VARIANCE_LABELS)
    return out


def variance_by_method(inv: pd.DataFrame) -> pd.DataFrame:
    """Dispute rate by attendance method inside each variance band, to separate method from mechanism."""
    paid = with_variance_band(_paid(inv))
    return (paid.groupby(["attendance_method", "variance_band"], observed=True)
            .agg(paid_invoices=("invoice_id", "size"), dispute_rate=("dispute_raised", "mean"))
            .reset_index())
