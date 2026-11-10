import streamlit as st

import components as ui
from core import charts, descriptive as ds, viz

st.set_page_config(page_title="Descriptive", layout="wide")
ui.page_header("Descriptive: what is happening",
               "Where DSO stands, which clients and segments drive it, and how long the cash gap is.")

inv = ui.get_data()["inv"]
names = ui.get_data()["clients"].set_index("client_id")["client_name"]
snapshot = ds.snapshot_date()
k = ds.kpis(inv, snapshot)

c = st.columns(3) + st.columns(3)
c[0].metric(f"DSO ({k['dso_window_days']} day)", f"{k['dso']:.1f} days",
            help=f"Open receivables ÷ credit sales in the last {k['dso_window_days']} days × "
                 f"{k['dso_window_days']}, measured on {k['dso_period_end']:%d %b %Y}.")
c[1].metric("Average days to pay", f"{k['mean_days_to_pay']:.1f}", help="Paid invoices only.")
c[2].metric("Paid late", f"{k['late_rate']:.0%}", help="Share of paid invoices paid after the due date.")
c[3].metric("Dispute rate", f"{k['dispute_rate']:.0%}", help="Share of paid invoices the client disputed.")
c[4].metric("Open receivables", f"AED {k['open_ar'] / 1e6:.2f}m", f"{k['open_count']} invoices",
            delta_color="off", help=f"Unpaid on {snapshot:%d %b %Y}.")
c[5].metric("Overdue receivables", f"AED {k['overdue_ar'] / 1e6:.2f}m", f"{k['overdue_count']} invoices",
            delta_color="off", help="Open and past the due date.")

st.subheader("DSO by month")
trend = ds.dso_trend(inv)
st.caption(f"DSO has moved between {trend['dso'].min():.0f} and {trend['dso'].max():.0f} days. "
           "It only starts once a full 90-day window of invoices exists.")
ui.chart(charts.line(trend, "month_end", "dso", "DSO (days)", range_tools=True), "descriptive_dso_trend")
st.caption("How to read this: hover anywhere to read that month. The buttons above the chart zoom to the last 6 or "
           "12 months, and the strip underneath drags to any window.")
with st.expander("Data table"):
    ui.table(trend, {"month_end": ui.col_date("Month end", fmt="MMM YYYY", width=120),
                     "dso": ui.col_number("DSO (days)", "Open receivables over the last 90 days of credit sales, "
                                                        "times 90, on that month end.", "%.1f", 120),
                     "late_rate_of_invoices_raised": ui.col_share(
                         "Paid late", "Share of the invoices raised that month that were paid after the due date.",
                         200)})
ui.download_csv(trend, "dso_trend.csv", "Download the DSO trend")


@st.cache_data(show_spinner="Working out DSO for every day...")
def dso_by_day(df, end, window_days):
    return viz.daily_dso(df, end, window_days)


st.subheader("How far DSO swings inside a month")
window = k["dso_window_days"]
daily = dso_by_day(inv, ds.last_month_end(snapshot), window)
ohlc = viz.monthly_ohlc(daily)
ui.chart(charts.dso_candles(ohlc), "descriptive_dso_candles")
st.caption(f"How to read this: DSO is not a price. Each candle is one month of daily DSO ({window}-day window). The box "
           "runs from the first day to the last day of the month and the thin line from the lowest to the highest "
           "day. A month that ended with DSO higher than it started is orange, because rising DSO is bad; one "
           "that ended lower is cyan. That is the reverse of the usual price chart colours.")
widest = ohlc.loc[ohlc["swing"].idxmax()]
rose = int((ohlc["close"] > ohlc["open"]).sum())
st.markdown(f"The widest swing was in {widest['month']:%B %Y}, when DSO moved between {widest['low']:.1f} and "
            f"{widest['high']:.1f} days. In {rose} of {len(ohlc)} months DSO ended higher than it started. A typical "
            f"month swings by {ohlc['swing'].median():.1f} days, so a single month-end reading can be off by that "
            "much.")
ui.download_csv(ohlc, "dso_monthly_candles.csv", "Download the monthly candles")

st.subheader("Breakdown by segment")
DIMENSIONS = {"Client ownership": "client_ownership", "Sector": "sector", "Service line": "service_line",
              "Emirate": "emirate", "Payment terms": "payment_terms_days", "Attendance method": "attendance_method",
              "Submission channel": "submission_channel", "Client": "client_id"}
MEASURES = {"DSO": ("dso", "DSO (days)", False), "Paid late": ("late_rate", "Share paid late", True),
            "Average days to pay": ("mean_days_to_pay", "Average days to pay", False),
            "Dispute rate": ("dispute_rate", "Dispute rate", True)}
left, right = st.columns(2)
dimension = left.selectbox("Group by", list(DIMENSIONS))
measure = right.selectbox("Measure", list(MEASURES))
column, title, percent = MEASURES[measure]
table = ds.breakdown(inv, DIMENSIONS[dimension])
ui.chart(charts.ranked_bars(table, DIMENSIONS[dimension], column, title, percent=percent), f"descriptive_breakdown_{dimension}")
ui.table(table, {DIMENSIONS[dimension]: ui.col_text(dimension, width=160),
                 "paid_invoices": ui.col_number("Paid invoices", "Paid invoices in this group.", "%d", 110),
                 "late_rate": ui.col_share("Paid late", "Share of paid invoices paid after the due date.", 140),
                 "mean_days_to_pay": ui.col_number("Days to pay", "Average days from invoice to payment.", "%.1f",
                                                   110),
                 "dispute_rate": ui.col_share("Disputed", "Share of paid invoices the client disputed.", 140),
                 "revenue_aed": ui.col_money("Invoiced (AED)", "Total invoiced to this group.", 140),
                 "dso": ui.col_number("DSO (days)", "DSO for this group on the last month end.", "%.1f", 100)})
ui.download_csv(table, f"breakdown_by_{DIMENSIONS[dimension]}.csv", "Download this breakdown")


@st.cache_data(show_spinner=False)
def paid_days(df):
    return viz.paid_days(df)


@st.fragment
def days_spread() -> None:
    """Box or violin of days to pay per group. Its own controls rerun only this block."""
    st.subheader("How spread out payment is")
    paid = paid_days(inv)
    c1, c2, c3 = st.columns([1.2, 1, 1], vertical_alignment="bottom")
    group = c1.selectbox("Group by", list(viz.BOX_GROUPS), key="spread_group")
    split = c2.toggle("Split disputed and not disputed", key="spread_split")
    violin = c3.toggle("Show as violins", key="spread_violin")
    by = viz.BOX_GROUPS[group]
    stats = viz.box_stats(paid, by, split)
    order = list(stats[by].cat.categories)
    ui.chart(charts.days_box(paid, by, group, order, split, violin, float(paid["days_to_pay"].max()) * 1.05),
             "descriptive_days_box")
    if violin:
        st.caption("How to read this: the wider a violin, the more invoices take that many days. The small box "
                   "inside holds the middle half of invoices, the line across it is the mean, and dots are unusually "
                   "slow or fast invoices. Hover for the median and quartiles.")
    else:
        st.caption("How to read this: each box holds the middle half of invoices. The solid line inside is the "
                   "median, the dashed line is the mean, and dots are unusually slow or fast invoices. Hover a box "
                   "for its median and quartiles.")
    medians = paid.groupby(by)["days_to_pay"].median()
    slow, fast = medians.idxmax(), medians.idxmin()
    text = (f"{slow} has the slowest median at {medians[slow]:.0f} days, {medians[slow] - medians[fast]:.0f} days "
            f"more than {fast} ({medians[fast]:.0f}).")
    if split:
        by_dispute = paid.groupby("dispute_raised")["days_to_pay"].median()
        text += (f" Across all groups, disputed invoices take a median of {by_dispute.get(1, float('nan')):.0f} "
                 f"days against {by_dispute.get(0, float('nan')):.0f} for the rest.")
    st.markdown(text)
    ui.download_csv(stats.assign(**{by: stats[by].astype(str)}), f"days_to_pay_spread_by_{by}.csv",
                    "Download the medians and quartiles")


days_spread()

st.subheader("Receivables aging")
buckets, _ = ds.aging(inv, snapshot)
left, right = st.columns(2)
with left:
    st.caption(f"Open receivables on {snapshot:%d %b %Y} by days past the due date.")
    ui.chart(charts.columns(buckets, "bucket", "amount_aed", "Open amount (AED)", colors=charts.RAMP,
                                   value_format=",.0f"), "descriptive_aging")
    ui.table(buckets, {"bucket": ui.col_text("Days past due", width=130),
                       "invoices": ui.col_number("Invoices", "Open invoices in this bucket.", "%d", 90),
                       "amount_aed": ui.col_money("Open amount (AED)", "Unpaid amount in this bucket.", 160)})
    ui.download_csv(buckets, "aging.csv", "Download the aging table")
with right:
    top = ds.top_overdue_clients(inv, snapshot)
    st.caption("The 10 clients with the most overdue money.")
    if top.empty:
        st.info("No client has overdue invoices on the snapshot date.")
    else:
        ui.chart(charts.ranked_bars(top, "client_id", "overdue_aed", "Overdue amount (AED)",
                                           value_format=",.0f"), "descriptive_top_overdue")
        ui.download_csv(top, "top_overdue_clients.csv", "Download the top overdue clients")


@st.cache_data(show_spinner=False)
def tree_frame(df, snap, measure):
    return viz.sunburst_frame(df, snap, measure, names)


@st.fragment
def receivables_tree() -> None:
    """Sunburst or icicle of ownership, sector and client. Its own controls rerun only this block."""
    st.subheader("Where the money sits")
    c1, c2, c3 = st.columns([1.2, 1, 1], vertical_alignment="bottom")
    measure = c1.selectbox("Size by", list(viz.SUNBURST_MEASURES), key="tree_measure")
    icicle = c2.toggle("Show as an icicle", key="tree_icicle")
    if c3.button("Reset the view", key="tree_reset"):
        st.session_state["tree_view"] = st.session_state.get("tree_view", 0) + 1
    frame = tree_frame(inv, snapshot, viz.SUNBURST_MEASURES[measure])
    if frame.empty:
        st.info(f"Nothing to show: no client has {measure.lower()} on the snapshot date.")
        return
    ui.chart(charts.receivables_tree(frame, measure, icicle),
             f"descriptive_tree_{st.session_state.get('tree_view', 0)}")
    layout = ("the columns run from all clients to ownership to sector. Click a block to open it down to single "
              "clients, and click the left column (or Reset the view) to go back." if icicle else
              "the inner ring is client ownership and the outer ring is sector. Click a segment to open it down "
              "to single clients, and click the centre (or Reset the view) to go back.")
    st.caption(f"How to read this: {layout} Size is the amount you picked. Colour is the share of open "
               "receivables that is overdue, from slate (none) to orange (all of it).")
    owners = frame[frame["level"] == 0].set_index("label")["value"]
    clients = frame[frame["level"] == 2].sort_values("value", ascending=False)
    lead = owners.idxmax()
    text = f"{lead} clients hold {owners[lead] / owners.sum():.0%} of {measure.lower().replace(' (aed)', '')}."
    if not clients.empty:
        big = clients.iloc[0]
        text += (f" The largest single client is {big['label']} ({big['client_name']}) with AED "
                 f"{big['value']:,.0f}.")
    st.markdown(text)
    ui.download_csv(frame.drop(columns=["value"]), f"receivables_tree_{viz.SUNBURST_MEASURES[measure]}.csv",
                    "Download the amounts behind this chart")


receivables_tree()

st.subheader("Cash gap")
summary, by_client = ds.cash_gap(inv)
st.caption("Days between paying staff through WPS and receiving the client's money. "
           "Every one of these days is funded from the company's own working capital.")
c = st.columns(3)
c[0].metric("Average cash gap", f"{summary['mean']:.0f} days")
c[1].metric("Median cash gap", f"{summary['median']:.0f} days")
c[2].metric("Invoices with a gap over 60 days", f"{summary['share_over_60']:.0%}")
paid = inv[inv["invoice_status"] == "Paid"]
ui.chart(charts.histogram(paid["cash_gap_days"], "Cash gap (days)", summary["median"], "Median", marginal_box=True),
         "descriptive_cash_gap")
st.caption("How to read this: the bars count invoices by cash gap. The box on top shows the same invoices: its middle "
           "half, the median as a solid line, the mean as a dashed line and unusual invoices as dots.")
ui.table(by_client, {"client_id": ui.col_text("Client", width=100),
                     "paid_invoices": ui.col_number("Paid invoices", "Paid invoices for this client.", "%d", 120),
                     "mean_cash_gap_days": ui.col_number("Cash gap (days)", "Average days between paying staff "
                                                         "through WPS and receiving this client's money.", "%.1f",
                                                         140),
                     "revenue_aed": ui.col_money("Invoiced (AED)", "Total invoiced to this client.", 150)},
         height=320)
ui.download_csv(by_client, "cash_gap_by_client.csv", "Download the cash gap by client")

ui.explainer(
    "**DSO** uses the standard formula: open receivables at a month end, divided by the credit sales of the "
    "last 90 days, times 90. It is weighted by money, so one large slow invoice moves it more than ten small "
    "ones. Average days to pay and the late rate count every invoice equally, which is why they are shown next "
    "to it.\n\n"
    "**Aging** shows how old the unpaid money is today. **The cash gap** is the number specific to a manpower "
    "business: salaries leave on the 1st of the month under WPS whatever the client does, so it measures how "
    "long the company finances its clients.\n\n"
    "**The DSO range tools** let you zoom into recent months without losing the full history. **The box and "
    "violin plot** shows the spread of days to pay, not just the average, so a group with a few very slow "
    "invoices stands out from one that is slow across the board. **The sunburst** shows where open, overdue or "
    "invoiced money sits by ownership, sector and client in one view, with colour flagging where open money has "
    "gone overdue. **The box over the cash gap histogram** summarises the same spread in one line. "
    "**The DSO candles** work out DSO for every day and show each month's first, last, highest and lowest day, so "
    "you can see how much of a month-end figure is just timing within the month."
)
