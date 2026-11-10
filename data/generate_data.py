"""
Synthetic order-to-cash dataset for a UAE manpower / facility services company (v2).

Outputs (in this folder)
  invoices.csv       one row per monthly invoice, Jul 2024 to Sep 2026 service months.
                     Snapshot date 2026-11-09: invoices not yet paid are OPEN (no payment_date).
  current_batch.csv  draft invoices for the Oct 2026 service month, not yet sent.
                     Used by the automation checks and the risk scoring.
  clients.csv        client and contract master.
  lpos.csv           LPOs issued by clients (value, validity, renewal).
  payroll.csv        employee-month payroll for Jun to Oct 2026, for the WPS checks.

Design rules
  1. Disputes are created mechanically from mismatches the firm can see before sending the invoice
     (unsigned timesheet, attendance variance, unapproved OT, headcount gap, LPO problem,
     rate mismatch, missing documents), plus client temperament. Not random labels.
  2. Client history columns only use invoices PAID before the current invoice date (no peeking).
  3. Deliberate mess (duplicates, typos, missing values, amount entry errors) for the cleaning step.

All names, IDs, IBANs and person codes are fake.
"""
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(7)
SNAPSHOT = pd.Timestamp("2026-11-09")
HIST_MONTHS = pd.period_range("2024-07", "2026-09", freq="M")
CURRENT_MONTH = pd.Period("2026-10", freq="M")
N_CLIENTS = 60

# ------------------------------------------------------------------ client master
SECTORS = {
    # sector:        (weight, ownership options + probs,                                   terms options, probs,   layers)
    "Mall":          (12, (["Private large", "Semi-government"], [0.8, 0.2]),               [60, 90], [0.7, 0.3], (2, 3)),
    "Office":        (14, (["Private large", "Private SME", "Semi-government"], [0.5, 0.35, 0.15]), [30, 45, 60], [0.35, 0.3, 0.35], (1, 2)),
    "Residential":   (12, (["Private SME", "Private large"], [0.6, 0.4]),                   [30, 45, 60], [0.4, 0.3, 0.3], (1, 2)),
    "Hospital":      (11, (["Private large", "Semi-government"], [0.6, 0.4]),               [60, 90], [0.5, 0.5], (2, 3)),
    "Government":    (8,  (["Government"], [1.0]),                                          [30, 60, 90], [0.3, 0.3, 0.4], (3, 4)),
    "Hospitality":   (7,  (["Private large", "Private SME"], [0.7, 0.3]),                   [30, 60], [0.5, 0.5], (1, 3)),
}
SERVICE_LINES = {  # rate per head per month (AED, excl VAT), basic salary range, OT intensity
    "Security":               (2700, (1300, 1700), 1.4),
    "Technical (MEP)":        (3600, (1800, 2600), 1.0),
    "Front office and supervision": (5200, (3000, 4500), 0.4),
}
ARCH = ["fast_clean", "slow_clean", "slow_messy", "average"]
EMIRATES = (["Dubai", "Abu Dhabi", "Sharjah"], [0.65, 0.2, 0.15])

sec_names = list(SECTORS)
sec_w = np.array([SECTORS[s][0] for s in sec_names], float); sec_w /= sec_w.sum()

clients = []
for i in range(N_CLIENTS):
    sec = rng.choice(sec_names, p=sec_w)
    _, (own_opts, own_p), t_opts, t_p, (lmin, lmax) = SECTORS[sec]
    own = rng.choice(own_opts, p=own_p)
    if own == "Government":
        arch = rng.choice(ARCH, p=[0.05, 0.6, 0.15, 0.2])
    elif own == "Private SME":
        arch = rng.choice(ARCH, p=[0.2, 0.05, 0.4, 0.35])
    else:
        arch = rng.choice(ARCH, p=[0.3, 0.12, 0.23, 0.35])
    line = rng.choice(list(SERVICE_LINES), p=[0.45, 0.4, 0.15])
    rate = int(SERVICE_LINES[line][0] * rng.uniform(0.9, 1.12))
    start = HIST_MONTHS[int(rng.choice([0] * 35 + list(range(1, 20))))]
    clients.append(dict(
        client_id=f"CL-{i+1:03d}", client_name=f"Client {i+1:03d} LLC", sector=sec, client_ownership=own,
        emirate=rng.choice(EMIRATES[0], p=EMIRATES[1]), service_line=line,
        payment_terms_days=int(rng.choice(t_opts, p=t_p)),
        billing_basis=rng.choice(["Per head per month", "Per hour"], p=[0.7, 0.3]),
        approval_layers=int(rng.integers(lmin, lmax + 1)),
        heads_contracted=int(np.clip(rng.lognormal(3.4, 0.6), 6, 160)),
        attendance_method=rng.choice(["Paper", "Biometric", "App"], p=[0.4, 0.4, 0.2]),
        submission_channel=rng.choice(["Email", "Client portal", "Hand delivery"], p=[0.5, 0.3, 0.2]),
        sla_penalty_clause=int(rng.random() < 0.55),
        rate_per_head_aed=rate, contract_start_month=str(start),
        _arch=arch,
        _delay=dict(fast_clean=-14, slow_clean=12, slow_messy=4, average=-6)[arch] + rng.normal(0, 5),
        _ot_appr=dict(fast_clean=0.88, slow_clean=0.8, slow_messy=0.4, average=0.65)[arch],
        _lpo_renew_lag=dict(fast_clean=0, slow_clean=1, slow_messy=2, average=1)[arch],
        _temper=dict(fast_clean=-1.0, slow_clean=-0.5, slow_messy=0.9, average=0.0)[arch],
        _sign_speed=dict(fast_clean=-1.5, slow_clean=1.5, slow_messy=2.5, average=0.0)[arch],
    ))
CL = {c["client_id"]: c for c in clients}

# ------------------------------------------------------------------ LPOs (12-month blocks, renewal can lag)
lpo_rows, lpo_by_client = [], {}
for c in clients:
    monthly = c["heads_contracted"] * c["rate_per_head_aed"] * 1.12
    blocks, start = [], pd.Period(c["contract_start_month"], freq="M")
    k = 1
    while start <= CURRENT_MONTH:
        lag = int(max(0, rng.poisson(c["_lpo_renew_lag"]))) if k > 1 else 0
        valid_from = start + lag
        valid_to = start + 11
        value = round(monthly * 12 * rng.uniform(0.85, 1.12), -3)
        lpo = dict(lpo_number=f"LPO-{c['client_id'][-3:]}-{k:02d}", client_id=c["client_id"],
                   covers_from=str(start), valid_from=str(valid_from), valid_to=str(valid_to),
                   lpo_value_aed=value)
        blocks.append(lpo); lpo_rows.append(lpo)
        start = start + 12; k += 1
    lpo_by_client[c["client_id"]] = blocks

# ------------------------------------------------------------------ one invoice
REASON_CODES = ["TS_MISMATCH", "HC_DISCREPANCY", "OT_UNAPPROVED", "LPO_ISSUE", "RATE_DISPUTE", "DOCS_MISSING", "SLA_PENALTY"]
RESOLVE_DAYS = {"TS_MISMATCH": (12, 35), "HC_DISCREPANCY": (8, 25), "OT_UNAPPROVED": (10, 30), "LPO_ISSUE": (15, 45),
                "RATE_DISPUTE": (20, 50), "DOCS_MISSING": (3, 10), "SLA_PENALTY": (7, 20), "SERVICE_QUALITY": (10, 30)}
lpo_used = {cid: {} for cid in CL}


def simulate(c, m, inv_no, settle=True):
    month_end = m.to_timestamp(how="end").normalize()
    summer, ramadan = m.month in (6, 7, 8), (m.year, m.month) in [(2025, 3), (2026, 2), (2026, 3)]
    sec_line = SERVICE_LINES[c["service_line"]]

    # stage 3: deployment and attendance
    gap = float(np.clip(rng.normal(0.03 + 0.035 * summer + 0.02 * ramadan, 0.035), 0, 0.3))
    heads = max(1, round(c["heads_contracted"] * (1 - gap)))
    gap_pct = round(100 * (c["heads_contracted"] - heads) / c["heads_contracted"], 1)
    relief_share = round(float(np.clip(rng.beta(2, 18) + 0.03 * summer, 0, 0.5)), 3)
    absence = round(float(np.clip(rng.beta(2, 30) + 0.02 * summer, 0, 0.3)), 3)
    ot_per_head = rng.gamma(2, 3.2) * sec_line[2] * (1.4 if summer and c["sector"] in ("Mall", "Hospital") else 1)
    ot_hours = int(heads * ot_per_head)
    ot_pre = int(rng.random() < c["_ot_appr"])
    method = c["attendance_method"]
    var_scale = {"Paper": 14, "Biometric": 3, "App": 2}[method]
    ts_variance = int(abs(rng.normal(0, var_scale)) * (1 + heads / 60) + (gap_pct > 6) * rng.integers(0, 12))

    # stage 5: timesheet sign-off
    sign_days = max(0, rng.normal(3 + c["approval_layers"] * 1.1 + c["_sign_speed"] + {"Paper": 3, "Biometric": 0.5, "App": 0}[method]
                                  + (3 if (not ot_pre and ot_per_head > 6) else 0) + ts_variance / 15, 2))
    p_unsigned = 0.04 + 0.06 * (sign_days > 9)
    status = rng.choice(["Signed", "Signed with remarks", "Unsigned"],
                        p=[max(0.0, 1 - p_unsigned - (0.08 + ts_variance / 150)), min(0.6, 0.08 + ts_variance / 150), p_unsigned])
    if status == "Unsigned":  # invoice pushed out without waiting for sign-off
        sign_days_eff, signoff_date = None, pd.NaT
        days_to_inv = int(rng.integers(2, 6))
    else:
        sign_days_eff = int(round(sign_days))
        signoff_date = month_end + pd.Timedelta(days=sign_days_eff)
        days_to_inv = sign_days_eff + int(rng.integers(0, 4))
    invoice_date = month_end + pd.Timedelta(days=days_to_inv)

    # stage 6: invoice and LPO match
    ot_rate = 21 if c["billing_basis"] == "Per hour" else 17
    net = heads * c["rate_per_head_aed"] + ot_hours * ot_rate
    rate_ok = int(rng.random() > (0.06 if m.month == 1 else 0.025))  # January escalations get missed
    if not rate_ok:
        net *= rng.uniform(1.03, 1.08)
    sla_ded = round(net * rng.uniform(0.01, 0.03), 2) if (c["sla_penalty_clause"] and gap_pct > 8) else 0.0
    amount = round((net - sla_ded) * 1.05, 2)
    docs_attached = int(rng.random() > (0.12 if c["submission_channel"] == "Email" else 0.04))

    lpo_status, lpo_no, lpo_bal = "Missing on invoice", "", np.nan
    for b in lpo_by_client[c["client_id"]]:
        if pd.Period(b["covers_from"], freq="M") <= m <= pd.Period(b["valid_to"], freq="M"):
            used = lpo_used[c["client_id"]].get(b["lpo_number"], 0.0)
            lpo_bal = round(b["lpo_value_aed"] - used, 2)
            lpo_no = b["lpo_number"]
            if m < pd.Period(b["valid_from"], freq="M"):
                lpo_status = "Not yet renewed"
            elif lpo_bal < amount:
                lpo_status = "Insufficient balance"
            else:
                lpo_status = "Valid"
            lpo_used[c["client_id"]][b["lpo_number"]] = used + amount
            break
    if lpo_status == "Valid" and rng.random() < 0.03:
        lpo_status = "Missing on invoice"
    lpo_valid = int(lpo_status == "Valid")

    terms = c["payment_terms_days"]
    due_date = invoice_date + pd.Timedelta(days=terms)
    payroll_cost = round(heads * rng.uniform(*sec_line[1]) * 1.18 + ot_hours * 9, 2)  # incl. accommodation, transport share

    row = dict(
        invoice_id=f"INV-{inv_no:05d}", client_id=c["client_id"], service_month=str(m),
        month_end_date=month_end.date(), signoff_date=signoff_date, invoice_date=invoice_date.date(), due_date=due_date.date(),
        wps_pay_date=(month_end + pd.Timedelta(days=1)).date(),
        heads_deployed=heads, headcount_gap_pct=gap_pct, relief_worker_share=relief_share, absence_rate=absence,
        ot_hours=ot_hours, ot_preapproved=ot_pre, timesheet_variance_hours=ts_variance,
        timesheet_status=status, days_to_signoff=sign_days_eff, days_monthend_to_invoice=days_to_inv,
        lpo_number=lpo_no, lpo_status=lpo_status, lpo_valid=lpo_valid, lpo_balance_before_aed=lpo_bal,
        rate_matches_contract=rate_ok, docs_attached=docs_attached, sla_deduction_aed=sla_ded,
        invoice_amount_aed=amount, payroll_cost_aed=payroll_cost,
    )
    if not settle:
        return row

    # stage 7: client acknowledgement, approval, dispute
    ack = invoice_date + pd.Timedelta(days=int(max(0, rng.normal({"Client portal": 1, "Email": 4, "Hand delivery": 6}[c["submission_channel"]], 1.5))))
    triggers = {
        "TS_MISMATCH": (status != "Signed") * 1.0 + ts_variance / 25,
        "HC_DISCREPANCY": max(0, gap_pct - 5) / 6,
        "OT_UNAPPROVED": (not ot_pre) * min(ot_per_head / 6, 1.6),
        "LPO_ISSUE": 1.6 * (not lpo_valid),
        "RATE_DISPUTE": 1.8 * (not rate_ok),
        "DOCS_MISSING": 1.3 * (not docs_attached),
        "SLA_PENALTY": 0.6 * (sla_ded > 0),
    }
    z = -3.0 + c["_temper"] + sum(triggers.values()) * 0.95
    dispute = int(rng.random() < 1 / (1 + np.exp(-z)))
    reasons, raised, resolved, disputed_amt, resolution = [], pd.NaT, pd.NaT, 0.0, ""
    if dispute:
        w = np.array([max(v, 0.02) for v in triggers.values()]); w /= w.sum()
        k = 1 + int(rng.random() < 0.3)
        reasons = list(rng.choice(list(triggers), size=k, replace=False, p=w))
        if sum(triggers.values()) < 0.3 and rng.random() < 0.5:
            reasons = ["SERVICE_QUALITY"]
        raised = ack + pd.Timedelta(days=int(rng.integers(3, 8 + 4 * c["approval_layers"])))
        fix = max(rng.integers(*RESOLVE_DAYS[r]) for r in reasons)
        resolved = raised + pd.Timedelta(days=int(fix))
        disputed_amt = round(amount * rng.uniform(0.03, 0.4), 2)
        resolution = rng.choice(["Credit note", "Reissued invoice", "Withdrawn by client"], p=[0.45, 0.4, 0.15])

    # stage 8: payment
    base = invoice_date + pd.Timedelta(days=float(terms + c["_delay"] + (c["approval_layers"] - 2) * 4
                                                  + (8 if c["client_ownership"] == "Government" and m.month in (11, 12) else 0)
                                                  + (9 if c["client_ownership"] == "Private SME" else 0)
                                                  + rng.normal(0, 8)))
    pay = base
    if dispute:
        pay = max(base, resolved + pd.Timedelta(days=int(rng.integers(8, 28))))
    if rng.random() < 0.012:
        pay = pay + pd.Timedelta(days=int(rng.uniform(90, 220)))
    pay = max(pay, invoice_date + pd.Timedelta(days=5)).normalize()
    late = pay > pd.Timestamp(due_date)
    first_fu = (pd.Timestamp(due_date) + pd.Timedelta(days=int(rng.integers(4, 25)))) if late else pd.NaT
    if pd.notna(first_fu) and first_fu >= pay:
        first_fu = pd.NaT
    short = round(disputed_amt * (resolution == "Credit note") * rng.uniform(0.3, 1.0), 2)
    if pay > SNAPSHOT:  # still open on snapshot date
        pay = pd.NaT
        if pd.notna(resolved) and resolved > SNAPSHOT:
            resolved, resolution = pd.NaT, "Open"
        if pd.notna(raised) and raised > SNAPSHOT:
            raised, resolved, reasons, dispute, disputed_amt, resolution = pd.NaT, pd.NaT, [], 0, 0.0, ""
        if pd.notna(first_fu) and first_fu > SNAPSHOT:
            first_fu = pd.NaT
        short = 0.0
    row.update(client_ack_date=ack.date(), dispute_raised=dispute, dispute_reasons="; ".join(reasons),
               dispute_raised_date=raised, dispute_resolved_date=resolved, disputed_amount_aed=disputed_amt,
               dispute_resolution=resolution, first_followup_date=first_fu, short_paid_aed=short, payment_date=pay)
    return row


rows, n = [], 1
for m in HIST_MONTHS:
    for c in clients:
        if m >= pd.Period(c["contract_start_month"], freq="M"):
            rows.append(simulate(c, m, n)); n += 1
inv = pd.DataFrame(rows)
cur = pd.DataFrame([simulate(c, CURRENT_MONTH, n + i, settle=False) for i, c in enumerate(clients)
                    if CURRENT_MONTH >= pd.Period(c["contract_start_month"], freq="M")])
cur["invoice_id"] = [f"DRAFT-{i+1:04d}" for i in range(len(cur))]

date_cols = ["month_end_date", "signoff_date", "invoice_date", "due_date", "wps_pay_date", "client_ack_date",
             "dispute_raised_date", "dispute_resolved_date", "first_followup_date", "payment_date"]
for d in (inv, cur):
    for col in date_cols:
        if col in d:
            d[col] = pd.to_datetime(d[col])

inv["invoice_status"] = np.where(inv["payment_date"].notna(), "Paid", "Open")
inv["days_to_pay"] = (inv["payment_date"] - inv["invoice_date"]).dt.days
inv["paid_late"] = np.where(inv["payment_date"].notna(), (inv["payment_date"] > inv["due_date"]).astype(float), np.nan)


# ------------------------------------------------------------------ client history (past, paid invoices only)
def add_history(target, history):
    out = {k: [] for k in ["prev_invoices_paid", "prev_avg_days_to_pay", "prev_late_rate", "prev_dispute_rate",
                           "last_paid_invoice_late", "open_invoices_count", "open_amount_aed"]}
    hist_by_client = {cid: g for cid, g in history.groupby("client_id")}
    for _, r in target.iterrows():
        g = hist_by_client.get(r["client_id"])
        if g is None:
            paid = still_open = history.iloc[0:0]
        else:
            before = g[g["invoice_date"] < r["invoice_date"]]
            paid = before[before["payment_date"].notna() & (before["payment_date"] < r["invoice_date"])]
            still_open = before[~(before["payment_date"].notna() & (before["payment_date"] < r["invoice_date"]))]
        out["prev_invoices_paid"].append(len(paid))
        out["prev_avg_days_to_pay"].append(round(paid["days_to_pay"].mean(), 1) if len(paid) else np.nan)
        out["prev_late_rate"].append(round(paid["paid_late"].mean(), 3) if len(paid) else np.nan)
        out["prev_dispute_rate"].append(round(paid["dispute_raised"].mean(), 3) if len(paid) else np.nan)
        out["last_paid_invoice_late"].append(paid.sort_values("payment_date")["paid_late"].iloc[-1] if len(paid) else np.nan)
        out["open_invoices_count"].append(len(still_open))
        out["open_amount_aed"].append(round(still_open["invoice_amount_aed"].sum(), 2))
    for k, v in out.items():
        target[k] = v
    return target


inv = add_history(inv, inv)
cur = add_history(cur, inv)

profile = ["client_id", "sector", "client_ownership", "emirate", "service_line", "payment_terms_days", "billing_basis",
           "approval_layers", "heads_contracted", "attendance_method", "submission_channel", "sla_penalty_clause"]
cl_df = pd.DataFrame(clients)
inv = inv.merge(cl_df[profile], on="client_id", how="left")
cur = cur.merge(cl_df[profile], on="client_id", how="left")

ORDER = (["invoice_id", "client_id", "service_month", "month_end_date", "signoff_date", "invoice_date", "due_date", "wps_pay_date"]
         + profile[1:]
         + ["prev_invoices_paid", "prev_avg_days_to_pay", "prev_late_rate", "prev_dispute_rate", "last_paid_invoice_late",
            "open_invoices_count", "open_amount_aed",
            "heads_deployed", "headcount_gap_pct", "relief_worker_share", "absence_rate", "ot_hours", "ot_preapproved",
            "timesheet_variance_hours", "timesheet_status", "days_to_signoff", "days_monthend_to_invoice",
            "lpo_number", "lpo_status", "lpo_valid", "lpo_balance_before_aed", "rate_matches_contract", "docs_attached",
            "sla_deduction_aed", "invoice_amount_aed", "payroll_cost_aed"])
POST = ["client_ack_date", "dispute_raised", "dispute_reasons", "dispute_raised_date", "dispute_resolved_date",
        "disputed_amount_aed", "dispute_resolution", "first_followup_date", "short_paid_aed", "payment_date",
        "invoice_status", "days_to_pay", "paid_late"]
inv = inv[ORDER + POST].sort_values(["invoice_date", "client_id"]).reset_index(drop=True)
cur = cur[ORDER].reset_index(drop=True)

# ------------------------------------------------------------------ deliberate mess (history file only)
mess = inv.copy()
idx = rng.choice(mess.index, 28, replace=False)
mess.loc[idx, "sector"] = mess.loc[idx, "sector"].map(
    {"Mall": "mall", "Office": "OFFICE", "Residential": "Residential ", "Hospital": "Hosp.", "Government": "Govt", "Hospitality": "hospitality"})
for col, k in [("attendance_method", 30), ("ot_hours", 22), ("absence_rate", 18), ("timesheet_variance_hours", 15)]:
    mess.loc[rng.choice(mess.index, k, replace=False), col] = np.nan
idx = rng.choice(mess.index, 5, replace=False)
mess.loc[idx, "invoice_amount_aed"] = mess.loc[idx, "invoice_amount_aed"] * 10
mess = pd.concat([mess, mess.sample(9, random_state=3)]).sort_values(["invoice_date", "client_id"]).reset_index(drop=True)

# ------------------------------------------------------------------ payroll (Jun to Oct 2026) for WPS checks
# Ministerial Resolution 340 of 2026 (reported, in force 1 Jun 2026): wages due on the 1st of the following month.
late_ratio_by_client = inv[inv["invoice_status"] == "Paid"].groupby("client_id")["paid_late"].mean()
pay_rows, e = [], 1
for c in clients:
    if CURRENT_MONTH < pd.Period(c["contract_start_month"], freq="M"):
        continue
    lo, hi = SERVICE_LINES[c["service_line"]][1]
    trade = {"Security": ["Security guard", "Security supervisor"], "Technical (MEP)": ["HVAC technician", "Electrician", "Plumber", "MEP helper"],
             "Front office and supervision": ["Receptionist", "Site supervisor", "Facility coordinator"]}[c["service_line"]]
    for _ in range(c["heads_contracted"]):
        emp = dict(employee_id=f"E{e:05d}", person_code=f"99{rng.integers(10**11, 10**12 - 1)}", client_id=c["client_id"],
                   trade=rng.choice(trade), basic_salary_aed=int(rng.uniform(lo, hi) / 50) * 50,
                   allowances_aed=int(rng.choice([0, 150, 250, 400])), iban_on_file=int(rng.random() > 0.01))
        e += 1
        for m in pd.period_range("2026-06", "2026-10", freq="M"):
            dim = m.days_in_month
            lwop = int(rng.random() < 0.05) * int(rng.integers(1, 6))
            days_paid = dim - lwop
            ot = float(np.clip(rng.gamma(2, 9) * SERVICE_LINES[c["service_line"]][2], 0, 95))
            hourly = emp["basic_salary_aed"] / 30 / 8
            ot_mult = 1.25 if rng.random() > 0.03 else 1.0  # occasional wrong OT rate
            fixed = round((emp["basic_salary_aed"] + emp["allowances_aed"]) * days_paid / dim, 2)
            variable = round(ot * hourly * ot_mult, 2)
            due = (m + 1).to_timestamp()
            # cash squeeze: payroll slips when this client's invoices are paid late
            slip_p = 0.02 + 0.10 * late_ratio_by_client.get(c["client_id"], 0.4) * (m.month in (7, 8))
            pay_date = due + pd.Timedelta(days=int(rng.integers(1, 12))) if rng.random() < slip_p else due - pd.Timedelta(days=int(rng.integers(0, 3)))
            pay_rows.append(dict(**{k: v for k, v in emp.items()}, payroll_month=str(m), days_in_month=dim,
                                 days_paid=days_paid if rng.random() > 0.004 else dim + 1, lwop_days=lwop,
                                 ot_hours=round(ot, 1), ot_rate_multiplier_used=ot_mult,
                                 fixed_income_aed=fixed, variable_income_aed=variable, wps_due_date=due.date(),
                                 pay_date=pay_date.date()))
payroll = pd.DataFrame(pay_rows)

# ------------------------------------------------------------------ write
mess.to_csv(OUT / "invoices.csv", index=False)
cur.to_csv(OUT / "current_batch.csv", index=False)
cl_df[[c for c in cl_df.columns if not c.startswith("_")]].to_csv(OUT / "clients.csv", index=False)
pd.DataFrame(lpo_rows).to_csv(OUT / "lpos.csv", index=False)
payroll.to_csv(OUT / "payroll.csv", index=False)
print("invoices", mess.shape, "current_batch", cur.shape, "payroll", payroll.shape, "lpos", len(lpo_rows))
