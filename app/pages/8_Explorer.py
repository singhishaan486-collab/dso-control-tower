import streamlit as st

import components as ui
from core import charts, viz

st.set_page_config(page_title="Explorer", layout="wide")
ui.page_header("Explorer", "Look at clients from several angles at once. Select clients on the first chart and the "
                           "charts under it follow.")

d = ui.get_data()
END = ui.config()["split"]["test_end_month"]
names = d["clients"].set_index("client_id")["client_name"]


@st.cache_data(show_spinner="Preparing the client views...")
def prepare(inv, end: str):
    paid = viz.settled(inv, end)
    monthly, skipped = viz.client_monthly(paid)
    return paid, viz.client_summary(paid, names), viz.outcome_mix(paid, names), monthly, skipped


paid, summary, mix, monthly, skipped = prepare(d["inv"], END)
y_max = float(max(summary["mean_days_to_pay"].max(), monthly["mean_days_to_pay"].max())) * 1.1
st.caption(f"Only service months up to {END} are used, and every invoice in them has been paid, so recent unpaid "
           f"invoices do not make clients look better than they are. That is {len(paid):,} invoices from "
           f"{len(summary)} clients.")


@st.fragment
def linked_views() -> None:
    """Client scatter with selection. The charts and table below show only the selected clients."""
    st.subheader("Pick clients, see what they have in common")
    view = st.session_state.get("explorer_view", 0)
    event = ui.chart(charts.client_scatter(summary, y_max, float(summary["invoiced_aed"].max())),
                     f"explorer_clients_{view}", config=charts.SELECT_CONFIG, on_select="rerun",
                     selection_mode=("points", "box", "lasso"))
    st.caption("How to read this: each bubble is a client. Further right means more of its invoices were paid "
               "late, higher means it takes longer to pay, and a bigger bubble means more money invoiced. Colour "
               "and shape show ownership. Drag a box, draw a lasso or click bubbles to select clients.")
    points = event.selection.points if event and event.selection else []
    chosen = {p["customdata"][0] for p in points if p.get("customdata")}
    picked = summary[summary["client_id"].isin(chosen)] if chosen else summary
    invoices = paid[paid["client_id"].isin(picked["client_id"])]

    left, right = st.columns([4, 1], vertical_alignment="center")
    if chosen:
        text = (f"Showing {len(picked)} of {len(summary)} clients. They take {invoices['days_to_pay'].mean():.0f} "
                f"days to pay on average and {invoices['paid_late'].mean():.0%} of their invoices are late, "
                f"against {paid['days_to_pay'].mean():.0f} days and {paid['paid_late'].mean():.0%} for all clients.")
    else:
        text = (f"Showing all {len(summary)} clients: {paid['days_to_pay'].mean():.0f} days to pay on average and "
                f"{paid['paid_late'].mean():.0%} of invoices late. Select bubbles to compare a group.")
    left.markdown(text)
    right.button("Clear selection", key="explorer_clear", disabled=not chosen, width="stretch",
                 on_click=lambda: st.session_state.update(explorer_view=view + 1))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Days to pay**")
        days = charts.histogram(invoices["days_to_pay"], "Days to pay", invoices["days_to_pay"].median(), "Median")
        days.update_xaxes(range=[0, float(paid["days_to_pay"].max()) * 1.05])
        ui.chart(days, "explorer_days")
    with c2:
        st.markdown("**Dispute reasons**")
        reasons = viz.reason_counts(invoices)
        if reasons.empty:
            st.info("None of these clients' invoices were disputed.")
        else:
            ui.chart(charts.ranked_bars(reasons, "reason", "disputes", "Disputes", value_format=",.0f",
                                        color=charts.ORANGE), "explorer_reasons")
    with c3:
        st.markdown("**Sector mix**")
        ui.chart(charts.ranked_bars(viz.sector_mix(invoices), "sector", "share", "Share of invoiced AED",
                                    percent=True), "explorer_sectors")
    ui.table(picked, {
        "client_id": ui.col_text("Client", width=75), "client_name": ui.col_text("Name", width=130),
        "client_ownership": ui.col_text("Ownership", width=125), "sector": ui.col_text("Sector", width=100),
        "invoices": ui.col_number("Invoices", "Settled invoices for this client.", "%d", 70),
        "late_rate": ui.col_share("Paid late", "Share of this client's invoices paid after the due date.", 110),
        "mean_days_to_pay": ui.col_number("Days to pay", "Average days from invoice to payment.", "%.0f", 95),
        "dispute_rate": ui.col_share("Disputed", "Share of this client's invoices that were disputed.", 110),
        "invoiced_aed": ui.col_money("Invoiced (AED)", "Total invoiced in the settled months.", 125),
    }, height=320)
    ui.download_csv(picked, "explorer_selected_clients.csv", "Download these clients")


linked_views()

st.subheader("How clients moved over time")
ui.chart(charts.animated_clients(monthly, y_max), "explorer_animation")
months = sorted(monthly["month"].unique())
first, last = monthly[monthly["month"] == months[0]], monthly[monthly["month"] == months[-1]]
st.caption("How to read this: each bubble is a client, measured over the three service months up to the month on "
           "the slider. Press Play to watch the months go by, or drag the slider to a month. Axes and bubble sizes "
           f"stay fixed so movement is real. {skipped} client-months are left out because their three-month "
           "window held fewer than 3 settled invoices. Clients bill about once a month, so a window usually holds "
           "three invoices and the late rate can only be 0%, 33%, 67% or 100%. That is why bubbles line up in "
           "columns.")
st.markdown(f"In the window ending {months[0]}, the average client took {first['mean_days_to_pay'].mean():.0f} days "
            f"to pay and paid {first['late_rate'].mean():.0%} of invoices late. In the window ending {months[-1]}, "
            f"it took {last['mean_days_to_pay'].mean():.0f} days and paid {last['late_rate'].mean():.0%} late.")
ui.download_csv(monthly, "explorer_rolling_three_months.csv", "Download the rolling three-month figures")


@st.fragment
def outcome_triangle() -> None:
    """Ternary plot of each client's on time, late and disputed shares."""
    st.subheader("How each client's invoices end")
    color_by = st.segmented_control("Colour by", ["Ownership", "Segment"], default="Ownership", required=True,
                                    key="explorer_ternary_colour")
    segment_of = None
    if color_by == "Segment":
        segment_of = ui.get_models()["segments"]["clients"].set_index("client_id")["segment"].to_dict()
    ui.chart(charts.outcome_ternary(mix, color_by, segment_of), "explorer_ternary")
    st.caption("How to read this: every invoice ends one of three ways that never overlap, so the three shares add "
               "up to 100%. A client near the top corner pays on time without disputes, near the left corner it is "
               "mostly late, and near the right corner it is mostly disputed. Bubble size is money invoiced.")
    main = mix[list(viz.MIX_GROUPS)].idxmax(axis=1).map(viz.MIX_GROUPS)
    counts = main.value_counts()
    worst = mix.loc[mix["disputed_share"].idxmax()]
    st.markdown(f"{counts.get('On time, no dispute', 0)} of {len(mix)} clients have most invoices on time without "
                f"a dispute, {counts.get('Late, no dispute', 0)} are mostly late and "
                f"{counts.get('Disputed', 0)} are mostly disputed. The most disputed client is "
                f"{worst['client_id']}, with {worst['disputed_share']:.0%} of its invoices disputed.")
    ui.download_csv(mix, "explorer_outcome_mix.csv", "Download the outcome mix")


outcome_triangle()

ui.explainer(
    "**Linked views** (brushing) let you ask a question with the mouse: select a group of clients on the scatter "
    "and the days to pay, dispute reasons, sector mix and table below show only that group. It is a quick way to "
    "see what slow payers have in common without writing a filter.\n\n"
    "**The animated bubble chart** shows change over time. Each client is measured over a rolling three-month "
    "window so one odd invoice does not make it jump, and windows with fewer than three settled invoices are "
    "left out.\n\n"
    "**The ternary plot** shows a mix of three parts that add up to 100% in one point per client, which a bar "
    "chart can only do with three bars.\n\n"
    "Only settled service months are used throughout, because recent invoices that are not yet paid would make "
    "late rates look better than they are."
)
