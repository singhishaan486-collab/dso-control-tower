"""Automation checks: invoice QA with the LPO guard, a tamper-evident attendance ledger, and the WPS check.

Every function returns recommendations for a person. Nothing is sent, paid or changed.
Findings share one layout: item_id, node, check_id, severity, message, recommended_action, owner.
"""
import hashlib
import hmac
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from core.features import FEATURES, add_invoice_month

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
FINDING_COLUMNS = ["item_id", "node", "check_id", "severity", "message", "recommended_action", "owner"]
SEVERITY_RANK = {"Block": 0, "Warn": 1, "Info": 2}
GENESIS = "0" * 64


def _finding(item_id, node, check_id, severity, message, action, owner) -> dict:
    return dict(item_id=item_id, node=node, check_id=check_id, severity=severity, message=message,
                recommended_action=action, owner=owner)


# ------------------------------------------------------------------ LPO guard and invoice QA

def lpo_checks(current: pd.DataFrame, lpos: pd.DataFrame, config: dict) -> list[dict]:
    """LPO-01 to LPO-05 on this month's draft invoices."""
    cfg, action = config["lpo_guard"], "Request renewal or top-up from client procurement"
    joined = current.merge(lpos[["lpo_number", "lpo_value_aed", "valid_to"]], on="lpo_number", how="left")
    found = []
    for _, r in joined.iterrows():
        add = lambda cid, sev, msg: found.append(_finding(r["invoice_id"], "LPO", cid, sev, msg, action,
                                                          "Account manager"))
        if pd.isna(r["lpo_number"]) or r["lpo_number"] == "" or r["lpo_status"] == "Missing on invoice":
            add("LPO-01", "Block", "No LPO number on the invoice")
            continue
        if r["lpo_status"] == "Not yet renewed":
            add("LPO-02", "Block", f"{r['lpo_number']} has not been renewed for this period")
        balance = r["lpo_balance_before_aed"]
        if pd.notna(balance) and balance < r["invoice_amount_aed"]:
            add("LPO-03", "Block", f"LPO balance AED {balance:,.0f} is below the invoice AED "
                                   f"{r['invoice_amount_aed']:,.0f}")
        elif pd.notna(balance) and pd.notna(r["lpo_value_aed"]):
            after = balance - r["invoice_amount_aed"]
            if after < cfg["low_balance_pct"] / 100 * r["lpo_value_aed"]:
                add("LPO-04", "Warn", f"Only AED {after:,.0f} left after this invoice "
                                      f"({after / r['lpo_value_aed']:.0%} of the LPO)")
        if pd.notna(r["valid_to"]):
            months_left = (pd.Period(r["valid_to"], freq="M") - pd.Period(r["service_month"], freq="M")).n
            if 0 <= months_left <= cfg["expiry_warn_months"]:
                add("LPO-05", "Warn", f"{r['lpo_number']} expires {r['valid_to']}")
    return found


QA_RULES = [
    ("QA-01", "Block", lambda r, c: r["timesheet_status"] == "Unsigned",
     lambda r: "Timesheet not signed by the client", "Get the timesheet signed before sending"),
    ("QA-02", "Warn", lambda r, c: r["timesheet_status"] == "Signed with remarks",
     lambda r: "Timesheet signed with remarks", "Resolve the remarks with the FM team first"),
    ("QA-03", "Block", lambda r, c: r["lpo_valid"] == 0,
     lambda r: f"LPO status is {r['lpo_status']}", "See the LPO guard findings"),
    ("QA-04", "Block", lambda r, c: r["rate_matches_contract"] == 0,
     lambda r: "Billed rate differs from the contract rate", "Reissue at the contract rate"),
    ("QA-05", "Block", lambda r, c: r["docs_attached"] == 0,
     lambda r: "Signed timesheet and backup not attached", "Attach the full document pack"),
    ("QA-06", "Warn", lambda r, c: r["ot_preapproved"] == 0 and r["ot_hours_per_head"] > c["ot_hours_per_head_warn"],
     lambda r: f"{r['ot_hours_per_head']:.1f} OT hours per head without pre-approval",
     "Get written OT approval or remove the OT line"),
    ("QA-07", "Warn", lambda r, c: r["headcount_gap_pct"] > c["headcount_gap_warn_pct"],
     lambda r: f"Headcount {r['headcount_gap_pct']:.1f}% below contract", "Check the SLA deduction is applied"),
    ("QA-08", "Warn", lambda r, c: r["timesheet_variance_hours"] > c["timesheet_variance_warn_hours"],
     lambda r: f"{r['timesheet_variance_hours']:.0f} hours difference with the client's count",
     "Reconcile hours with the site supervisor"),
]


def qa_checks(current: pd.DataFrame, config: dict) -> list[dict]:
    """QA-01 to QA-08: a three-way match of each draft against timesheet, LPO and contract rate."""
    cfg, found = config["invoice_qa"], []
    for _, r in current.iterrows():
        for check_id, severity, test, message, action in QA_RULES:
            if test(r, cfg):
                found.append(_finding(r["invoice_id"], "Invoice QA", check_id, severity, message(r), action,
                                      "Billing"))
    return found


def _saved_models() -> dict:
    return {target: joblib.load(MODELS_DIR / f"clf_{target}.joblib") for target in ("paid_late", "dispute_raised")}


def invoice_qa(current: pd.DataFrame, lpos: pd.DataFrame, config: dict, saved: dict | None = None):
    """Return (one row per draft invoice with Pass, Warn or Block, every finding)."""
    findings = pd.DataFrame(lpo_checks(current, lpos, config) + qa_checks(current, config), columns=FINDING_COLUMNS)
    saved = saved or _saved_models()
    x = add_invoice_month(current)[FEATURES]
    out = current[["invoice_id", "client_id", "service_month", "invoice_amount_aed", "timesheet_status",
                   "lpo_status"]].copy()
    out["p_dispute"] = saved["dispute_raised"]["model"].predict_proba(x)[:, 1]
    out["p_late"] = saved["paid_late"]["model"].predict_proba(x)[:, 1]
    counts = findings.groupby(["item_id", "severity"]).size().unstack(fill_value=0)
    for severity in ("Block", "Warn"):
        out[f"{severity.lower()}s"] = out["invoice_id"].map(counts.get(severity, pd.Series(dtype=int))).fillna(0).astype(int)
    out["result"] = np.select([out["blocks"] > 0, out["warns"] > 0], ["Block", "Warn"], "Pass")
    out["aed_at_risk"] = out["invoice_amount_aed"] * out[["p_dispute", "p_late"]].max(axis=1)
    reasons = findings.groupby("item_id")["check_id"].agg(lambda s: ", ".join(sorted(set(s))))
    out["checks_failed"] = out["invoice_id"].map(reasons).fillna("")
    return out.sort_values("aed_at_risk", ascending=False).reset_index(drop=True), findings


# ------------------------------------------------------------------ attendance ledger

def _canonical(record: dict) -> str:
    return json.dumps({k: v for k, v in record.items() if k != "hash"}, sort_keys=True, separators=(",", ":"),
                      default=str)


def record_hash(record: dict) -> str:
    return hashlib.sha256((_canonical(record) + record["prev_hash"]).encode()).hexdigest()


def seal(key: str, value: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def _shift_records(employees, days, method, absence, seed) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for day in days:
        for i, emp in enumerate(employees):
            if rng.random() < absence:
                continue
            night = i % 3 == 2
            start = day + pd.Timedelta(hours=19 if night else 7, minutes=int(rng.integers(-10, 6)))
            rows.append(dict(date=str(day.date()), employee_id=emp, shift="Night" if night else "Day",
                             check_in=start, method=method, normal_hours=8.0, ot_hours=0.0))
    return rows


def generate_month(client_row: pd.Series, invoice_row: pd.Series, employees: list[str], keys: dict,
                   seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Daily attendance for one client and month that adds up to the invoice, chained and sealed each day."""
    month = pd.Period(invoice_row["service_month"], freq="M")
    days = pd.date_range(month.start_time, month.end_time.normalize(), freq="D")
    heads = int(invoice_row["heads_deployed"])
    staff = (list(employees) + [f"TMP{i:04d}" for i in range(heads)])[:heads]
    rows = _shift_records(staff, days, client_row["attendance_method"], float(invoice_row["absence_rate"]), seed)
    rng = np.random.default_rng(seed + 1)
    remaining = int(invoice_row["ot_hours"])
    while remaining > 0 and rows:
        pick = rows[int(rng.integers(len(rows)))]
        extra = min(remaining, int(rng.integers(1, 4)))
        pick["ot_hours"] += extra
        remaining -= extra
    approved = int(invoice_row["ot_preapproved"]) == 1
    records, prev = [], GENESIS
    for seq, row in enumerate(rows, start=1):
        row["check_out"] = row["check_in"] + pd.Timedelta(hours=row["normal_hours"] + row["ot_hours"])
        row["ot_approval_ref"] = f"OTA-{invoice_row['client_id'][-3:]}-{row['date'][-5:]}" if (
            row["ot_hours"] and approved) else ""
        record = dict(seq=seq, **{k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in row.items()},
                      prev_hash=prev)
        record["hash"] = record_hash(record)
        records.append(record)
        prev = record["hash"]
    return records, daily_seals(records, keys)


def daily_seals(records: list[dict], keys: dict) -> list[dict]:
    """At the end of each day both parties sign the last hash of that day."""
    last = {}
    for record in records:
        last[record["date"]] = record
    return [dict(date=day, last_seq=r["seq"], last_hash=r["hash"], supplier_seal=seal(keys["supplier_key"], r["hash"]),
                 client_seal=seal(keys["client_key"], r["hash"])) for day, r in last.items()]


def verify(records: list[dict], seals: list[dict], keys: dict) -> tuple[bool, int | None, str]:
    """Recompute every hash and every daily seal. Return (ok, first bad seq, reason)."""
    prev = GENESIS
    for record in records:
        if record["prev_hash"] != prev:
            return False, record["seq"], "The link to the previous record is broken"
        if record_hash(record) != record["hash"]:
            return False, record["seq"], "The record's contents no longer match its hash"
        prev = record["hash"]
    by_seq = {r["seq"]: r for r in records}
    for day in seals:
        record = by_seq.get(day["last_seq"])
        if record is None or record["hash"] != day["last_hash"]:
            return False, day["last_seq"], f"The last record of {day['date']} differs from the one both parties sealed"
        for party, key in (("supplier", keys["supplier_key"]), ("client", keys["client_key"])):
            if seal(key, record["hash"]) != day[f"{party}_seal"]:
                return False, day["last_seq"], f"The {party} seal for {day['date']} does not match"
    return True, None, "Every hash and every daily seal checks out"


def tamper(records: list[dict], seq: int, field: str, value, rehash: bool = False) -> list[dict]:
    """Return an edited copy. With rehash, the forger also rebuilds every hash after the edit."""
    edited = [dict(r) for r in records]
    target = next(r for r in edited if r["seq"] == seq)
    target[field] = value
    if rehash:
        prev = GENESIS
        for record in edited:
            record["prev_hash"] = prev
            record["hash"] = record_hash(record)
            prev = record["hash"]
    return edited


def ledger_summary(records: list[dict], invoice_row: pd.Series) -> dict:
    df = pd.DataFrame(records)
    days = pd.Period(invoice_row["service_month"], freq="M").days_in_month
    return dict(records=len(df), employees=df["employee_id"].nunique(), ot_hours=float(df["ot_hours"].sum()),
                invoice_ot_hours=float(invoice_row["ot_hours"]), shifts_worked=len(df),
                shifts_expected=int(invoice_row["heads_deployed"] * days * (1 - invoice_row["absence_rate"])))


# ------------------------------------------------------------------ WPS compliance

def wps_check(payroll: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """WPS-01 to WPS-06. Return (findings, monthly on-time share)."""
    cfg = config["wps"]
    p = payroll
    item = p["employee_id"] + " " + p["payroll_month"].astype(str)
    rules = [
        ("WPS-01", "Block", p["pay_date"] > p["wps_due_date"],
         "Paid " + (p["pay_date"] - p["wps_due_date"]).dt.days.astype(str) + " days after the WPS due date",
         "Release the salary today and log the reason"),
        ("WPS-02", "Block", p["ot_rate_multiplier_used"] < cfg["ot_multiplier_min"],
         "OT paid at " + p["ot_rate_multiplier_used"].astype(str) + "x, below the legal minimum",
         "Recalculate OT at the legal rate and pay the difference"),
        ("WPS-03", "Warn", p["ot_hours"] > cfg["ot_hours_month_max"],
         p["ot_hours"].astype(str) + " OT hours, above the monthly limit", "Review rosters and add relief staff"),
        ("WPS-04", "Block", p["days_paid"] > p["days_in_month"],
         "Paid for " + p["days_paid"].astype(str) + " days in a " + p["days_in_month"].astype(str) + "-day month",
         "Correct the payroll days before the file is sent"),
        ("WPS-05", "Block", p["iban_on_file"] == 0, pd.Series("No IBAN on file", index=p.index),
         "Collect the employee's bank details"),
    ]
    frames = [pd.DataFrame({"item_id": item[mask], "client_id": p.loc[mask, "client_id"],
                            "payroll_month": p.loc[mask, "payroll_month"].astype(str), "node": "WPS",
                            "check_id": check_id, "severity": severity, "message": message[mask],
                            "recommended_action": action, "owner": "Payroll"})
              for check_id, severity, mask, message, action in rules]
    monthly = (p.assign(on_time=p["pay_date"] <= p["wps_due_date"])
               .groupby("payroll_month")["on_time"].mean().rename("on_time_share").reset_index())
    monthly["payroll_month"] = monthly["payroll_month"].astype(str)
    low = monthly[monthly["on_time_share"] < cfg["establishment_on_time_min"]]
    frames.append(pd.DataFrame({
        "item_id": "Establishment " + low["payroll_month"], "client_id": "All", "payroll_month": low["payroll_month"],
        "node": "WPS", "check_id": "WPS-06", "severity": "Block",
        "message": "Only " + (low["on_time_share"] * 100).round(1).astype(str) + "% of staff paid on time",
        "recommended_action": "Fund payroll before the due date; escalate to the owner", "owner": "Payroll"}))
    return pd.concat(frames, ignore_index=True), monthly


def payroll_vs_invoice_lateness(payroll: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    """Per client: share of salaries paid late against the share of that client's invoices paid late."""
    salaries = (payroll.assign(late=payroll["pay_date"] > payroll["wps_due_date"])
                .groupby("client_id")["late"].mean().rename("payroll_late_rate"))
    paid = inv[inv["invoice_status"] == "Paid"]
    invoices = paid.groupby("client_id")["paid_late"].mean().rename("invoice_late_rate")
    return pd.concat([salaries, invoices], axis=1).dropna().reset_index()
