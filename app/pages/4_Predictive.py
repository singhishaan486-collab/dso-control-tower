import pandas as pd
import streamlit as st

import components as ui
from core import charts, models

st.set_page_config(page_title="Predictive", layout="wide")
ui.page_header("Predictive: what will happen",
               "On the day an invoice is raised, predict whether it will be paid late or disputed, and how many "
               "days it will take.")

results = ui.get_models()
first = results["paid_late"]
st.caption(f"Every model trains on service months up to {ui.config()['split']['train_end_month']} "
           f"({first['rows']['train']} paid invoices) and is tested on {ui.config()['split']['test_start_month']} to "
           f"{ui.config()['split']['test_end_month']} ({first['rows']['test']} invoices). Nothing is shuffled across "
           "time, and only columns known on invoice day are used.")

FRAMING = {
    "paid_late": dict(
        positive="late", negative="on-time", labels=["on time", "late"],
        caught="Late invoices caught", noun="late invoices", adj="late",
        missed="**A missed late invoice (false negative)** is a cash shock nobody saw coming. Salaries still "
               "leave on the 1st under WPS, so the gap is funded from working capital.",
        alarm="**A false alarm (false positive)** means chasing a client who would have paid on time. It costs a "
              "collector's time and a little goodwill.",
        choice="Missing a late invoice costs more than a false alarm, so the threshold is tuned for recall (F2)."),
    "dispute_raised": dict(
        positive="disputed", negative="undisputed", labels=["no dispute", "dispute"],
        caught="Disputes caught", noun="disputed invoices", adj="disputed",
        missed="**A missed dispute (false negative)** is an invoice sent with a problem the client will reject. "
               "A dispute adds about 10 days before cash arrives.",
        alarm="**A false alarm (false positive)** means an extra check before sending an invoice that was fine. "
              "It costs a few minutes of billing time.",
        choice="A check before sending is cheap and a dispute is expensive, so the threshold is tuned for recall (F2)."),
}


def classification_tab(target: str) -> None:
    part, frame = results[target], FRAMING[target]
    metrics = part["metrics"]
    st.markdown(f"Best model on the validation months: **{part['best']}**, flagging at a probability of "
                f"{part['threshold']:.2f} or more.")
    ui.model_table(metrics, part["best"], key=target, caught=frame["caught"], noun=frame["noun"], adj=frame["adj"])
    base = part["baseline"]
    st.caption(f"Baseline: always predicting '{frame['labels'][base['majority_class']]}' scores accuracy "
               f"{base['accuracy']:.3f} and recall {base['recall']:.0f}. A useful model needs a better balance of "
               "recall and precision than that.")
    ui.download_csv(metrics, f"metrics_{target}.csv", "Download these metrics")

    left, right = st.columns([1.2, 1])
    with left:
        aucs = metrics.query("threshold_type == '0.5'").set_index("model")["roc_auc"].to_dict()
        ui.chart(charts.roc_lines(part["roc"], aucs, frame["positive"], frame["negative"]), f"predictive_roc_{target}")
    with right:
        name = st.selectbox("Model", list(part["probas"]), index=list(part["probas"]).index(part["best"]),
                            key=f"model_{target}")
        tuned = float(metrics.query("model == @name and threshold_type == 'Tuned'")["threshold"].iat[0])
        threshold = st.slider("Flag when the probability is at least", 0.05, 0.95, tuned, 0.01,
                              key=f"threshold_{target}")
        normalise = st.toggle("Show as shares of each actual class", key=f"normalise_{target}")
        matrix = models.confusion(part["y_test"], part["probas"][name], threshold)
        ui.chart(charts.confusion_heatmap(matrix, frame["labels"], normalise), f"predictive_confusion_{target}")
        scores = models.classification_metrics(part["y_test"], part["probas"][name], threshold)
        st.caption(f"Recall {scores['recall']:.0%}, precision {scores['precision']:.0%}, "
                   f"accuracy {scores['accuracy']:.0%}.")

    st.markdown(f"{frame['missed']}\n\n{frame['alarm']}\n\n{frame['choice']}")

    st.markdown(f"**What drives the {part['best'].lower()} prediction**")
    st.caption("Permutation importance on the test months: how much the ROC AUC drops when one column is shuffled.")
    ui.chart(charts.ranked_bars(part["importance"], "feature", "importance", "Drop in ROC AUC",
                                       value_format=".3f"), f"predictive_importance_{target}")


tabs = st.tabs(["Late payment", "Dispute", "Days to pay", "Client segments", "Leakage demo"])

with tabs[0]:
    classification_tab("paid_late")

with tabs[1]:
    classification_tab("dispute_raised")

with tabs[2]:
    reg = results["days_to_pay"]
    metrics = reg["metrics"]
    baseline = metrics.iloc[0]
    best = metrics.set_index("model").loc[reg["best"]]
    if reg["baseline_wins"]:
        st.warning(f"No model beats the simple baseline. The client's own past average misses by "
                   f"{baseline['mae']:.1f} days on the test months, against {best['mae']:.1f} for the best model "
                   f"({reg['best'].lower()}). How long a client takes to pay is mostly a fixed habit of that "
                   "client, so its history is already the best forecast. The classifiers above add value; this "
                   "regression does not.")
    ui.table(ui.chip_style(metrics, "model", [reg["baseline_wins"] and i == 0 for i in range(len(metrics))],
                           {"validation_mae": "{:.2f}", "mae": "{:.2f}", "rmse": "{:.2f}", "r2": "{:.3f}"}), {
        "model": ui.col_text("Model", width=250),
        "validation_mae": ui.col_number("Validation miss (days)", "MAE on the validation months: the "
                                        "average gap between predicted and actual days to pay.", "%.2f", 185),
        "mae": ui.col_number("Test miss (days)", "MAE on the unseen test months: the average gap between predicted "
                                 "and actual days to pay.", "%.2f", 150),
        "rmse": ui.col_number("RMSE, test (days)", "Like the average miss, but big misses count more.", "%.2f", 150),
        "r2": ui.col_number("Share explained (R²)", "Share of the variation in days to pay that the model "
                            "explains on the test months.", "%.3f", 170),
    })
    st.caption("MAE is the average miss in days. RMSE punishes big misses more. R² is the share of the variation "
               "explained. The model is chosen on the validation months, not the test months.")
    choice = st.selectbox("Show", list(reg["predictions"]), index=list(reg["predictions"]).index(reg["best"]))
    left, right = st.columns(2)
    ui.chart(charts.predicted_vs_actual(reg["y_test"], reg["predictions"][choice], choice), "predictive_pred_vs_actual", where=left)
    residuals = pd.Series(reg["y_test"] - reg["predictions"][choice])
    ui.chart(charts.histogram(residuals, "Actual minus predicted days", 0, "No error"), "predictive_residuals", where=right)
    predictions = pd.DataFrame({"invoice_id": reg["test_ids"], "actual_days": reg["y_test"],
                                **{name: values.round(1) for name, values in reg["predictions"].items()}})
    ui.download_csv(predictions, "days_to_pay_predictions.csv", "Download the test predictions")

with tabs[3]:
    seg = results["segments"]
    st.markdown(f"K-means chose **{seg['best_k']} segments**, the number with the best silhouette score.")
    left, right = st.columns(2)
    ui.chart(charts.simple_line(seg["search"], "k", "inertia", "Number of segments (k)",
                                         "Inertia (lower is tighter)", seg["best_k"]), "predictive_inertia", where=left)
    ui.chart(charts.simple_line(seg["search"], "k", "silhouette", "Number of segments (k)",
                                          "Silhouette (higher is clearer)", seg["best_k"]), "predictive_silhouette", where=right)
    st.caption(f"The best silhouette is {seg['search']['silhouette'].max():.2f}, so the segments overlap at the "
               "edges. Treat them as tendencies, not hard boxes.")
    ui.chart(charts.segment_map(seg["clients"], seg["pca_variance"]), "predictive_segment_map")
    st.markdown("**Each client across six measures**")
    st.html(ui.legend_html({name: charts.segment_line_color(name) for name in sorted(seg["clients"]["segment"].unique())},
                           seg["clients"]["segment"].value_counts().to_dict(), "clients"))
    ui.chart(charts.segment_parcoords(seg["clients"]), "predictive_segment_parcoords")
    st.caption("How to read this: each line is one client and each upright axis is one measure, low at the bottom "
               "and high at the top. Lines of one colour that run together show what a segment has in common. Drag "
               "along an axis to keep only the clients in that range, and click the axis outside the range to clear "
               "it.")
    by_segment = seg["clients"].groupby("segment")[["mean_days_to_pay", "dispute_rate", "payment_terms_days"]].mean()
    slow, fast = by_segment["mean_days_to_pay"].idxmax(), by_segment["mean_days_to_pay"].idxmin()
    disputes = by_segment["dispute_rate"].idxmax()
    st.markdown(f"{slow} clients take {by_segment.loc[slow, 'mean_days_to_pay']:.0f} days to pay on average against "
                f"{by_segment.loc[fast, 'mean_days_to_pay']:.0f} for {fast.lower()}, and their terms average "
                f"{by_segment.loc[slow, 'payment_terms_days']:.0f} days against "
                f"{by_segment.loc[fast, 'payment_terms_days']:.0f}. {disputes} clients have the highest dispute "
                f"rate at {by_segment.loc[disputes, 'dispute_rate']:.0%}.")
    names = models.CLUSTER_FEATURES
    ui.table(seg["profile"], {
        "segment": ui.col_text("Segment", width=110),
        "clients": ui.col_number("Clients", "Number of clients in the segment.", "%d", 62),
        "mean_days_to_pay": ui.col_number("Days to pay", names["mean_days_to_pay"] + ".", "%.1f", 95),
        "mean_days_overdue": ui.col_number("Overdue", names["mean_days_overdue"] + ".", "%.1f", 80),
        "late_rate": ui.col_share("Paid late", names["late_rate"] + ".", 85),
        "dispute_rate": ui.col_share("Disputed", names["dispute_rate"] + ".", 85),
        "mean_resolution_days": ui.col_number("Resolution", names["mean_resolution_days"] + ".", "%.1f", 90),
        "payment_terms_days": ui.col_number("Terms", "Average agreed payment terms in days.", "%.1f", 65),
        "revenue_share": ui.col_share("Of revenue", names["revenue_share"] + ".", 85),
        "unapproved_ot_rate": ui.col_share("Unapproved OT", names["unapproved_ot_rate"] + ".", 105),
        "unsigned_rate": ui.col_share("Unsigned", names["unsigned_rate"] + ".", 85),
    })
    ui.download_csv(seg["clients"].drop(columns=["pc1", "pc2"]), "client_segments.csv",
                    "Download every client with its segment")
    chosen = st.selectbox("Clients in segment", sorted(seg["clients"]["segment"].unique()))
    members = seg["clients"][seg["clients"]["segment"] == chosen]
    ui.table(members[["client_id", "client_ownership", "sector", "invoices", "mean_days_to_pay", "dispute_rate",
                      "late_rate"]], {
        "client_id": ui.col_text("Client", width=100),
        "client_ownership": ui.col_text("Ownership", width=150),
        "sector": ui.col_text("Sector", width=130),
        "invoices": ui.col_number("Invoices", "Invoices raised for this client.", "%d", 90),
        "mean_days_to_pay": ui.col_number("Days to pay", "Average days from invoice to payment.", "%.1f", 110),
        "dispute_rate": ui.col_share("Disputed", "Share of this client's invoices that were disputed.", 150),
        "late_rate": ui.col_share("Paid late", "Share of this client's invoices paid after the due date.", 150),
    })
    st.info("Segments use each client's full payment history. That is fine for describing clients, but it "
            "includes outcomes the models are trying to predict, so segment labels are never fed into the "
            "predictive models.")

with tabs[4]:
    leak = results["leakage"]
    m = leak["metrics"].set_index("model")
    clean, leaky = m.iloc[0], m.iloc[1]
    st.error(f"Adding four columns that only exist after the invoice is sent lifts ROC AUC from "
             f"{clean['roc_auc']:.3f} to {leaky['roc_auc']:.3f} and accuracy from {clean['accuracy']:.1%} to "
             f"{leaky['accuracy']:.1%}. The improvement is fake: on invoice day none of these columns exist.")
    ui.table(leak["metrics"], {
        "model": ui.col_text("Model", width=240),
        "accuracy": ui.col_number("Overall correct", "Accuracy: share of all test invoices the model got right.",
                                  "%.3f", 130),
        "precision": ui.col_number("Flags right", "Precision: share of flagged invoices that were truly "
                                   "late.", "%.3f", 120),
        "recall": ui.col_number("Late caught", "Recall: share of late invoices the model flagged.",
                                "%.3f", 120),
        "f1": ui.col_number("Balance (F1)", "One score that balances recall and precision.", "%.3f", 115),
        "roc_auc": ui.col_number("AUC, test months", "How well the model ranks invoices from safe to risky on the "
                                 "test months. 0.5 is a coin toss and 1 is perfect.", "%.3f", 140),
    })
    st.markdown("The leaked columns: **was_chased** (collections followed up, which only happens once an "
                "invoice is already late), **dispute_raised**, **stage_ack_days** and **short_paid_aed**.")
    ui.chart(charts.ranked_bars(leak["importance"], "feature", "importance", "Drop in ROC AUC",
                                       value_format=".3f"), "predictive_leak_importance")
    st.caption("was_chased dominates because it is close to a copy of the answer: you only chase invoices that "
               "are late.")
    ui.download_csv(leak["metrics"], "leakage_demo.csv", "Download the comparison")

ui.explainer(
    "**Classification** answers yes or no questions on invoice day: will this invoice be late, will it be "
    "disputed. Four models are compared because each sees the data differently. KNN copies the outcome of "
    "similar past invoices, a decision tree learns readable rules, and a random forest and gradient boosting "
    "combine many trees for accuracy.\n\n"
    "**The time split** trains on older months and tests on newer ones, which is how the model would be used. "
    "The last three training months choose the best model and the threshold, so the test months stay unseen.\n\n"
    "**Regression** predicts a number, the days to pay. It is judged against a naive baseline, because a model "
    "is only worth running if it beats the simple answer.\n\n"
    "**K-means clustering** groups clients with similar payment behaviour so each group can get its own policy. "
    "The number of groups is chosen with the silhouette score, which measures how cleanly they separate. "
    "**The parallel axes chart** shows every client on six measures at once, so you can see which measures "
    "actually separate the segments, something the two-pattern map above compresses away.\n\n"
    "**The leakage demo** shows why the known_at rule matters: a model that sees the future looks better on "
    "paper and is useless in practice."
)
