import pandas as pd
import streamlit as st

import components as ui
from core import charts, diagnostic as dg, prescriptive as pr, viz

st.set_page_config(page_title="Prescriptive", layout="wide")
ui.page_header("Prescriptive: what to do",
               "A policy for each client segment, and an estimate of what each process change would do to disputes, "
               "DSO and cash.")
st.warning("Every number on this page is a model estimate on synthetic data. It shows what the trained models "
           "predict if their learned relationships hold, not a proven effect.")

inv = ui.get_data()["inv"]
results = ui.get_models()

st.subheader("Policy by client segment")
policies = pr.policy_table(results["segments"]["clients"])
st.caption("Segments come from the clustering on the Predictive page.")
ui.table(policies, {
    "segment": ui.col_text("Segment", width=110),
    "clients": ui.col_number("Clients", "Clients in this segment.", "%d", 60),
    "revenue_share": ui.col_share("Of revenue", "Share of all revenue from this segment.", 90),
    "mean_days_to_pay": ui.col_number("Days to pay", "Average days from invoice to payment.", "%.0f", 85),
    "dispute_rate": ui.col_share("Disputed", "Average share of invoices disputed.", 90),
    "late_rate": ui.col_share("Paid late", "Average share of invoices paid late.", 90),
    "policy": ui.col_text("Policy", "What to do for this segment. Click a cell to read all of it.", 236),
    "owner": ui.col_text("Owner", width=110),
    "metric_to_watch": ui.col_text("Watch", "The number that shows whether the policy works.", 90)})
ui.download_csv(policies, "segment_policies.csv", "Download the policy table")

st.subheader("What-if simulator")
st.caption("Each slider is the share of invoices where the change is adopted. The models then rescore the "
           "latest 12 settled months of invoices.")
with st.expander("What each lever changes"):
    ui.table(pd.DataFrame(pr.LEVER_CHANGES.items(), columns=["Lever", "Change to the invoice"]),
             {"Lever": ui.col_text("Lever", width=220),
              "Change to the invoice": ui.col_text("Change to the invoice", width=690)})
adoption = {}
columns = st.columns(len(pr.LEVERS))
for column, lever in zip(columns, pr.LEVERS):
    adoption[lever] = column.slider(lever, 0, 100, 50, 5, format="%d%%", key=f"adopt_{lever}") / 100
signoff_days = st.slider("Faster sign-off: days earlier", 1, 10, 3)

sim = pr.simulate(inv, results["dispute_raised"]["model"], results["days_to_pay"]["model"], adoption, signoff_days)
before, after = sim["before"], sim["after"]
c = st.columns(3) + st.columns(2)
c[0].metric("Dispute score (model)", f"{after['mean_p_dispute']:.3f}",
            f"{after['mean_p_dispute'] - before['mean_p_dispute']:+.3f}", delta_color="inverse",
            help="Average predicted probability of a dispute. The forest scores run higher than the real rate.")
c[1].metric("Disputes per month", f"{after['disputes_per_month']:.1f}",
            f"{after['disputes_per_month'] - before['disputes_per_month']:+.1f}", delta_color="inverse",
            help="Scaled to the real dispute rate of these months.")
c[2].metric("Predicted days to pay", f"{after['weighted_days_to_pay']:.1f}",
            f"{after['weighted_days_to_pay'] - before['weighted_days_to_pay']:+.2f}", delta_color="inverse",
            help="Weighted by invoice amount.")
c[3].metric("DSO change", f"{round(sim['dso_change'], 2) + 0:+.2f} days",
            help="The change in amount-weighted predicted days to pay, used as the change in DSO.")
c[4].metric("Cash released", f"AED {round(sim['cash_released']) + 0:,.0f}",
            help=f"DSO reduction × average daily credit sales of AED {sim['cash_per_day']:,.0f}.")

ui.chart(charts.cash_waterfall(sim["steps"]), "prescriptive_cash_waterfall")
st.caption("Levers are applied one after another in the order shown, so each bar is what that lever adds on top "
           "of the ones before it. An orange bar means the model expects that lever to slow payment.")
ui.table(sim["steps"], {
    "lever": ui.col_text("Lever", width=172),
    "adoption": ui.col_share("Adopted on", "Share of invoices where the change is adopted.", 120),
    "invoices_changed": ui.col_number("Invoices changed", "Invoices this lever changed.", "%d", 120),
    "p_dispute_change": ui.col_number("Dispute score change", "Change in the average predicted dispute "
                                                              "probability.", "%+.4f", 150),
    "disputes_per_month_change": ui.col_number("Disputes a month", "Change in expected disputes per month.",
                                               "%+.2f", 120),
    "dso_change_days": ui.col_number("DSO change (days)", "Change in amount-weighted predicted days to pay.",
                                     "%+.3f", 130),
    "cash_released_aed": ui.col_money("Cash released (AED)", "DSO reduction times average daily credit sales.",
                                      140)})
ui.download_csv(sim["steps"], "what_if_results.csv", "Download the simulator results")


@st.cache_data(show_spinner=False, persist="disk")
def pair_grid(df, lever_a: str, lever_b: str, days: int, _dispute_model, _days_model):
    return viz.lever_grid_fast(df, _dispute_model, _days_model, lever_a, lever_b, days)


@st.fragment
def two_levers() -> None:
    """DSO change over a 5 by 5 grid of adoption shares for two levers. Reruns on its own."""
    st.subheader("Two levers together")
    st.caption("Model estimate on synthetic data. Every cell reruns the what-if simulator above with only these two "
               "levers adopted, at 0, 25, 50, 75 or 100% of invoices.")
    c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    lever_a = c1.selectbox("Lever A", pr.LEVERS, index=pr.LEVERS.index("OT pre-approval enforced"), key="pair_a")
    others = [lever for lever in pr.LEVERS if lever != lever_a]
    lever_b = c2.selectbox("Lever B", others, index=others.index("Invoice QA") if "Invoice QA" in others else 0,
                           key="pair_b")
    view = c3.segmented_control("View", ["Flat map", "3D surface"], default="Flat map", required=True,
                                key="pair_view")
    pair = (lever_a, lever_b, signoff_days)
    done = st.session_state.setdefault("pair_done", [])
    if pair not in done:
        ask = st.empty()
        with ask.container():
            st.info("Working out a pair reruns the simulator 25 times. The first time takes about 20 to 60 seconds "
                    "depending on the computer; after that the pair is stored and opens at once.")
            clicked = st.button("Work out this pair", key="pair_go")
        if not clicked:
            return
        ask.empty()
        done.append(pair)
    with st.spinner("Rescoring the invoices for all 25 combinations..."):
        grid = pair_grid(inv, lever_a, lever_b, signoff_days, results["dispute_raised"]["model"],
                         results["days_to_pay"]["model"])
    ui.chart(charts.lever_surface(grid, lever_a, lever_b, view == "3D surface"), "prescriptive_lever_surface")
    st.caption("How to read this: each labelled point is one mix of the two levers, with lever A going up and "
               "lever B going across. The number is the change in DSO in days. Cyan means DSO falls, orange means "
               "the model expects it to rise, and the lines join mixes with the same change. The 3D view shows the "
               "same numbers as height.")
    best = grid.loc[grid["dso_change_days"].idxmin()]
    full = grid[(grid["adoption_a"] == 1.0) & (grid["adoption_b"] == 1.0)].iloc[0]
    rising = int((grid["dso_change_days"] > 0.005).sum())
    text = (f"The largest fall in this grid is {best['dso_change_days']:+.2f} days, with {viz.lower(lever_a)} on "
            f"{best['adoption_a']:.0%} and {viz.lower(lever_b)} on {best['adoption_b']:.0%} of invoices (about AED "
            f"{best['cash_released_aed']:,.0f} released). Both at 100% gives {full['dso_change_days']:+.2f} days.")
    text += (f" In {rising} of {len(grid)} mixes the model expects DSO to rise; those cells are orange."
             if rising else " No mix in this grid makes the model expect DSO to rise.")
    st.markdown(text)
    ui.download_csv(grid, f"two_levers_{lever_a}_{lever_b}.csv".replace(" ", "_").lower(),
                    "Download the grid")


two_levers()

stages = dg.stage_waterfall(inv)
totals = stages.groupby("group")["mean_days"].sum()
cost = totals["Disputed"] - totals["Not disputed"]
ceiling = pr.dispute_ceiling_days(inv, cost)
st.info(
    f"**Why the DSO effect is small.** A dispute adds about {cost:.1f} days, and about "
    f"{inv.loc[inv['invoice_status'] == 'Paid', 'dispute_raised'].mean():.0%} of invoices are disputed. So even "
    f"removing every dispute could only take about {ceiling:.1f} days off DSO. Most of DSO comes from how long "
    "each client takes to pay by habit, which is why the segment policies above, such as pricing the wait for slow "
    "clients and submitting through their portal, matter more for cash than the invoice fixes. The invoice fixes "
    "earn their place by cutting disputes and the work they create."
)

st.subheader("Caveats")
st.markdown(
    "- These are associations learned from synthetic data, not proven causes.\n"
    "- When a lever moves a prediction the wrong way, the simulator shows it rather than hiding it. Automated "
    "attendance switches invoices to the app, and the Diagnostic page shows app clients dispute more because of "
    "who they are, not because of the app. The model has learned that confusion.\n"
    "- The days-to-pay model leans on each client's payment history, so it reacts little to invoice fixes.\n"
    "- The latest 12 settled months include some months the models trained on, so the starting point fits better "
    "than new data would. The changes between before and after are what matter here."
)

ui.explainer(
    "**Prescriptive analytics** turns predictions into decisions. The segment table gives each kind of client "
    "its own policy, because one policy for every client is the problem the business started with.\n\n"
    "**The what-if simulator** reuses the trained models instead of guessing. It changes the invoice features "
    "a process change would change, then asks the models what they would now predict. The difference is the "
    "estimated effect. Cash released converts days of DSO into money: each day of DSO ties up one day of "
    "average credit sales.\n\n"
    "**The two-lever map** runs the same simulator for every mix of two levers on a 5 by 5 grid, so you can see "
    "whether they add up, overlap or work against each other. The flat map is easier to read exactly; the 3D "
    "surface shows the shape of the effect."
)
