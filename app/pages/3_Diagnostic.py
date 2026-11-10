import pandas as pd
import streamlit as st

import components as ui
from core import charts, diagnostic as dg, viz

st.set_page_config(page_title="Diagnostic", layout="wide")
ui.page_header("Diagnostic: why it is happening",
               "Which stage of the order-to-cash process loses the days, and which conditions lead to disputes "
               "and late payment.")

inv = ui.get_data()["inv"]


@st.cache_data(show_spinner="Mining association rules...")
def rules(df: pd.DataFrame) -> pd.DataFrame:
    return dg.outcome_rules(df)


st.subheader("Where the days go")
stages = dg.stage_waterfall(inv)
totals = stages.groupby("group")["mean_days"].sum()
cost = totals["Disputed"] - totals["Not disputed"]
st.caption(f"Paid invoices, from the end of the service month to cash. A dispute adds {cost:.1f} days on "
           f"average ({totals['Disputed']:.1f} against {totals['Not disputed']:.1f}). Most of it is the "
           "resolution itself.")
y_max = totals.max() * 1.15
left, right = st.columns(2)
for column, group in zip((left, right), ("Not disputed", "Disputed")):
    part = stages[stages["group"] == group]
    column.markdown(f"**{group}** ({int(part['invoices'].iloc[0]):,} invoices)")
    ui.chart(charts.waterfall(part, "Month end to cash", y_max), f"diagnostic_waterfall_{group}", where=column)
ui.download_csv(stages, "stage_waterfall.csv", "Download the stage durations")

st.subheader("Why clients dispute")
pareto = dg.dispute_pareto(inv)
top3 = pareto.head(3)
st.caption(f"{', '.join(top3['reason'])} cause {top3['share'].sum():.0%} of all dispute reasons. An invoice "
           "can carry more than one reason.")
ui.chart(charts.ranked_bars(pareto, "reason", "disputes", "Disputes", value_format=",.0f"), "diagnostic_pareto")
ui.table(pareto, {
    "reason": ui.col_text("Reason", "Dispute reason code.", 170),
    "disputes": ui.col_number("Disputes", "Disputed invoices that carry this reason.", "%d", 90),
    "mean_resolution_days": ui.col_number("Resolution (days)", "Average days to resolve the dispute.", "%.1f", 140),
    "mean_days_to_pay": ui.col_number("Days to pay", "Average days from invoice to payment.", "%.1f", 110),
    "share": ui.col_share("Share", "Share of all dispute reasons.", 120),
    "cumulative_share": ui.col_share("Running total", "Share of all reasons covered by this reason and the ones "
                                                      "above it.", 130),
    "extra_days_vs_undisputed": ui.col_number("Extra days", "Average days to pay with this reason, minus the "
                                                            "average for invoices never disputed.", "%+.1f", 110)})
st.caption("Extra days compares the average days to pay of invoices with this reason against invoices "
           "that were never disputed.")
ui.download_csv(pareto, "dispute_pareto.csv", "Download the dispute reasons")

st.subheader("Conditions that lead to disputes and late payment")
cfg = ui.config()["association"]
all_rules = rules(inv)
st.caption(f"Association rules on {(inv['invoice_status'] == 'Paid').sum():,} paid invoices. Kept when "
           f"support is at least {cfg['min_support']:.0%}, confidence at least {cfg['min_confidence']:.0%} and lift "
           f"at least {cfg['min_lift']}. A longer rule is dropped when a shorter one with the same outcome already "
           "has the same or higher lift.")
OUTCOME_VIEWS = {"All": None, "Dispute": "DISPUTE", "Paid late": "LATE", "Over 30 days late": "LATE_30+"}
SORTS = {"Lift": "lift", "Confidence": "confidence", "Support": "support"}


@st.fragment
def rules_block(all_rules: pd.DataFrame) -> None:
    """Controls, the plain-English rule list and the rule scatter. Reruns on its own when a control moves."""
    frame = viz.rules_frame(all_rules).assign(rule_id=range(len(all_rules)))
    c1, c2, c3 = st.columns([1.5, 0.8, 1.2], vertical_alignment="bottom")
    view = c1.segmented_control("Outcome", list(OUTCOME_VIEWS), default="All", required=True, key="rules_outcome")
    sort = c2.selectbox("Sort by", list(SORTS), key="rules_sort")
    min_lift = c3.slider("Minimum lift", 1.0, float(max(all_rules["lift"].max(), 1.2)), float(cfg["min_lift"]), 0.1,
                         key="rules_min_lift")
    st.html(ui.RULES_LEGEND)
    outcome = OUTCOME_VIEWS.get(view or "All")
    shown = frame[(frame["lift"] >= min_lift) & ((frame["then"] == outcome) if outcome else True)]
    shown = shown.sort_values([SORTS[sort], "lift"], ascending=False)

    left, right = st.columns([1.35, 1], gap="medium")
    with right:
        event = ui.chart(charts.rules_scatter(shown, float(frame["support"].max()) * 1.3,
                                              max(0.0, float(frame["confidence"].min()) - 0.08)),
                         "diagnostic_rules_scatter", config=charts.SELECT_CONFIG, on_select="rerun",
                         selection_mode=("points", "box", "lasso"))
        st.caption("How to read this: each bubble is one rule. Further right means more invoices match it, higher "
                   "means the outcome follows more often, and a bigger bubble means a higher lift. Drag a box or "
                   "click bubbles to highlight their rules. Double-click the chart to clear.")
        if not shown.empty:
            strongest = shown.loc[shown["lift"].idxmax()]
            common = shown.loc[shown["support"].idxmax()]
            st.markdown(f"The strongest rule shown, **{strongest['plain_if']}**, makes "
                        f"{viz.OUTCOMES[strongest['then']]['short']} {strongest['lift']:.1f}x more likely than normal. "
                        f"The most common, **{common['plain_if']}**, matches {common['support']:.1%} of paid "
                        f"invoices ({int(common['invoices']):,}).")
    points = event.selection.points if event and event.selection else []
    selected = {int(p["customdata"][3]) for p in points if p.get("customdata")} & set(shown["rule_id"])
    ordered = pd.concat([shown[shown["rule_id"].isin(selected)], shown[~shown["rule_id"].isin(selected)]])
    with left:
        limit = max(st.session_state.get("rules_limit", 10), len(selected))
        if selected:
            st.caption(f"{len(selected)} rules selected on the chart are listed first and marked in cyan.")
        ui.rules_view(ordered.head(limit), selected)
        st.caption(f"Showing {min(limit, len(ordered))} of {len(ordered)} rules.")
        if len(ordered) > limit:
            st.button("Show more", key="rules_more",
                      on_click=lambda: st.session_state.update(rules_limit=limit + 10))
    insight = viz.ownership_insight(frame)
    if insight:
        st.markdown(insight)
    ui.download_csv(all_rules.loc[shown["rule_id"]], "association_rules.csv", "Download these rules")


rules_block(all_rules)
with st.expander("What the items mean"):
    meanings = pd.DataFrame([(item, viz.item_info(item)[0], text) for item, text in dg.ITEM_MEANINGS.items()],
                            columns=["item", "shown_as", "meaning"])
    ui.table(meanings, {"item": ui.col_text("Code", width=150), "shown_as": ui.col_text("Shown as", width=220),
                        "meaning": ui.col_text("Meaning", width=520)})
st.markdown("**Which dispute reasons appear together**")
pairs = dg.reason_pairs(inv)
st.caption("Lift below 1 means the two reasons appear together less often than chance would predict, so most "
           "disputes have one main cause.")
ui.pairs_view(pairs)
ui.download_csv(pairs, "dispute_reason_pairs.csv", "Download the reason pairs")

st.subheader("Attendance method, or attendance accuracy?")
by_method = dg.dispute_rate_by(inv, "attendance_method")
by_status = dg.dispute_rate_by(inv, "timesheet_status")
by_band = dg.dispute_rate_by(dg.with_variance_band(inv), "variance_band")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("**By attendance method**")
    ui.chart(charts.columns(by_method, "attendance_method", "dispute_rate", "Dispute rate", percent=True), "diagnostic_by_method")
with c2:
    st.markdown("**By timesheet status**")
    ui.chart(charts.columns(by_status, "timesheet_status", "dispute_rate", "Dispute rate", percent=True), "diagnostic_by_status")
with c3:
    st.markdown("**By timesheet variance**")
    ui.chart(charts.columns(by_band, "variance_band", "dispute_rate", "Dispute rate", colors=charts.RAMP[1:5],
                                   percent=True), "diagnostic_by_band")

method = by_method.set_index("attendance_method")
paid = inv[inv["invoice_status"] == "Paid"]
variance = paid.groupby("attendance_method")["timesheet_variance_hours"].mean()
st.info(
    f"**Be careful with the first chart.** App sites have a higher dispute rate than Biometric sites "
    f"({method.loc['App', 'dispute_rate']:.0%} against {method.loc['Biometric', 'dispute_rate']:.0%}), yet App "
    f"has the most accurate attendance: an average variance of {variance['App']:.1f} hours against "
    f"{variance['Biometric']:.1f} for Biometric and {variance['Paper']:.1f} for Paper. The gap stays inside the "
    f"same variance band, so it is not about attendance accuracy. Only {method.loc['App', 'clients']} clients use "
    "App, and their own habits drive that number. This is confounding: the method is tied to who the client is.\n\n"
    f"The mechanism that does hold up is the variance itself. The dispute rate rises from "
    f"{by_band['dispute_rate'].iloc[0]:.0%} when our hours and the client's agree to "
    f"{by_band['dispute_rate'].iloc[-1]:.0%} when they differ by more than 40 hours."
)
with st.expander("Dispute rate by method within each variance band"):
    ui.table(dg.variance_by_method(inv), {
        "attendance_method": ui.col_text("Attendance method", width=160),
        "variance_band": ui.col_text("Hours mismatch", "Gap between our hours and the client's hours.", 150),
        "paid_invoices": ui.col_number("Paid invoices", "Paid invoices in this group.", "%d", 120),
        "dispute_rate": ui.col_share("Disputed", "Share of these invoices the client disputed.", 160)})
ui.download_csv(by_band, "dispute_rate_by_variance.csv", "Download the variance comparison")

ui.explainer(
    "**The stage waterfall** splits the time from month end to cash into steps, so the slow step is visible. "
    "Comparing disputed and undisputed invoices gives the cost of a dispute in days.\n\n"
    "**The Pareto** ranks dispute reasons, because a few reasons usually cause most disputes and that is where "
    "a fix pays off first.\n\n"
    "**Association rule mining** (apriori) finds combinations of conditions that appear together with an "
    "outcome. Support is how common the rule is, confidence is how often the outcome follows, and lift is how "
    "much more likely the outcome is than on average. Only conditions known before the invoice is sent are "
    "allowed on the left side, so every rule points at something that could be fixed in time.\n\n"
    "**The rule list** translates each rule into plain words, with the normal rate (confidence divided by lift) "
    "next to it so the size of the jump is clear. **The rule scatter** shows all rules at once: common rules sit "
    "to the right, reliable ones near the top, and strong ones are large. Selecting bubbles highlights the "
    "matching rules in the list.\n\n"
    "**The attendance comparison** is a reminder that a raw difference between groups is not a cause. Checking "
    "the same comparison inside bands of the real mechanism separates the two."
)
