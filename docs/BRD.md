# Business Requirements Document

**Project:** DSO Control Tower for a UAE manpower and facility services company
**Author:** Ishaan
**Course:** Data Analytics (DIVA), MGB June 2026, SP Jain School of Global Management, Dubai
**Version:** 1.0, 9 November 2026
**Status:** Prototype on synthetic data

---

## 1. Summary

A manpower company pays its workers before its clients pay it. Salaries go out through the Wage Protection System (WPS) at the start of every month whatever the client does, while client payments arrive weeks or months later and are often held up by disputes over attendance, overtime, headcount and purchase orders. The owner funds that gap from working capital.

This project builds a working prototype platform that:

1. measures DSO and shows where it is high (descriptive),
2. finds the stage of the order-to-cash process where days are lost and why (diagnostic),
3. predicts, on the day an invoice is raised, whether it will be disputed or paid late and how many days it will take (predictive),
4. recommends what to do for each client segment and estimates the cash it would release (prescriptive),
5. runs automated checks at each workflow node, including a trained dispute triage classifier that reads client emails and prepares a response for a human to approve.

No large language model is used. Everything runs offline on a laptop.

## 2. Business background

### 2.1 How the business works

| Stage | What happens | Cash effect |
|---|---|---|
| 1. Contract and LPO | Rates, headcount, payment terms, SLA and LPO agreed with a commercial client | None yet |
| 2. Recruit and mobilise | Visas, medicals, accommodation, transport | Outflow before any billing |
| 3. Deploy and track attendance | Staff work shifts. Attendance captured on paper, biometric or app. OT happens | Running cost |
| 4. Payroll via WPS | Salaries paid through WPS on the 1st of the following month | Largest outflow, fixed date |
| 5. Timesheet sign-off | Client FM team verifies and signs the monthly timesheet | Delay here delays the invoice |
| 6. Invoice | Tax invoice with 5% VAT, matched to LPO and signed timesheet | DSO clock starts |
| 7. Client approval and disputes | FM, procurement and finance review. Disputes raised and resolved | Waiting |
| 8. Payment and collections | Client pays in full, short pays or goes overdue | Cash finally in |

### 2.2 Why it matters

| Evidence | Source | Reliability |
|---|---|---|
| 58% of UAE B2B credit sales were overdue, mainly due to administrative inefficiencies in customer payment processes | Atradius Payment Practices Barometer UAE, 2025 | Credit insurer survey |
| Around two in five UAE B2B invoices are paid late | Atradius UAE press release, 11 Aug 2026 | Credit insurer survey |
| Average collection times in FM and manpower outsourcing are "crossing 150 days"; salaries are 70 to 80% of cost | Tariq Chauhan, EFS Group CEO, Gulf News, Oct 2022 | Industry opinion piece |
| Wages due on the 1st of the following month from 1 June 2026 | Ministerial Resolution 340 of 2026, as reported by Gulf News and advisory firms | Secondary sources; MOHRE text not checked |

No public UAE manpower invoice dataset exists, so this project uses synthetic data calibrated to these ranges.

### 2.3 Problem statement

The company treats every client the same way: same terms, same follow-up. It learns an invoice is late only after it is late. Disputes are found when the client raises them, not before the invoice is sent, and each one is handled by hand from scratch. Collections effort goes to the biggest or loudest client rather than the invoices most at risk. The result is a long, unpredictable cash gap between payroll and collection.

## 3. Objectives and success measures

| # | Objective | Measure | Target for the prototype |
|---|---|---|---|
| O1 | Know where DSO stands | DSO by month, client, segment, sector; AR aging | Shown on dashboard, matches hand calculation |
| O2 | Find where days are lost | Average days per stage, disputed vs not; top dispute reasons; association rules | Stage with largest controllable delay identified |
| O3 | Predict trouble at invoice stage | Dispute and late-payment models on a time-based test set | Recall for "late" of at least 0.70 with precision reported; no leaked features |
| O4 | Forecast cash | Days-to-pay regression | MAE reported in days and beaten against a naive baseline (client's past average) |
| O5 | Act on it | Segment policies and a what-if simulator | Estimated DSO reduction and cash released for at least three interventions |
| O6 | Resolve disputes faster | Triage classifier accuracy and time to prepare a response | Macro F1 reported per reason code; human approval kept for every reply |
| O7 | Prevent avoidable disputes | Pre-send invoice checks on the current batch | Every draft invoice gets a pass, warn or block result with reasons |

## 4. Scope

**In scope**
- Synthetic data generation, cleaning and transformation with a visible cleaning log
- Streamlit platform with descriptive, diagnostic, predictive and prescriptive pages
- Classification, regression, clustering and association rule mining
- Automation hub: attendance ledger, LPO guard, invoice QA, WPS compliance check, dispute triage, collections queue
- Upload of a user's own invoice file in the same format
- Docker packaging and Streamlit Community Cloud deployment

**Out of scope for this version**
- Large language models and API keys
- A real blockchain network (replaced by a hash-chained, tamper-evident ledger)
- Live ERP, banking or WPS integration
- Sending emails or messages to real clients
- User accounts and access control
- Real company data (the pipeline is built so real data can replace the synthetic files later)

## 5. Users

| User | Needs | Main pages |
|---|---|---|
| Owner or MD | Cash tied up, which clients drive it, what to change | Overview, Descriptive, Prescriptive |
| Finance and AR | DSO, aging, cash forecast | Descriptive, Predictive |
| Collections team | Who to chase today and with what message | Collections queue |
| Operations and site supervisors | Attendance and OT problems before they turn into disputes | Attendance ledger, Diagnostic |
| Account managers | LPO renewals, client risk, dispute replies | LPO guard, Dispute triage |
| HR and payroll | WPS compliance before the payroll file goes out | WPS check |

## 6. Business requirements

Priority: **M** must have, **S** should have, **C** could have.

### 6.1 Data

| ID | Requirement | Priority |
|---|---|---|
| BR-D1 | The platform loads invoice, client, LPO, payroll and email data from CSV files | M |
| BR-D2 | It shows the raw data quality problems and every cleaning step applied, with row counts and the reason for each | M |
| BR-D3 | A user can upload their own invoices file in the same format and the whole platform recalculates | S |
| BR-D4 | Every column is tagged with when it becomes known (contract, invoice, later). Models may only use contract and invoice columns | M |

### 6.2 Descriptive: what is happening

| ID | Requirement | Priority |
|---|---|---|
| BR-DS1 | Headline KPIs: DSO (90-day), average days to pay, % paid late, dispute rate, open AR, overdue AR | M |
| BR-DS2 | DSO and late rate by month, sector, ownership, service line and client | M |
| BR-DS3 | AR aging buckets on the snapshot date (current, 1 to 30, 31 to 60, 61 to 90, 91 to 120, 120+) | M |
| BR-DS4 | Cash gap: days between the WPS pay date and the client payment, averaged and by client | S |

### 6.3 Diagnostic: why it is happening

| ID | Requirement | Priority |
|---|---|---|
| BR-DG1 | Stage delay waterfall: average days at each stage from month end to cash, split by disputed and not disputed | M |
| BR-DG2 | Dispute reason Pareto and average resolution days per reason | M |
| BR-DG3 | Association rules linking pre-invoice conditions (unsigned timesheet, unapproved OT, LPO problem, paper attendance, headcount gap) to dispute and late outcomes, with support, confidence and lift | M |
| BR-DG4 | Comparison of dispute rate by attendance method and timesheet status | S |

### 6.4 Predictive: what will happen

| ID | Requirement | Priority |
|---|---|---|
| BR-P1 | Predict `paid_late` at invoice stage with KNN, decision tree, random forest and gradient boosting, compared on accuracy, precision, recall, F1, ROC AUC and confusion matrix | M |
| BR-P2 | Predict `dispute_raised` at invoice stage with the same four models | M |
| BR-P3 | Predict `days_to_pay` with linear regression, random forest and gradient boosting, reporting MAE, RMSE and R², compared to a naive baseline | M |
| BR-P4 | Segment clients with k-means, choose k with elbow and silhouette, and describe each segment in business terms | M |
| BR-P5 | Show feature importance for the best models | M |
| BR-P6 | A leakage demonstration: rerun the late model with post-invoice columns included and show the inflated, misleading accuracy | S |
| BR-P7 | Train on earlier months and test on later months only. No random shuffling across time | M |

### 6.5 Prescriptive: what to do

| ID | Requirement | Priority |
|---|---|---|
| BR-PR1 | A policy table per client segment (for example advance billing, shorter terms, sign-off before invoicing, deposit, price the wait into the rate) | M |
| BR-PR2 | A what-if simulator with switches for automated attendance, OT pre-approval enforcement, LPO guard, invoice QA and portal submission, showing predicted change in dispute rate, days to pay, DSO and cash released | M |
| BR-PR3 | Every prescriptive number states its assumption and that it is a model estimate on synthetic data | M |

### 6.6 Automation hub

| ID | Requirement | Priority |
|---|---|---|
| BR-A1 | **Attendance ledger:** daily attendance records chained with hashes so any later edit is detectable; both parties' confirmations recorded; a tamper demonstration | M |
| BR-A2 | **LPO guard:** flags LPOs that are expired, not yet renewed, below 20% balance, or insufficient for the next invoice | M |
| BR-A3 | **Invoice QA:** three-way match of every draft invoice against the signed timesheet, LPO and contract rate, plus document checks; result Pass, Warn or Block with reasons | M |
| BR-A4 | **WPS compliance check:** flags late pay dates, OT paid below the legal multiplier, OT hours above the limit, days paid above days in month, missing IBAN, and the monthly on-time share | M |
| BR-A5 | **Dispute triage (trained classifier, no LLM):** see section 7 | M |
| BR-A6 | **Collections queue:** ranks open and draft invoices by predicted risk times amount and suggests the action and reminder template for each | S |
| BR-A7 | **Router:** when a check fails or a model flags risk, the case is assigned to the right automation and owner, shown as a single action list | S |
| BR-A8 | Every automated output is a recommendation. Money movements and client communication need human approval | M |

## 7. Dispute triage requirements

**Goal:** cut the time from receiving a dispute email to sending an evidence-backed response, and stop disputes being handled from scratch each time.

**Flow:** email arrives → find which invoice it refers to → classify the reason(s) → pull the evidence → judge whether the evidence supports the client or us → recommend an action → fill a reply template → human approves, edits or rejects → log the decision.

| ID | Requirement | Priority |
|---|---|---|
| BR-T1 | Extract the invoice reference from the subject or body in its various formats ("INV-00412", "inv 412", "invoice no. 00412"). If none is found, match on client and most recent disputed invoice and mark it low confidence | M |
| BR-T2 | Classify the email as NOT_DISPUTE or one or more of: TS_MISMATCH, HC_DISCREPANCY, OT_UNAPPROVED, LPO_ISSUE, RATE_DISPUTE, DOCS_MISSING, SLA_PENALTY. Multi-label. SERVICE_QUALITY and anything below the confidence threshold go to a human | M |
| BR-T3 | Compare at least two text classifiers trained on earlier emails and tested on later emails; report per-label precision, recall, F1 and confusion matrices | M |
| BR-T4 | For each predicted reason, pull the relevant evidence from the data: timesheet status and variance, OT approval flag, headcount gap, LPO status and balance, rate match, documents attached, SLA deduction | M |
| BR-T5 | Give a verdict per reason: "Evidence supports client", "Evidence supports us" or "Unclear", using written rules | M |
| BR-T6 | Recommend an action (credit note, reissue with corrected documents, request LPO renewal, send signed timesheet, escalate to account manager) and fill a reply template with invoice-specific facts | M |
| BR-T7 | A human reviews every reply. Decisions are logged so the classifier can be retrained later | M |
| BR-T8 | Report the estimated time saved per dispute and its effect on resolution days in the prescriptive simulator | S |

## 8. Assumptions and constraints

- All data is synthetic. Patterns found by the models were partly built into the generator. The value is the pipeline, not the findings.
- The professor evaluates by running the project on his own laptop. It must install and run offline with one command and no API keys.
- Synthetic payment terms, rates and timelines are informed by the secondary research but are assumptions, not company figures.
- WPS rules are taken from secondary reporting and must be checked against MOHRE before any real use.

## 9. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Data leakage | Model looks accurate and is useless | Known-at tags, feature allowlist, time-based split, automated leakage test |
| Overclaiming causality | Prescriptive numbers taken as facts | Labels on every estimate; simulator described as "if the model's relationships hold" |
| Synthetic data bias | Findings mirror the generator | State it plainly; design for real data swap |
| Censored recent invoices | Recent paid invoices look faster than reality | Train only on service months with enough time to settle; report open invoices separately |
| Rare classes in triage | SERVICE_QUALITY and RATE_DISPUTE poorly learned | Confidence threshold and human routing |
| Scope creep | Deadline missed | Build in the phase order in BUILD_PLAN.md; automation hub after analytics |

## 10. Mapping to the course brief

| Brief requirement | Where it is met |
|---|---|
| Business objective | Sections 2 and 3 |
| Data set, cleaning, transformation | Data page and cleaning log (BR-D2) |
| Descriptive analytics | Section 6.2 |
| Diagnostic analytics | Section 6.3 |
| Predictive analytics | Section 6.4 |
| Prescriptive analytics | Section 6.5 |
| Classification | BR-P1, BR-P2, BR-T3 |
| Clustering | BR-P4 |
| Regression | BR-P3 |
| Association rule mining | BR-DG3 |
| Accuracy and confusion matrix | BR-P1, BR-P2, BR-T3 |
| Rationale for every technique | In the app (an explainer box on every page) and in the report |
| Deliverable: zip with report, data and code | Repository plus the report the student writes himself |

## 11. Acceptance criteria

The prototype is accepted when:

1. `docker compose up` and `streamlit run app/Home.py` both start the app on a clean machine with no internet and no keys.
2. Every page in section 6 loads without errors on the bundled data and on an uploaded copy of `invoices.csv`.
3. All automated tests pass, including the leakage test.
4. Every model shows its metrics on a later-months test set.
5. The current batch of draft invoices gets a Pass, Warn or Block result, a risk score and a router action.
6. The triage page processes any email in `dispute_emails.csv` end to end and shows extracted invoice, predicted labels with confidence, evidence, verdict and a draft reply.

## 12. Sources

- Atradius, Payment Practices Barometer UAE 2025; Atradius UAE press release, 11 August 2026 (via media-outreach.com)
- Coface UAE, receivables management article, June 2025 (coface.ae)
- Chauhan, T., "UAE's facilities management businesses have a payment issue to resolve", Gulf News, October 2022
- Zeng, S. et al. (2008), "Using predictive analysis to improve invoice-to-cash collection", KDD
- Appel, A. P. et al. (2020), "Optimize cash collection: use machine learning to predicting invoice payment", arXiv 2008.07363
- Schoonbee, L., Moore, W. R. and van Vuuren, J. H. (2022), "A machine-learning approach towards solving the invoice payment prediction problem", South African Journal of Industrial Engineering 33(4)
- UAE Federal Tax Authority, VAT Executive Regulation, Articles 59 and 60
- Federal Decree-Law No. 33 of 2021 (UAE Labour Law), Articles 17 and 19
- Emirates Islamic, Salary WPS File Creation User Guide
