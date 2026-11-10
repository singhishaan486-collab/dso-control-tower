from datetime import datetime

import pandas as pd
import streamlit as st

import components as ui
from core import charts, triage

st.set_page_config(page_title="Dispute triage", layout="wide")
ui.page_header("Dispute triage",
               "Read a client's dispute email, find the invoice, classify the reasons, check the evidence and "
               "draft a reply. A person approves every reply. Nothing is sent.")

d = ui.get_data()
inv, lpos = d["inv"], d["lpos"]
clients = d["clients"].set_index("client_id")
emails = ui.get_emails()
bundle = ui.get_triage()
cfg = ui.config()["triage"]

st.subheader("Model comparison")
st.caption(f"Both classifiers train on the earliest {bundle['train_size']} emails and are tested on the latest "
           f"{len(bundle['test_ids'])}. Labels with fewer than {cfg['min_label_examples']} training examples "
           f"({', '.join(bundle['excluded'])}) are not learned and always go to a person.")
ui.table(bundle["comparison"], {
    "model": ui.col_text("Model", width=200),
    "macro_f1": ui.col_number("Average over reasons (macro F1)", "F1 worked out for each reason and then averaged, "
                                                                 "so rare reasons count as much as common ones.",
                              "%.3f", 230),
    "micro_f1": ui.col_number("Over all labels (micro F1)", "F1 over every label decision together.", "%.3f", 210),
    "dispute_vs_not_accuracy": ui.col_number("Dispute or not, correct", "Share of emails where the model was right "
                                                                       "about whether it is a dispute at all.",
                                             "%.3f", 200)})
best = bundle["comparison"].set_index("model").loc[bundle["best"]]
if best["macro_f1"] > 0.98:
    st.warning(f"{bundle['best']} scores {best['macro_f1']:.2f} on the test emails. That is too good to expect in "
               "practice: the synthetic emails are written from a fixed set of phrases, so later emails reuse the "
               "wording of earlier ones. Real client emails are messier, and the human decisions on each reply are "
               "how the classifier would be retrained.")
left, right = st.columns([1.4, 1])
with left:
    ui.chart(charts.grouped_bars(bundle["per_label"], "label", "model", "f1", "F1 on test emails"), "triage_f1")
with right:
    extraction = triage.extraction_accuracy(emails, inv)
    st.markdown("**Finding the invoice**")
    ui.table(extraction, {"confidence": ui.col_text("Confidence", width=110),
                          "emails": ui.col_number("Emails", "Test emails at this confidence.", "%d", 80),
                          "accuracy": ui.col_number("Right invoice found", "Share of these emails matched to the "
                                                                           "right invoice.", "%.3f", 160)})
    st.caption("High confidence means the email named the invoice. Low means it did not, so the client's most "
               "recent disputed or unpaid invoice was used and the email goes to a person.")
ui.table(bundle["per_label"], {
    "model": ui.col_text("Model", width=190), "label": ui.col_text("Reason", "Dispute reason code.", 160),
    "precision": ui.col_number("Flags that were right (precision)", "Share of emails given this reason that "
                                                                   "really had it.", "%.3f", 230),
    "recall": ui.col_number("Found (recall)", "Share of emails with this reason that were given it.", "%.3f", 130),
    "f1": ui.col_number("Balance (F1)", "One score that balances the two.", "%.3f", 110),
    "test_emails": ui.col_number("Test emails", "Test emails that really had this reason.", "%d", 100)},
         height=320)
ui.download_csv(bundle["per_label"], "triage_per_label_metrics.csv", "Download the per-label metrics")

st.subheader("Process one email")
only_test = st.toggle("Only show emails the classifier did not train on", value=True)
pool = emails[emails["email_id"].isin(bundle["test_ids"])] if only_test else emails
options = pool.sort_values("received_date", ascending=False)
labels = {row.email_id: f"{row.email_id} | {row.client_id} | {row.received_date:%d %b %Y} | {row.subject}"
          for row in options.itertuples()}
email_id = st.selectbox("Email", list(labels), format_func=labels.get)
email = emails.set_index("email_id").loc[email_id].copy()
email["email_id"] = email_id
result = triage.triage_email(email, bundle, inv, lpos, clients)

with st.container(border=True):
    st.markdown(f"**From** {clients.loc[email['client_id'], 'client_name']} ({email['client_id']}), "
                f"{email['received_date']:%d %B %Y}  \n**Subject:** {email['subject']}")
    st.text(email["body"])

st.markdown("**Step 1. Find the invoice**")
found = result["extraction"]
c = st.columns(3)
c[0].metric("Invoice", found["invoice_id"] or "None")
c[1].metric("Confidence", found["confidence"].capitalize())
c[2].metric("Matches the true invoice", "Yes" if found["invoice_id"] == email["invoice_id_true"] else "No",
            help="Checked against the ground truth kept for testing. A real inbox has no ground truth.")
st.caption(found["method"])

st.markdown("**Step 2. Classify the reasons**")
probabilities = pd.DataFrame(result["probabilities"].items(), columns=["label", "probability"])
fig = charts.ranked_bars(probabilities, "label", "probability", "Probability", percent=True)
fig.add_vline(x=cfg["confidence_threshold"], line=dict(color=charts.MUTED, width=1.5),
              annotation=dict(text="Threshold", xanchor="left"))
left, right = st.columns([1.4, 1])
ui.chart(fig, "triage_probabilities", where=left)
right.markdown(f"Predicted: **{', '.join(result['predicted'])}**  \nTrue labels: {email['labels']}")

if result["evidence"]:
    st.markdown("**Step 3. Check the evidence and Step 4. Give a verdict**")
    VERDICT_TEXT = {"supports_us": "Evidence supports us", "supports_client": "Evidence supports the client",
                    "unclear": "Unclear"}
    columns = st.columns(len(result["evidence"]))
    for column, (label, evidence) in zip(columns, result["evidence"].items()):
        with column.container(border=True):
            st.markdown(f"**{label}**")
            ui.table(pd.DataFrame(evidence.items(), columns=["Check", "Value"]).astype(str),
                     {"Check": ui.col_text("Check", width=260), "Value": ui.col_text("Value", width=300)})
            st.markdown(f"Verdict: **{VERDICT_TEXT[result['verdicts'][label]]}**  \n"
                        f"Action: {result['actions'][label]}")
    if "TS_MISMATCH" in result["evidence"]:
        st.caption("The attendance ledger is rebuilt from the invoice for this demo, so it always agrees with it.")

st.markdown("**Step 5. Route**")
if result["route_reasons"]:
    st.warning("A person must handle this email: " + "; ".join(result["route_reasons"]) + ".")
else:
    st.success("Confident on the invoice, the reasons and every verdict. Ready for a quick human check.")

if result["reply"]:
    st.markdown("**Step 6. Draft reply**")
    text = st.text_area("Reply", result["reply"], height=260, key=f"reply_{email_id}")
    decisions = st.session_state.setdefault("triage_decisions", [])
    record = dict(email_id=email_id, invoice_id=found["invoice_id"], labels=", ".join(result["predicted"]),
                  verdicts=", ".join(f"{k}: {v}" for k, v in result["verdicts"].items()),
                  action="; ".join(result["actions"].values()))
    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
    if b1.button("Approve", type="primary"):
        decisions.append(dict(record, decision="Approve", reply=result["reply"], time=datetime.now()))
        st.success("Approved. In a live system this would go to the client from the shared mailbox.")
    if b2.button("Save edits", disabled=text == result["reply"]):
        decisions.append(dict(record, decision="Edit", reply=text, time=datetime.now()))
        st.success("Edited reply saved.")
    if b3.button("Reject"):
        decisions.append(dict(record, decision="Reject", reply="", time=datetime.now()))
        st.info("Rejected. The email goes back to the account manager.")

st.subheader("Decisions this session")
log = pd.DataFrame(st.session_state.get("triage_decisions", []))
if log.empty:
    st.caption("No decisions yet. They are kept for this session only.")
else:
    ui.table(log, {"email_id": ui.col_text("Email", width=80), "invoice_id": ui.col_text("Invoice", width=85),
                   "labels": ui.col_text("Reasons", width=130), "verdicts": ui.col_text("Verdicts", width=160),
                   "action": ui.col_text("Action", width=160), "decision": ui.col_text("Decision", width=80),
                   "reply": ui.col_text("Reply", "Click a cell to read the whole reply.", 130),
                   "time": ui.col_datetime("Time", width=130)})
    ui.download_csv(log, "triage_decisions.csv", "Download the decisions")

ui.explainer(
    "**Regular expressions** find the invoice number in its different formats (INV-00412, inv 412, invoice no. "
    "00412), which is a precise job rules do better than a model.\n\n"
    "**Text classification** turns each email into TF-IDF features: word pairs catch phrases like 'not approved', "
    "and character fragments catch typos like 'attendence'. A one-vs-rest set of classifiers gives each reason "
    "its own yes or no, so one email can carry several reasons. Logistic regression and complement naive Bayes "
    "are compared on later emails, as they would meet new mail.\n\n"
    "**Written verdict rules** check the reason against the invoice's own records, so every reply is backed by "
    "evidence and the logic can be audited. Anything uncertain goes to a person, and a person approves every "
    "reply."
)
