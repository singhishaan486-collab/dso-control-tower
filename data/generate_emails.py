"""
Synthetic client emails for the dispute triage classifier.

Reads invoices.csv (output of generate_data.py) and writes dispute_emails.csv:
  - one email per disputed invoice, written from the true dispute reasons (multi-label)
  - plus non-dispute emails (payment status, remittance advice, general queries) labelled NOT_DISPUTE
Realism added on purpose: informal tone, typos, missing or oddly formatted invoice numbers,
two-issue emails, vague complaints, signatures and greetings.
"""
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(11)
inv = pd.read_csv(OUT / "invoices.csv", parse_dates=["invoice_date", "dispute_raised_date"]).drop_duplicates()

PHRASES = {
    "TS_MISMATCH": [
        "the hours on your invoice do not match our attendance records for {m}",
        "our site team count shows fewer man-hours than you billed for {m}",
        "timesheet attached with the invoice is different from what our FM supervisor signed",
        "we have not signed the timesheet you used for this invoice",
        "the attendance sheet has corrections that we never agreed to",
        "pls check, attendence for {m} is not matching our register",
    ],
    "HC_DISCREPANCY": [
        "you billed {h} staff but only {h2} were on site most days",
        "headcount on the invoice is higher than the deployed manpower",
        "several positions were vacant in {m} but are charged in full",
        "we were short of guards for many shifts, the invoice charges full strength",
        "the replacement staff were not provided yet invoice shows full deployment",
    ],
    "OT_UNAPPROVED": [
        "overtime of {ot} hours was never approved by us",
        "OT charges are not acceptable, no prior approval from facility manager",
        "who approved the extra hours? we did not request overtime in {m}",
        "please remove the overtime line, it was not pre approved as per contract",
        "the OT hours look excessive and there is no approval email",
    ],
    "LPO_ISSUE": [
        "the LPO quoted on the invoice has expired",
        "there is no valid PO for this period, invoice cannot be processed",
        "PO number missing on the invoice, our system rejects it",
        "the purchase order balance is exhausted, procurement needs to issue a new one first",
        "LPO renewal is pending with procurement so finance cannot release payment",
    ],
    "RATE_DISPUTE": [
        "the rate per head is higher than the contract rate",
        "you applied the escalation but we have not agreed to the revised rates",
        "unit price on the invoice does not match the rate card in the agreement",
        "the monthly rate charged is wrong, please refer to clause on pricing",
    ],
    "DOCS_MISSING": [
        "the signed timesheet is not attached",
        "supporting documents are missing, please resend with attendance report",
        "we only received the invoice copy, no backup documents",
        "original invoice with stamped timesheet not received at our office",
    ],
    "SLA_PENALTY": [
        "as per SLA we are deducting penalty for uncovered shifts",
        "penalty will be applied for the shortfall in {m} as per contract",
        "we will short pay due to SLA non compliance",
        "kindly issue a credit note for the SLA deductions",
    ],
    "SERVICE_QUALITY": [
        "we are not satisfied with the service quality this month",
        "there were multiple complaints from tenants about your staff",
        "the cleaning and security standard dropped, we need to discuss before paying",
    ],
}
NOT_DISPUTE = [
    "could you please confirm the outstanding balance on our account",
    "please find attached remittance advice for the payment released today",
    "payment for {inv} has been processed and should reflect in 3 working days",
    "kindly share your updated bank details letter on company letterhead",
    "can you send a statement of account up to {m}",
    "please update the invoice address to our new office, no other change",
    "we will release payment next week after the CFO approval",
    "requesting a copy of your trade licence for our vendor registration renewal",
]
OPEN = ["Dear team,", "Hi,", "Hello Accounts,", "Dear Sir/Madam,", "Hi Ahmed,", "Good morning,", "Dear Collections team,", ""]
CLOSE = ["Regards,\nFM Department", "Thanks,\nProcurement", "Best regards,\nAccounts Payable", "Rgds\nFacility Manager",
         "Kind regards,\nFinance", "Thank you", "-- Sent from my phone"]
ASK = ["Please revise and resend.", "Kindly clarify urgently.", "We are holding the payment until this is resolved.",
       "Please issue a credit note.", "Let us discuss.", "Awaiting your corrected invoice.", ""]
SUBJ = ["Invoice query", "RE: {inv}", "Dispute - {m} invoice", "Invoice on hold", "Clarification required", "{inv} rejected",
        "FW: monthly manpower invoice", "Payment hold"]


def typo(s):
    if rng.random() < 0.25 and len(s) > 20:
        i = rng.integers(5, len(s) - 5)
        s = s[:i] + s[i + 1] + s[i] + s[i + 2:]
    return s


def inv_ref(inv_id):
    num = inv_id.split("-")[1]
    r = rng.random()
    if r < 0.55:
        return inv_id
    if r < 0.75:
        return f"inv {int(num)}"
    if r < 0.85:
        return f"invoice no. {num}"
    return "your latest invoice"


rows = []
d = inv[inv["dispute_raised"] == 1]
for _, r in d.iterrows():
    labels = [x for x in str(r["dispute_reasons"]).split("; ") if x and x != "nan"]
    if not labels:
        continue
    m = pd.Period(r["service_month"], freq="M").strftime("%B")
    ref = inv_ref(r["invoice_id"])
    h = int(r["heads_deployed"]) + int(rng.integers(1, 4))
    sents = []
    for lab in labels:
        p = rng.choice(PHRASES[lab]).format(m=m, h=h, h2=int(r["heads_deployed"]), ot=int(r["ot_hours"]) if pd.notna(r["ot_hours"]) else 40)
        sents.append(typo(p))
    extra = " This is not the first time this has happened." if rng.random() < 0.15 else ""  # vague, label unchanged
    body = f"{rng.choice(OPEN)}\n\nRegarding {ref}, {'. Also, '.join(sents)}.{extra} {rng.choice(ASK)}\n\n{rng.choice(CLOSE)}".strip()
    rows.append(dict(email_id="", received_date=r["dispute_raised_date"], client_id=r["client_id"],
                     invoice_id_true=r["invoice_id"], subject=rng.choice(SUBJ).format(inv=r["invoice_id"], m=m),
                     body=body, labels="; ".join(labels), is_dispute=1))

paid = inv[inv["dispute_raised"] == 0].sample(int(len(rows) * 0.25), random_state=5)
for _, r in paid.iterrows():
    m = pd.Period(r["service_month"], freq="M").strftime("%B")
    txt = typo(rng.choice(NOT_DISPUTE).format(inv=inv_ref(r["invoice_id"]), m=m))
    rows.append(dict(email_id="", received_date=r["invoice_date"] + pd.Timedelta(days=int(rng.integers(10, 60))),
                     client_id=r["client_id"], invoice_id_true=r["invoice_id"],
                     subject=rng.choice(["Account statement", "Payment update", "Remittance advice", "Vendor details", "Query"]),
                     body=f"{rng.choice(OPEN)}\n\n{txt[0].upper() + txt[1:]}.\n\n{rng.choice(CLOSE)}".strip(),
                     labels="NOT_DISPUTE", is_dispute=0))

em = pd.DataFrame(rows).sort_values("received_date").reset_index(drop=True)
em["email_id"] = [f"EM-{i+1:04d}" for i in range(len(em))]
em.to_csv(OUT / "dispute_emails.csv", index=False)
print("emails", em.shape, "\n", em["labels"].str.split("; ").explode().value_counts().to_dict())
