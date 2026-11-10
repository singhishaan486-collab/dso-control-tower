import pandas as pd
import streamlit as st

import components as ui
from core import charts, overview as ov
from core.descriptive import snapshot_date

st.set_page_config(page_title="Overview", layout="wide")
ui.apply_style()

d = ui.get_data()
inv = d["inv"]
names = d["clients"].set_index("client_id")["client_name"]

title, download = st.columns([5, 1], vertical_alignment="center")
title.markdown("## Overview")

f1, f2, f3 = st.columns(3)
timeframe = f1.selectbox("Timeframe", list(ov.TIMEFRAMES), format_func=lambda v: f"Timeframe: {v}",
                         label_visibility="collapsed")
ownership = f2.selectbox("Client ownership", ["All"] + sorted(inv["client_ownership"].unique()),
                         format_func=lambda v: f"Ownership: {v}", label_visibility="collapsed")
sector = f3.selectbox("Sector", ["All"] + sorted(inv["sector"].unique()), format_func=lambda v: f"Sector: {v}",
                      label_visibility="collapsed")

filtered = ov.apply_filters(inv, timeframe, ownership, sector)
scope = ov.apply_filters(inv, "All time", ownership, sector)
with download:
    ui.download_csv(filtered, "overview_invoices.csv", "Download")
if filtered.empty or (filtered["invoice_status"] == "Paid").sum() == 0:
    st.info("No paid invoices match these filters. Try another combination.")
    st.stop()

def change(value, unit: str, scale: float = 1) -> dict:
    """Delta arguments for a metric where lower is better. A change near zero shows as no change."""
    if value is None:
        return {}
    shown = value * scale
    if abs(shown) < 0.05:
        return dict(delta="no change", delta_color="off", delta_arrow="off")
    return dict(delta=f"{shown:+.1f} {unit}", delta_color="inverse")


k = ov.kpi_cards(filtered, inv, scope)
left, right = st.columns([1.05, 1], gap="medium")
with left:
    row1 = st.columns(3)
    with row1[0].container(key="card_clients"):
        st.metric("Active clients", f"{k['clients']}/{k['clients_total']}")
    with row1[1].container(key="card_invoices"):
        st.metric("Invoices", f"{k['invoices']:,}", f"{k['open_invoices']} still open", delta_color="off",
                  delta_arrow="off")
    with row1[2].container(key="card_days"):
        st.metric("Days to pay", f"{k['mean_days_to_pay']:.0f}", help="Average days from invoice to payment.")
    row2 = st.columns(3)
    with row2[0].container(key="card_dso"):
        st.metric("DSO (days)", f"{k['dso']:.1f}", chart_data=k["dso_series"], chart_type="area",
                  help="Change: the last 3 months against the 3 before. Lower is better.",
                  **change(k["dso_change"], "days"))
    with row2[1].container(key="card_late"):
        st.metric("Paid late", f"{k['late_rate']:.0%}", chart_data=k["late_series"], chart_type="area",
                  help="Trend over settled service months only, because recent invoices are not all paid yet.",
                  **change(k["late_change"], "pts", 100))
    with row2[2].container(key="card_dispute"):
        st.metric("Dispute rate", f"{k['dispute_rate']:.0%}", chart_data=k["dispute_series"], chart_type="area",
                  help="Trend over settled service months only.", **change(k["dispute_change"], "pts", 100))

with right.container(key="card_activity"):
    head, pick = st.columns([2, 1], vertical_alignment="center")
    head.html('<div class="ov-title">Activity</div><div class="ov-sub">Last 12 months</div>')
    measure = pick.selectbox("Measure", ["Invoiced (AED)", "Collected (AED)", "Invoices raised"],
                             label_visibility="collapsed")
    activity = ov.monthly_activity(filtered if timeframe == "All time" else scope, measure)
    ui.chart(charts.activity_bars(activity, measure), "overview_activity", config={"displayModeBar": False})

slow, fast = ov.payer_extremes(filtered, names)
left, right = st.columns(2, gap="medium")
scale_note = f'<div class="ov-sub">Average days to pay. The bar runs from 0 to {ov.DAYS_SCALE} days.</div>'
with left.container(key="card_slow"):
    st.html(f'<div class="ov-title">Slowest paying clients</div>{scale_note}')
    ui.progress_rows([dict(name=r["name"], fill=r["fill"], value=f"{r['days']:.0f} days",
                           suffix=f"{r['on_time']:.0%} on time") for _, r in slow.iterrows()], "warm")
with right.container(key="card_fast"):
    st.html(f'<div class="ov-title">Fastest paying clients</div>{scale_note}')
    ui.progress_rows([dict(name=r["name"], fill=r["fill"], value=f"{r['days']:.0f} days",
                           suffix=f"{r['on_time']:.0%} on time") for _, r in fast.iterrows()], "cool")

clients_board = ov.leaderboard(scope, "client_id", names)
sector_board = ov.leaderboard(scope, "sector", n=6)
left, right = st.columns(2, gap="medium")
with left.container(key="card_client_board"):
    st.html('<div class="ov-title">Client leaderboard</div>'
            '<div class="ov-sub">Ranked by share paid on time in the latest 6 settled months, then by days to '
            'pay. Arrows compare with the 6 months before.</div>')
    ui.leaderboard_rows([dict(name=r["name"], rank=r["rank"], change=r["change"],
                              detail=f"{int(r['invoices'])} invoices · {r['on_time']:.0%} on time · "
                                     f"{r['days']:.0f} days to pay") for _, r in clients_board.iterrows()])
with right.container(key="card_sector_board"):
    st.html('<div class="ov-title">Sector leaderboard</div>'
            '<div class="ov-sub">The same ranking for each sector, in the latest 6 settled months.</div>')
    ui.leaderboard_rows([dict(name=r["name"], rank=r["rank"], change=r["change"],
                              detail=f"AED {r['revenue'] / 1e6:.1f}m invoiced · {r['on_time']:.0%} on time")
                         for _, r in sector_board.iterrows()])

st.caption(f"Snapshot date {snapshot_date():%d %B %Y}. {ui.SYNTHETIC_NOTICE}")

with st.expander("How the business turns work into cash"):
    stages = pd.DataFrame([
        (1, "Contract and LPO", "Rates, headcount, payment terms, SLA and LPO agreed with the client", "None yet"),
        (2, "Recruit and mobilise", "Visas, medicals, accommodation, transport", "Outflow before any billing"),
        (3, "Deploy and track attendance", "Staff work shifts. Attendance on paper, biometric or app. OT happens",
         "Running cost"),
        (4, "Payroll via WPS", "Salaries paid through WPS on the 1st of the following month",
         "Largest outflow, fixed date"),
        (5, "Timesheet sign-off", "Client FM team verifies and signs the monthly timesheet",
         "Delay here delays the invoice"),
        (6, "Invoice", "Tax invoice with 5% VAT, matched to the LPO and signed timesheet", "DSO clock starts"),
        (7, "Client approval and disputes", "FM, procurement and finance review. Disputes raised and resolved",
         "Waiting"),
        (8, "Payment and collections", "Client pays in full, short pays or goes overdue", "Cash finally in"),
    ], columns=["Stage", "Name", "What happens", "Cash effect"])
    ui.table(stages, {"Stage": ui.col_number("Stage", "Order in the order-to-cash process.", "%d", 60),
                      "Name": ui.col_text("Name", width=190), "What happens": ui.col_text("What happens", width=450),
                      "Cash effect": ui.col_text("Cash effect", width=220)})
    ui.download_csv(stages, "process_stages.csv", "Download the process stages")

ui.explainer(
    "The overview puts the numbers an owner checks first in one place. **DSO** shows how many days of sales are "
    "waiting to be collected, and the **late** and **dispute rates** show why. The small trend lines use only "
    "service months that have had time to settle, because recent invoices are not all paid yet and would make "
    "things look better than they are.\n\n"
    "The **leaderboards** rank clients and sectors by the share of invoices paid on time, and the arrows show "
    "who moved up or down against the previous six months, so a slipping client is visible early."
)
