import pandas as pd
import streamlit as st

import components as ui
from core import automation as au, charts

st.set_page_config(page_title="Automation", layout="wide")
ui.page_header("Automation",
               "Checks that run before an invoice goes out or a payroll file is sent. Every result is a "
               "recommendation for a person to act on. Nothing is sent, paid or changed.")

d = ui.get_data()
cfg = ui.config()
ui.get_models()

tab_qa, tab_ledger, tab_wps = st.tabs(["Invoice QA", "Attendance ledger", "WPS check"])

with tab_qa:
    qa, findings = au.invoice_qa(d["current"], d["lpos"], cfg)
    month = qa["service_month"].iloc[0]
    st.caption(f"{len(qa)} draft invoices for the {month} service month, checked against the signed timesheet, "
               "the LPO and the contract rate before they are sent.")
    counts = qa["result"].value_counts()
    c = st.columns(4)
    c[0].metric("Block", int(counts.get("Block", 0)), help="Do not send until fixed.")
    c[1].metric("Warn", int(counts.get("Warn", 0)), help="Can be sent, but check first.")
    c[2].metric("Pass", int(counts.get("Pass", 0)))
    c[3].metric("AED blocked", f"{qa.loc[qa['result'] == 'Block', 'invoice_amount_aed'].sum():,.0f}")

    show = st.pills("Show", ["Block", "Warn", "Pass"], selection_mode="multi", default=["Block", "Warn", "Pass"],
                    key="qa_filter")
    shown = qa[qa["result"].isin(show or [])]
    ui.table(shown, {
        # Twelve columns of full content need about 1,040 px, so at 1440 wide this one table scrolls a little
        # rather than cut off invoice numbers or statuses. It fits fully at 1920.
        "invoice_id": ui.col_text("Invoice", width=98), "client_id": ui.col_text("Client", width=64),
        "invoice_amount_aed": ui.col_money("AED", "Draft invoice amount in AED.", 80),
        "timesheet_status": ui.col_text("Timesheet", width=132), "lpo_status": ui.col_text("LPO", width=135),
        "p_dispute": ui.col_share("Dispute", "The dispute model's score for this invoice. It ranks invoices well, "
                                             "but runs higher than the real rate.", 76),
        "p_late": ui.col_share("Late", "The late payment model's score for this invoice.", 72),
        "blocks": ui.col_number("Blocks", "Checks that stop the invoice.", "%d", 56),
        "warns": ui.col_number("Warns", "Checks to look at before sending.", "%d", 56),
        "result": ui.col_text("Result", width=60),
        "aed_at_risk": ui.col_money("At risk", "Amount in AED times the higher of the two scores.", 78),
        "checks_failed": ui.col_text("Checks failed", width=150)}, height=360, hide=("service_month",))
    st.caption(f"Service month {month} for every row. It is left out of the table above but kept in the download.")
    st.caption("Sorted by AED at risk: the invoice amount times the higher of its dispute and late scores. The "
               "scores come from the saved models and rank invoices well, but run higher than real rates.")
    ui.download_csv(qa, "invoice_qa_results.csv", "Download the invoice results")

    by_check = findings.groupby(["check_id", "severity"]).size().rename("findings").reset_index()
    by_check["label"] = by_check["check_id"] + " (" + by_check["severity"] + ")"
    ui.chart(charts.ranked_bars(by_check, "label", "findings", "Findings", value_format=",.0f"), "automation_findings")
    ui.table(findings, {
        "item_id": ui.col_text("Invoice", width=85), "node": ui.col_text("Stage", width=60),
        "check_id": ui.col_text("Check", width=65), "severity": ui.col_text("Severity", width=70),
        "message": ui.col_text("What was found", width=260),
        "recommended_action": ui.col_text("Recommended action", width=260),
        "owner": ui.col_text("Owner", width=80)}, height=420)
    ui.download_csv(findings, "invoice_qa_findings.csv", "Download every finding")

LEDGER_COLUMNS = {
    "seq": ui.col_number("Record", "Position in the chain.", "%d", 60), "date": ui.col_text("Day", width=90),
    "employee_id": ui.col_text("Employee", width=80), "shift": ui.col_text("Shift", width=55),
    "check_in": ui.col_text("Check in", width=95), "method": ui.col_text("Method", width=75),
    "normal_hours": ui.col_number("Hours", "Normal hours worked.", "%.1f", 60),
    "ot_hours": ui.col_number("OT", "Overtime hours.", "%.1f", 50),
    "check_out": ui.col_text("Check out", width=95), "ot_approval_ref": ui.col_text("OT approval", width=90),
    "prev_hash": ui.col_text("Previous hash", "Hash of the record before. Click a cell to see all of it.", 95),
    "hash": ui.col_text("Hash", "This record's hash. Click a cell to see all of it.", 95),
}

with tab_ledger:
    st.caption("A hash-chained record of daily attendance. Each record carries the fingerprint of the one before "
               "it, and both parties sign the last record of every day.")
    clients = d["clients"].set_index("client_id")
    client_id = st.selectbox("Client", d["current"]["client_id"].tolist())
    invoice = d["current"].set_index("client_id").loc[client_id]
    invoice = invoice.copy()
    invoice["client_id"] = client_id

    @st.cache_data(show_spinner="Building the ledger...")
    def build(cid: str):
        employees = d["payroll"].loc[d["payroll"]["client_id"] == cid, "employee_id"].unique().tolist()
        return au.generate_month(clients.loc[cid], invoice, employees, cfg["ledger"])

    records, seals = build(client_id)
    summary = au.ledger_summary(records, invoice)
    c = st.columns(4)
    c[0].metric("Records", f"{summary['records']:,}")
    c[1].metric("Staff", summary["employees"])
    c[2].metric("OT hours in ledger", f"{summary['ot_hours']:,.0f}", f"Invoice says {summary['invoice_ot_hours']:,.0f}",
                delta_color="off")
    c[3].metric("Shifts worked", f"{summary['shifts_worked']:,}", f"Expected {summary['shifts_expected']:,}",
                delta_color="off")

    if st.button("Verify the chain", type="primary"):
        ok, seq, reason = au.verify(records, seals, cfg["ledger"])
        (st.success if ok else st.error)(reason if ok else f"Failed at record {seq}: {reason}")

    st.markdown("**Tamper with a record**")
    with st.form("tamper"):
        f1, f2, f3 = st.columns(3)
        seq = f1.number_input("Record number", 1, len(records), min(37, len(records)))
        field = f2.selectbox("Field", ["normal_hours", "ot_hours", "check_out", "employee_id"])
        value = f3.text_input("New value", "12")
        rehash = st.checkbox("The forger also rebuilds every hash after the edit")
        submitted = st.form_submit_button("Tamper and verify")
    if submitted:
        new_value = float(value) if field.endswith("hours") and value.replace(".", "", 1).isdigit() else value
        edited = au.tamper(records, int(seq), field, new_value, rehash)
        ok, bad_seq, reason = au.verify(edited, seals, cfg["ledger"])
        if ok:
            st.success("The edit was not detected. That only happens if the new value equals the old one.")
        else:
            st.error(f"Caught at record {bad_seq}: {reason}.")
            original = next(r for r in records if r["seq"] == int(seq))
            changed = next(r for r in edited if r["seq"] == int(seq))
            ui.table(pd.DataFrame([original, changed]).assign(version=["Sealed", "After the edit"]),
                     {"version": ui.col_text("Version", width=110), **LEDGER_COLUMNS})
            if rehash:
                st.caption("Rebuilding the hashes keeps the chain consistent, but the forger cannot reproduce the "
                           "client's daily seal without the client's key, so the day still fails.")

    st.markdown("**The chain** (first 50 records)")
    ui.table(pd.DataFrame(records[:50]), LEDGER_COLUMNS, height=360)
    st.markdown("**Daily seals**")
    seal_table = pd.DataFrame(seals)
    ui.table(seal_table, {"date": ui.col_text("Day", width=95),
                          "last_seq": ui.col_number("Last record", "Sequence number of the day's last record.",
                                                    "%d", 90),
                          "last_hash": ui.col_text("Last hash", "Hash of the day's last record.", 250),
                          "supplier_seal": ui.col_text("Our seal", "HMAC of the last hash with our key.", 250),
                          "client_seal": ui.col_text("Client seal", "HMAC of the last hash with the client's "
                                                                    "key.", 250)}, height=320)
    ui.download_csv(pd.DataFrame(records), f"attendance_ledger_{client_id}.csv", "Download the full ledger")
    st.info("**What this proves:** any edit after a day is sealed can be detected and pinned to the exact record. "
            "**What it does not prove:** that the entry was true when it was captured. A wrong check-in recorded "
            "on the day is sealed like any other. A shared, permissioned ledger that both companies run would be "
            "the next step. The keys here are demo keys from the config file.")

with tab_wps:
    wps, monthly = au.wps_check(d["payroll"], cfg)
    st.caption(f"{len(d['payroll']):,} employee pay records from {d['payroll']['payroll_month'].min()} to "
               f"{d['payroll']['payroll_month'].max()}, checked before the WPS file is sent.")
    names = {"WPS-01": "Paid late", "WPS-02": "OT below legal rate", "WPS-03": "OT above monthly limit",
             "WPS-04": "Days paid above days in month", "WPS-05": "Missing IBAN",
             "WPS-06": "Establishment on-time share too low"}
    counts = wps["check_id"].value_counts()
    c = st.columns(6)
    for column, (check_id, name) in zip(c, names.items()):
        column.metric(f"{check_id}: {name}", int(counts.get(check_id, 0)))

    left, right = st.columns(2)
    with left:
        st.markdown("**Share of staff paid on time each month**")
        fig = charts.columns(monthly, "payroll_month", "on_time_share", "Paid on time", percent=True)
        fig.add_hline(y=cfg["wps"]["establishment_on_time_min"], line=dict(color=charts.ORANGE, width=1.5),
                      annotation=dict(text=f"Minimum {cfg['wps']['establishment_on_time_min']:.0%}"))
        ui.chart(fig, "automation_wps_on_time")
    with right:
        st.markdown("**The cash squeeze: late clients, late salaries**")
        squeeze = au.payroll_vs_invoice_lateness(d["payroll"], d["inv"])
        ui.chart(charts.xy_scatter(squeeze, "invoice_late_rate", "payroll_late_rate", "client_id",
                                          "Client's invoices paid late", "Salaries paid late"), "automation_squeeze")
        st.caption(f"Each dot is a client. The correlation is "
                   f"{squeeze['invoice_late_rate'].corr(squeeze['payroll_late_rate']):.2f}: where clients pay us "
                   "late, salaries for their sites slip too.")

    st.markdown("**Findings by month and client**")
    by_month = wps.groupby(["payroll_month", "check_id"]).size().unstack(fill_value=0).reset_index()
    by_client = (wps[wps["client_id"] != "All"].groupby(["client_id", "check_id"]).size()
                 .unstack(fill_value=0).assign(total=lambda t: t.sum(axis=1))
                 .sort_values("total", ascending=False).reset_index())
    left, right = st.columns(2)
    check_cols = {code: ui.col_number(code, f"{code}: {name}.", "%d", 64) for code, name in names.items()}
    with left:
        ui.table(by_month, {"payroll_month": ui.col_text("Payroll month", width=110), **check_cols})
    with right:
        ui.table(by_client, {"client_id": ui.col_text("Client", width=75), **check_cols,
                             "total": ui.col_number("Total", "All WPS findings for this client.", "%d", 58)},
                 height=300)
    ui.table(wps, {"item_id": ui.col_text("Employee and month", width=135), "client_id": ui.col_text("Client", width=65),
                   "payroll_month": ui.col_text("Month", width=70), "node": ui.col_text("Stage", width=55),
                   "check_id": ui.col_text("Check", width=70), "severity": ui.col_text("Severity", width=70),
                   "message": ui.col_text("What was found", width=210),
                   "recommended_action": ui.col_text("Recommended action", width=190),
                   "owner": ui.col_text("Owner", width=75)}, height=300)
    ui.download_csv(wps, "wps_findings.csv", "Download every WPS finding")
    st.caption("The rules follow secondary reporting of Ministerial Resolution 340 of 2026 and the 2 hours a day "
               "OT cap. Check them against MOHRE before real use.")

ui.explainer(
    "**Rule engines** are the right tool here because the rules are known and must be explained. A model would "
    "guess, while a check states exactly which rule failed and what to do.\n\n"
    "**Invoice QA** runs a three-way match of each draft against the signed timesheet, the LPO and the contract "
    "rate. It catches the problems behind most disputes while they can still be fixed, and the model scores "
    "rank which invoices to fix first.\n\n"
    "**The attendance ledger** uses SHA-256 hash chaining, where each record includes the previous record's "
    "hash, and HMAC daily seals signed by both parties. It stands in for a blockchain: it proves that sealed "
    "records were not changed, which removes arguments about whose hours are right.\n\n"
    "**The WPS check** stops payroll problems before the file goes to the bank, where they become fines."
)
