"""Dispute triage without a language model: find the invoice, classify the reasons, pull the evidence,
judge it with written rules and draft a reply for a person to approve.
"""
import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.multiclass import OneVsRestClassifier
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

from core.automation import generate_month, verify
from core.config import load_config

PATTERNS = [re.compile(r"\bINV-(\d{5})\b", re.I), re.compile(r"\binvoice\s*no\.?\s*(\d{1,5})\b", re.I),
            re.compile(r"\binv\s*(\d{1,5})\b", re.I)]
GREETING = re.compile(r"^(dear|hi|hello|good morning)\b", re.I)
CLOSING = re.compile(r"^(regards|thanks|best regards|kind regards|rgds|thank you|--)", re.I)
NOT_DISPUTE = "NOT_DISPUTE"


# ------------------------------------------------------------------ text and invoice extraction

def clean_text(subject: str, body: str) -> str:
    """Subject plus body, lowercased, without the greeting line and everything from the sign-off down."""
    kept = []
    for line in str(body).splitlines():
        line = line.strip()
        if not line or GREETING.match(line):
            continue
        if CLOSING.match(line):
            break
        kept.append(line)
    return f"{subject} {' '.join(kept)}".lower()


def extract_invoice(email: pd.Series, inv: pd.DataFrame) -> dict:
    """Find the invoice reference in any of its formats; otherwise fall back to the client's latest open issue."""
    by_id = inv.set_index("invoice_id")
    text = f"{email['subject']} {email['body']}"
    for pattern in PATTERNS:
        for match in pattern.finditer(text):
            candidate = f"INV-{int(match.group(1)):05d}"
            if candidate in by_id.index and by_id.loc[candidate, "client_id"] == email["client_id"]:
                return dict(invoice_id=candidate, method=f"Found '{match.group(0)}' in the email", confidence="high")
    mine = inv[(inv["client_id"] == email["client_id"]) & (inv["invoice_date"] < email["received_date"])]
    open_issue = mine[(mine["dispute_raised"] == 1) | mine["payment_date"].isna()
                      | (mine["payment_date"] > email["received_date"])]
    pool = open_issue if len(open_issue) else mine
    if pool.empty:
        return dict(invoice_id=None, method="No invoice for this client before the email", confidence="low")
    latest = pool.sort_values("invoice_date").iloc[-1]["invoice_id"]
    return dict(invoice_id=latest, method="No reference found: used the client's most recent disputed or unpaid "
                                          "invoice", confidence="low")


def extraction_accuracy(emails: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, email in emails.iterrows():
        found = extract_invoice(email, inv)
        rows.append(dict(confidence=found["confidence"], correct=found["invoice_id"] == email["invoice_id_true"]))
    table = pd.DataFrame(rows)
    out = table.groupby("confidence")["correct"].agg(emails="size", accuracy="mean").reset_index()
    total = pd.DataFrame([dict(confidence="all", emails=len(table), accuracy=table["correct"].mean())])
    return pd.concat([out, total], ignore_index=True)


# ------------------------------------------------------------------ classifier

def split_emails(emails: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Earlier emails train, later emails test. Never shuffled across time."""
    ordered = emails.sort_values("received_date").reset_index(drop=True)
    cut = int(len(ordered) * (1 - load_config()["triage"]["test_share"]))
    return ordered.iloc[:cut], ordered.iloc[cut:]


def _features() -> FeatureUnion:
    return FeatureUnion([("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
                         ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2,
                                                   sublinear_tf=True))])


CANDIDATES = {
    "Logistic regression": lambda: OneVsRestClassifier(LogisticRegression(class_weight="balanced", max_iter=2000)),
    "Complement naive Bayes": lambda: OneVsRestClassifier(ComplementNB()),
}


def _texts(df: pd.DataFrame) -> list[str]:
    return [clean_text(s, b) for s, b in zip(df["subject"], df["body"])]


def _label_sets(df: pd.DataFrame, kept: list[str]) -> list[list[str]]:
    return [[label for label in str(labels).split("; ") if label in kept] for labels in df["labels"]]


def decide(proba: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Labels at or above the threshold; if none qualify, the single most likely label."""
    predicted = proba >= threshold
    empty = ~predicted.any(axis=1)
    predicted[empty, proba[empty].argmax(axis=1)] = True
    return predicted.astype(int)


def train_triage(emails: pd.DataFrame) -> dict:
    """Train both classifiers on earlier emails and compare them on later ones."""
    cfg = load_config()["triage"]
    train, test = split_emails(emails)
    counts = Counter(label for labels in train["labels"] for label in str(labels).split("; "))
    kept = sorted(label for label, n in counts.items() if n >= cfg["min_label_examples"])
    excluded = sorted(set(label for labels in emails["labels"] for label in str(labels).split("; ")) - set(kept))
    mlb = MultiLabelBinarizer(classes=kept)
    y_train, y_test = mlb.fit_transform(_label_sets(train, kept)), mlb.transform(_label_sets(test, kept))
    comparison, per_label, fitted = [], [], {}
    for name, make in CANDIDATES.items():
        model = Pipeline([("features", _features()), ("classify", make())]).fit(_texts(train), y_train)
        predicted = decide(model.predict_proba(_texts(test)))
        p, r, f, support = precision_recall_fscore_support(y_test, predicted, zero_division=0)
        per_label += [dict(model=name, label=label, precision=p[i], recall=r[i], f1=f[i], test_emails=support[i])
                      for i, label in enumerate(kept)]
        true_dispute = y_test[:, kept.index(NOT_DISPUTE)] == 0
        pred_dispute = predicted[:, kept.index(NOT_DISPUTE)] == 0
        comparison.append(dict(model=name, macro_f1=f1_score(y_test, predicted, average="macro", zero_division=0),
                               micro_f1=f1_score(y_test, predicted, average="micro", zero_division=0),
                               dispute_vs_not_accuracy=float((true_dispute == pred_dispute).mean())))
        fitted[name] = model
    majority = np.zeros_like(y_test)
    majority[:, y_train.sum(axis=0).argmax()] = 1
    comparison.append(dict(model="Baseline (always the most common label)",
                           macro_f1=f1_score(y_test, majority, average="macro", zero_division=0),
                           micro_f1=f1_score(y_test, majority, average="micro", zero_division=0),
                           dispute_vs_not_accuracy=np.nan))
    comparison = pd.DataFrame(comparison)
    best = comparison.loc[comparison["model"].isin(CANDIDATES), "macro_f1"].idxmax()
    best_name = comparison.loc[best, "model"]
    return dict(comparison=comparison, per_label=pd.DataFrame(per_label), best=best_name, model=fitted[best_name],
                labels=kept, excluded=excluded, train_size=len(train), test_ids=set(test["email_id"]))


# ------------------------------------------------------------------ evidence

def evidence_timesheet(r):
    signoff = r["signoff_date"]
    return {"Timesheet status": r["timesheet_status"], "Variance (hours)": float(r["timesheet_variance_hours"]),
            "Signed on": signoff.date().isoformat() if pd.notna(signoff) else "Not signed"}


def evidence_ot(r):
    return {"OT hours": float(r["ot_hours"]), "OT hours per head": float(r["ot_hours_per_head"]),
            "Pre-approved": "Yes" if r["ot_preapproved"] == 1 else "No"}


def evidence_headcount(r):
    return {"Contracted": int(r["heads_contracted"]), "Deployed": int(r["heads_deployed"]),
            "Gap (%)": float(r["headcount_gap_pct"]), "Relief share": float(r["relief_worker_share"])}


def evidence_lpo(r, lpos):
    match = lpos[lpos["lpo_number"] == r["lpo_number"]]
    return {"LPO": r["lpo_number"] if pd.notna(r["lpo_number"]) else "None", "Status": r["lpo_status"],
            "Balance before invoice (AED)": float(r["lpo_balance_before_aed"]) if pd.notna(
                r["lpo_balance_before_aed"]) else None,
            "Invoice amount (AED)": float(r["invoice_amount_aed"]),
            "Valid to": match["valid_to"].iat[0] if len(match) else "Unknown"}


def evidence_rate(r):
    return {"Billed at contract rate": "Yes" if r["rate_matches_contract"] == 1 else "No"}


def evidence_docs(r):
    return {"Signed timesheet and backup attached": "Yes" if r["docs_attached"] == 1 else "No"}


def evidence_sla(r):
    return {"SLA penalty clause": "Yes" if r["sla_penalty_clause"] == 1 else "No",
            "Headcount gap (%)": float(r["headcount_gap_pct"]), "Deduction already applied (AED)": float(
                r["sla_deduction_aed"])}


def evidence_ledger(r, clients):
    """Rebuild the sealed attendance ledger for that client and month and verify it."""
    keys = load_config()["ledger"]
    records, seals = generate_month(clients.loc[r["client_id"]], r, [], keys)
    ok, seq, reason = verify(records, seals, keys)
    return {"Ledger records": len(records), "Ledger OT hours": float(sum(x["ot_hours"] for x in records)),
            "Ledger verified": "Yes" if ok else f"No, at record {seq}"}


def gather_evidence(label: str, r: pd.Series, lpos: pd.DataFrame, clients: pd.DataFrame) -> dict:
    if label == "TS_MISMATCH":
        return {**evidence_timesheet(r), **evidence_ledger(r, clients)}
    return {"HC_DISCREPANCY": lambda: evidence_headcount(r), "OT_UNAPPROVED": lambda: evidence_ot(r),
            "LPO_ISSUE": lambda: evidence_lpo(r, lpos), "RATE_DISPUTE": lambda: evidence_rate(r),
            "DOCS_MISSING": lambda: evidence_docs(r), "SLA_PENALTY": lambda: evidence_sla(r)}[label]()


# ------------------------------------------------------------------ verdicts, actions and replies

def verdict(label: str, r: pd.Series) -> str:
    """supports_us, supports_client or unclear, from the written rules in the TRD."""
    v = load_config()["triage"]["verdict"]
    status, variance, gap = r["timesheet_status"], r["timesheet_variance_hours"], r["headcount_gap_pct"]
    if label == "TS_MISMATCH":
        if status == "Signed" and variance <= v["ts_variance_ok_hours"]:
            return "supports_us"
        return "supports_client" if status == "Unsigned" or variance > v["ts_variance_bad_hours"] else "unclear"
    if label == "HC_DISCREPANCY":
        return "supports_us" if gap <= v["hc_gap_ok_pct"] else "supports_client" if gap > v["hc_gap_bad_pct"] \
            else "unclear"
    if label == "OT_UNAPPROVED":
        return "supports_us" if r["ot_preapproved"] == 1 else "supports_client"
    if label == "LPO_ISSUE":
        valid = r["lpo_status"] == "Valid" and pd.notna(r["lpo_balance_before_aed"]) and \
            r["lpo_balance_before_aed"] >= r["invoice_amount_aed"]
        return "supports_us" if valid else "supports_client"
    if label == "RATE_DISPUTE":
        return "supports_us" if r["rate_matches_contract"] == 1 else "supports_client"
    if label == "DOCS_MISSING":
        return "supports_us" if r["docs_attached"] == 1 else "supports_client"
    if label == "SLA_PENALTY":
        return "supports_client" if r["sla_penalty_clause"] == 1 and gap > v["sla_gap_pct"] else "supports_us"
    return "unclear"


ACTIONS = {
    ("TS_MISMATCH", "supports_us"): "Send the signed timesheet and a ledger extract",
    ("TS_MISMATCH", "supports_client"): "Issue a credit note for the variance",
    ("TS_MISMATCH", "supports_client_unsigned"): "Get the timesheet signed and reissue the invoice",
    ("HC_DISCREPANCY", "supports_us"): "Send the deployment evidence",
    ("HC_DISCREPANCY", "supports_client"): "Issue a credit note for the shortfall",
    ("OT_UNAPPROVED", "supports_us"): "Send the OT approval reference",
    ("OT_UNAPPROVED", "supports_client"): "Reissue without the OT line and fix the approval process",
    ("LPO_ISSUE", "supports_us"): "Quote the valid LPO and its balance",
    ("LPO_ISSUE", "supports_client"): "Request LPO renewal and hold the invoice",
    ("RATE_DISPUTE", "supports_us"): "Share the rate clause from the contract",
    ("RATE_DISPUTE", "supports_client"): "Reissue at the contract rate",
    ("DOCS_MISSING", "supports_us"): "Resend the complete document pack",
    ("DOCS_MISSING", "supports_client"): "Resend the invoice with all documents",
    ("SLA_PENALTY", "supports_us"): "Contest the penalty with attendance records",
    ("SLA_PENALTY", "supports_client"): "Accept the penalty and issue a credit note",
}

TEMPLATES = {
    ("TS_MISMATCH", "supports_us"): "On the timesheet: your FM team signed it on {signed_on}, and the difference "
                                    "with your count is only {variance:.0f} hours. The signed timesheet and our "
                                    "sealed attendance record are attached.",
    ("TS_MISMATCH", "supports_client"): "On the timesheet: you are right that our count differs from yours by "
                                        "{variance:.0f} hours. We will issue a credit note for the difference.",
    ("TS_MISMATCH", "supports_client_unsigned"): "On the timesheet: you are right that the invoice went out before "
                                                 "your team signed the timesheet. We will send it for signature and "
                                                 "reissue the invoice once it is signed.",
    ("HC_DISCREPANCY", "supports_us"): "On headcount: we deployed {deployed} of {contracted} contracted staff, a gap "
                                       "of {gap:.1f}%. The deployment record is attached.",
    ("HC_DISCREPANCY", "supports_client"): "On headcount: we deployed {deployed} of {contracted} staff, a gap of "
                                           "{gap:.1f}%. We will credit the shortfall.",
    ("OT_UNAPPROVED", "supports_us"): "On overtime: the {ot:.0f} OT hours were approved in advance. The approval "
                                      "reference is attached.",
    ("OT_UNAPPROVED", "supports_client"): "On overtime: we cannot find your prior approval for the {ot:.0f} OT "
                                          "hours. We will reissue the invoice without that line.",
    ("LPO_ISSUE", "supports_us"): "On the LPO: {lpo} was valid for this period with enough balance to cover the "
                                  "invoice.",
    ("LPO_ISSUE", "supports_client"): "On the LPO: {lpo} is {lpo_status_lower}. Could your procurement team issue "
                                      "the renewal or top-up? We will hold the invoice until then.",
    ("RATE_DISPUTE", "supports_us"): "On the rate: the invoice uses the rate agreed in the contract. The pricing "
                                     "clause is attached.",
    ("RATE_DISPUTE", "supports_client"): "On the rate: you are right, the rate differs from the contract. We will "
                                         "reissue at the contract rate.",
    ("DOCS_MISSING", "supports_us"): "On documents: the signed timesheet and backup were attached. We are resending "
                                     "the full pack for convenience.",
    ("DOCS_MISSING", "supports_client"): "On documents: apologies, the backup was missing. The complete pack is "
                                         "attached.",
    ("SLA_PENALTY", "supports_us"): "On the SLA penalty: the headcount gap was {gap:.1f}%, within the contract "
                                    "tolerance, so we do not believe a penalty applies.",
    ("SLA_PENALTY", "supports_client"): "On the SLA penalty: the gap was {gap:.1f}%, so we accept the deduction "
                                        "and will issue a credit note.",
}
UNCLEAR = "On {label_text}: the records do not settle this clearly. An account manager will review it and reply " \
          "within two working days."
LABEL_TEXT = {"TS_MISMATCH": "the timesheet", "HC_DISCREPANCY": "headcount", "OT_UNAPPROVED": "overtime",
              "LPO_ISSUE": "the LPO", "RATE_DISPUTE": "the rate", "DOCS_MISSING": "documents",
              "SLA_PENALTY": "the SLA penalty"}


def response_key(label: str, verdict_value: str, r: pd.Series) -> tuple[str, str]:
    """An unsigned timesheet needs a different answer from a disagreement about hours."""
    if label == "TS_MISMATCH" and verdict_value == "supports_client" and r["timesheet_status"] == "Unsigned":
        return label, "supports_client_unsigned"
    return label, verdict_value


def draft_reply(r: pd.Series, client_name: str, verdicts: dict) -> str:
    facts = dict(variance=float(r["timesheet_variance_hours"]), deployed=int(r["heads_deployed"]),
                 contracted=int(r["heads_contracted"]), gap=float(r["headcount_gap_pct"]), ot=float(r["ot_hours"]),
                 lpo=r["lpo_number"] if pd.notna(r["lpo_number"]) else "the LPO",
                 lpo_status_lower=str(r["lpo_status"]).lower(),
                 signed_on=r["signoff_date"].date().isoformat() if pd.notna(r["signoff_date"]) else "the sign-off date")
    month = pd.Period(r["service_month"], freq="M").strftime("%B %Y")
    paragraphs = [TEMPLATES.get(response_key(label, v, r), UNCLEAR).format(label_text=LABEL_TEXT.get(label, label),
                                                                           **facts)
                  for label, v in verdicts.items()]
    return (f"Dear {client_name} team,\n\nThank you for your email about invoice {r['invoice_id']} for {month}.\n\n"
            + "\n\n".join(paragraphs) + "\n\nKind regards,\nAccounts Receivable")


def triage_email(email: pd.Series, bundle: dict, inv: pd.DataFrame, lpos: pd.DataFrame,
                 clients: pd.DataFrame) -> dict:
    """Run one email through every step and say whether a person must handle it."""
    threshold = load_config()["triage"]["confidence_threshold"]
    extraction = extract_invoice(email, inv)
    proba = bundle["model"].predict_proba([clean_text(email["subject"], email["body"])])[0]
    probabilities = dict(zip(bundle["labels"], proba))
    predicted = [bundle["labels"][i] for i in np.flatnonzero(decide(proba[None, :], threshold)[0])]
    reasons = []
    if max(proba) < threshold:
        reasons.append(f"Highest label confidence is {max(proba):.2f}, below {threshold}")
    if extraction["confidence"] == "low":
        reasons.append("The invoice was not named in the email")
    result = dict(extraction=extraction, probabilities=probabilities, predicted=predicted, evidence={},
                  verdicts={}, actions={}, reply="", route_reasons=reasons)
    if extraction["invoice_id"] is None:
        return result
    r = inv.set_index("invoice_id").loc[extraction["invoice_id"]].copy()
    r["invoice_id"] = extraction["invoice_id"]
    disputes = [label for label in predicted if label != NOT_DISPUTE]
    if not disputes:
        reasons.append("Not a dispute: pass to collections to answer the payment question")
        return result
    for label in disputes:
        result["evidence"][label] = gather_evidence(label, r, lpos, clients)
        result["verdicts"][label] = verdict(label, r)
        result["actions"][label] = ACTIONS.get(response_key(label, result["verdicts"][label], r),
                                               "Escalate to the account manager")
    if "unclear" in result["verdicts"].values():
        reasons.append("At least one verdict is unclear")
    result["reply"] = draft_reply(r, clients.loc[r["client_id"], "client_name"], result["verdicts"])
    return result
