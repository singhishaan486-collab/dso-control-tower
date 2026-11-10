# Technical Requirements Document

**Project:** DSO Control Tower (prototype)
**Version:** 1.0, 9 November 2026
**Read with:** `BRD.md` (what and why), `DATA_DICTIONARY.md` (columns), `BUILD_PLAN.md` (order of work), `../CLAUDE.md` (rules)

---

## 1. Architecture

```
data/*.csv ──► core/data.py ──► core/features.py ──► core/models_*.py ──► app/ (Streamlit pages)
 (synthetic)    load + clean       feature sets,         train, evaluate,      descriptive, diagnostic,
                + cleaning log     leakage allowlist     score, explain        predictive, prescriptive,
                                                                                automation hub, triage
                                   core/automation/*.py  rule engines, ledger,
                                                         triage, router
```

Five layers, matching the BRD:

1. **Data:** CSV files, loader, cleaner (exists: `core/data.py`)
2. **Analytics:** descriptive and diagnostic functions returning dataframes and Plotly figures
3. **Models:** classification, regression, clustering, association rules, triage classifier
4. **Prescriptive:** segment policies and a what-if simulator that reuses the trained models
5. **Automation:** rule engines and the triage pipeline, all returning recommendations for a human

Everything is pure Python, runs offline and needs no secrets.

## 2. Stack

| Component | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | Docker base `python:3.11-slim` |
| Data | pandas ≥ 2.2, numpy | |
| ML | scikit-learn ≥ 1.4 | All models, pipelines, metrics |
| Association rules | mlxtend ≥ 0.23 | `apriori`, `association_rules` |
| UI | Streamlit ≥ 1.36 | Multipage app in `app/` |
| Charts | Plotly ≥ 5 | Interactive charts |
| Persistence | joblib | Saved models in `models/` |
| Config | PyYAML | `config/config.yaml` |
| Tests | pytest, `streamlit.testing.v1.AppTest` | |
| Packaging | Docker, docker compose | Also deployable on Streamlit Community Cloud |

No LLM SDKs. No network calls at runtime.

## 3. Repository layout

```
dso-control-tower/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── config/config.yaml
├── data/
│   ├── generate_data.py          # exists
│   ├── generate_emails.py        # exists
│   ├── invoices.csv  current_batch.csv  clients.csv  lpos.csv  payroll.csv  dispute_emails.csv
│   └── runtime/                  # gitignored: decision logs, uploads
├── core/
│   ├── data.py                   # exists: load, clean, cleaning log, dso()
│   ├── features.py               # feature lists, LEAKY list, preprocessors, splits
│   ├── descriptive.py
│   ├── diagnostic.py             # stage waterfall, Pareto, association rules
│   ├── models_classify.py        # paid_late and dispute_raised
│   ├── models_regress.py         # days_to_pay
│   ├── models_cluster.py         # client segments
│   ├── prescriptive.py           # policies, what-if simulator
│   ├── train.py                  # `python -m core.train` trains and saves everything
│   └── automation/
│       ├── ledger.py             # hash-chained attendance ledger
│       ├── lpo_guard.py
│       ├── invoice_qa.py
│       ├── wps_check.py
│       ├── triage.py             # extractor, classifier, evidence, verdict, templates
│       ├── collections.py
│       └── router.py
├── app/
│   ├── Home.py
│   ├── components.py             # shared KPI cards, explainer boxes, download buttons
│   └── pages/
│       ├── 1_Data_and_Cleaning.py
│       ├── 2_Descriptive.py
│       ├── 3_Diagnostic.py
│       ├── 4_Predictive.py
│       ├── 5_Prescriptive.py
│       ├── 6_Automation_Hub.py
│       ├── 7_Dispute_Triage.py
│       └── 8_Collections.py
├── models/                       # gitignored joblib files
├── tests/
└── docs/  BRD.md  TRD.md  DATA_DICTIONARY.md  BUILD_PLAN.md
```

## 4. Configuration (`config/config.yaml`)

All thresholds live here, never hard-coded in pages.

```yaml
snapshot_date: "2026-11-09"
random_state: 42
split:
  train_end_month: "2025-09"     # train: service months up to and including this
  test_start_month: "2025-10"
  test_end_month: "2026-03"      # later months excluded from modelling: not enough time to settle (censoring)
dso_window_days: 90
classification:
  models: [knn, decision_tree, random_forest, gradient_boosting]
  threshold_metric: f2           # recall-weighted threshold chosen on the last 3 training months
regression:
  models: [linear, random_forest, gradient_boosting]
clustering:
  k_range: [2, 8]
  n_init: 20
association:
  min_support: 0.03
  min_confidence: 0.5
  min_lift: 1.2
invoice_qa:
  ot_hours_per_head_warn: 6
  headcount_gap_warn_pct: 5
  timesheet_variance_warn_hours: 20
lpo_guard:
  low_balance_pct: 20
  expiry_warn_months: 1
wps:
  ot_multiplier_min: 1.25
  ot_hours_month_max: 60         # derived from the 2 hours/day cap; verify before real use
  establishment_on_time_min: 0.85  # reported in secondary sources for Resolution 340/2026; verify
triage:
  min_label_examples: 10         # labels with fewer training examples go to a human
  confidence_threshold: 0.5
  test_share: 0.25
collections:
  overdue_weight_days: 30
prescriptive:
  dispute_resolution_passthrough: 0.8
ledger:
  supplier_key: "demo-supplier-key"   # demo only
  client_key: "demo-client-key"       # demo only
```

## 5. Data layer

`core/data.py` already exists and is tested:
- `load_all(invoice_path=None)` returns `raw`, `inv` (clean), `log` (cleaning steps), `current`, `clients`, `lpos`, `payroll`.
- `clean()` removes duplicates, fixes sector labels, fills attendance method from the same client, fills numeric blanks with the client median, fixes x10 amount errors, and adds derived columns (`ot_hours_per_head`, stage durations, `cash_gap_days`, history-missing flags, `log_amount`).
- `dso(df, period_end, days)` = open AR at `period_end` ÷ credit sales in the last `days` × `days`.

Add: `load_emails()` reading `dispute_emails.csv` with dates parsed.

Uploads: a user file must contain every `Contract` and `Invoice` column in the data dictionary plus `payment_date`, `dispute_raised` and `dispute_reasons`. Validate the columns and show a clear error listing the missing ones.

## 6. Feature sets and leakage control (`core/features.py`)

```python
CATEGORICAL = ["sector", "client_ownership", "emirate", "service_line", "billing_basis",
               "attendance_method", "submission_channel", "timesheet_status", "lpo_status"]
NUMERIC = ["payment_terms_days", "approval_layers", "heads_contracted", "sla_penalty_clause",
           "prev_invoices_paid", "prev_avg_days_to_pay", "prev_late_rate", "prev_dispute_rate",
           "last_paid_invoice_late", "open_invoices_count", "open_amount_aed", "is_new_client",
           "prev_avg_days_to_pay_missing", "prev_late_rate_missing",
           "heads_deployed", "headcount_gap_pct", "relief_worker_share", "absence_rate",
           "ot_hours", "ot_hours_per_head", "ot_preapproved", "timesheet_variance_hours",
           "days_monthend_to_invoice", "lpo_valid", "rate_matches_contract", "docs_attached",
           "sla_deduction_aed", "log_amount", "invoice_month"]   # invoice_month = invoice_date.month
LEAKY = ["client_ack_date", "dispute_raised", "dispute_reasons", "dispute_raised_date",
         "dispute_resolved_date", "disputed_amount_aed", "dispute_resolution", "first_followup_date",
         "short_paid_aed", "payment_date", "invoice_status", "days_to_pay", "paid_late",
         "stage_ack_days", "stage_dispute_resolution_days", "days_overdue", "cash_gap_days"]
```

Rules:
1. `set(CATEGORICAL + NUMERIC) & set(LEAKY)` must be empty. A test enforces it.
2. `days_to_signoff` is not a feature (blank when unsigned). Use `days_monthend_to_invoice` and `timesheet_status`.
3. Cluster labels are **never** used as model features, because clusters are built from full-history outcomes.
4. Preprocessing is one `ColumnTransformer` inside each sklearn `Pipeline`: `SimpleImputer(median)` + `StandardScaler` for numeric, `SimpleImputer(most_frequent)` + `OneHotEncoder(handle_unknown="ignore")` for categorical. Fitted on training rows only.

**Modelling frame:** `invoice_status == "Paid"` and service month between the first month and `test_end_month`.
**Split:** train = service month ≤ `train_end_month`; test = `test_start_month` to `test_end_month`. Never `train_test_split` with shuffle. Hyperparameter search uses `TimeSeriesSplit(n_splits=3)` on the training rows sorted by `invoice_date`.

Expose:
- `get_xy(df, target)`
- `time_split(df)`
- `build_preprocessor()`
- `FEATURES`
- `LEAKY`

## 7. Descriptive (`core/descriptive.py`)

| Function | Output |
|---|---|
| `kpis(inv, snapshot)` | DSO (90d at last month end), mean days to pay, % late, dispute rate, open AR, overdue AR |
| `dso_trend(inv)` | Monthly DSO series using `data.dso` at each month end |
| `breakdown(inv, by)` | Late rate, mean days to pay, dispute rate, revenue by any profile column |
| `aging(inv, snapshot)` | Open AR in buckets current, 1 to 30, 31 to 60, 61 to 90, 91 to 120, 120+ days past due |
| `cash_gap(inv)` | Mean and distribution of `cash_gap_days`, by client |

Charts: KPI cards, DSO line chart, bar charts by segment, aging stacked bar, top 10 clients by overdue AR.

## 8. Diagnostic (`core/diagnostic.py`)

**Stage waterfall:** mean days for month end → sign-off/invoice (`stage_invoice_days`), invoice → acknowledgement (`stage_ack_days`), acknowledgement → dispute raised, dispute raised → resolved, last event → payment. Show two waterfalls side by side: disputed and not disputed. The difference is the cost of a dispute in days.

**Dispute Pareto:** count and share by reason code (explode `dispute_reasons`), with mean resolution days and mean extra days to pay compared with undisputed invoices.

**Association rules** (`mlxtend`):
- One transaction per paid invoice.
- Items:
  - `TS=Signed`, `TS=Remarks` or `TS=Unsigned`
  - `OT_UNAPPROVED` when `ot_preapproved == 0` and `ot_hours_per_head > 4`
  - `LPO=<status>`
  - `ATT=<method>`
  - `HC_GAP>5`
  - `VAR>20h`
  - `DOCS_MISSING`
  - `RATE_MISMATCH`
  - `OWN=<ownership>`
  - outcome items `DISPUTE`, `LATE` and `LATE_30+` (more than 30 days overdue)
- Run `apriori` with the config thresholds.
- Keep rules where the consequent contains only outcome items and the antecedent contains none.
- Show support, confidence and lift, sorted by lift.
- A second rule set on `dispute_reasons` shows which reasons co-occur.

**Attendance comparison:** dispute rate by `attendance_method` and by `timesheet_status`, with a note on confounding. In the synthetic data, App clients show a higher raw dispute rate than Biometric because of client mix. Also show the rate by `timesheet_variance_hours` band, which is the actual mechanism. This makes a good "diagnostic is harder than it looks" talking point.

## 9. Predictive

### 9.1 Classification (`core/models_classify.py`)

Targets: `paid_late`, `dispute_raised`. Same code path for both.

| Model | Settings |
|---|---|
| KNN | `n_neighbors` in {5, 11, 21, 31}, `weights` in {uniform, distance}; scaling is mandatory (already in preprocessor) |
| Decision tree | `max_depth` in {3, 5, 8}, `min_samples_leaf` in {10, 25}, `class_weight="balanced"` |
| Random forest | `n_estimators=300`, `max_depth` in {6, 10, None}, `min_samples_leaf` in {5, 15}, `class_weight="balanced_subsample"` |
| Gradient boosting | `HistGradientBoostingClassifier`, `learning_rate` in {0.05, 0.1}, `max_depth` in {3, None}, `max_iter=300` |

Search with `GridSearchCV(cv=TimeSeriesSplit(3), scoring="roc_auc")`.

**Threshold:** pick the threshold maximising F2 on the last three training months (refit excluded). Report metrics at 0.5 and at the tuned threshold.

**Report:** accuracy, precision, recall, F1, ROC AUC, confusion matrix (counts and normalised), ROC curves overlaid.

**Business framing in the UI:** a false negative is a late invoice nobody saw coming (cash shock). A false positive is chasing a client who would have paid (relationship cost).

**Feature importance:** `permutation_importance` on the test set for the best model, top 15.

**Leakage demo (BR-P6):** same RF pipeline plus `dispute_raised`, `stage_ack_days`, `first_followup_date` (as a "was chased" flag) and `short_paid_aed`. Show the accuracy jump and the importance chart dominated by leaked columns, next to a sentence explaining why it is useless on invoice day.

Persist the best model per target to `models/clf_<target>.joblib` together with its threshold and metrics.

### 9.2 Regression (`core/models_regress.py`)

- Target: `days_to_pay`.
- Models: `LinearRegression` (with a `Ridge` fallback if unstable), `RandomForestRegressor` (300 trees, depth grid), and `HistGradientBoostingRegressor`.
- Baseline: `prev_avg_days_to_pay`. For new clients the baseline is `payment_terms_days` plus the training mean of days past terms.
- Metrics: MAE, RMSE and R² for each model and the baseline.
- Charts: predicted vs actual scatter, and a residual histogram.
- Also roll predictions up to a forecast collection period per client: the amount-weighted mean of predicted days to pay.

### 9.3 Clustering (`core/models_cluster.py`)

Grain: one row per client, from paid invoices.

Features:
- mean `days_to_pay`
- mean `days_overdue`
- `paid_late` rate
- `dispute_raised` rate
- mean `stage_dispute_resolution_days` (0 if none)
- `payment_terms_days`
- share of revenue
- unapproved-OT rate
- unsigned-timesheet rate

Method:
- Standardise the features.
- Run `KMeans(k, n_init=20, random_state=42)` for k = 2 to 8, and show the elbow (inertia) and silhouette.
- Default k is the best silhouette in the range 3 to 5, and the user can override it.

Name segments by rules on the centroids. For example:
- low days and low disputes → "Fast and clean"
- high days and low disputes → "Slow but clean"
- high disputes → "Dispute prone"
- otherwise "Average"

Show:
- a PCA 2D scatter coloured by segment
- a segment profile table
- clients in each segment

Explain on the page why using full history is fine here (description, not prediction) and why the labels are not fed into the predictive models.

## 10. Prescriptive (`core/prescriptive.py`)

### 10.1 Segment policy table

A rules map from segment name to recommended policy, owner and the metric to watch, for example:

| Segment | Policy |
|---|---|
| Fast and clean | Keep terms; consider them for growth and longer terms |
| Slow but clean (often government) | Price the wait into rates; submit through portal; track approval layers; consider receivables financing |
| Dispute prone | Timesheet sign-off before invoicing; enforce OT pre-approval; LPO guard; weekly attendance confirmation |
| Average | Standard reminders at D-10, D+1, D+15 |

### 10.2 What-if simulator

The frame is invoices from the latest 12 complete months in the modelling frame.

Each intervention has an adoption slider from 0 to 100%. It applies to a random adoption share of rows, using a fixed seed:

| Intervention | Feature changes |
|---|---|
| Automated attendance | `attendance_method="App"`, `timesheet_variance_hours *= 0.2`, `timesheet_status` Unsigned or Remarks becomes Signed |
| OT pre-approval enforced | `ot_preapproved = 1` |
| LPO guard | `lpo_status="Valid"`, `lpo_valid=1` |
| Invoice QA | `docs_attached=1`, `rate_matches_contract=1` |
| Portal submission | `submission_channel="Client portal"` |
| Faster sign-off | `days_monthend_to_invoice -= N` (min 1) |
| Triage speed-up | Separate formula: `expected_days_saved = P(dispute) × days_saved_per_dispute × passthrough` |

**Outputs, before and after:**
- mean P(dispute)
- expected disputes per month
- amount-weighted mean predicted days to pay
- forecast DSO change

Cash released = DSO reduction × average daily credit sales over the last 12 months (AED).

Show these as a waterfall chart, one bar per intervention.

**Caveats shown in the UI:**
- These are associations learned from synthetic data, not proven causes.
- If an intervention moves a prediction the wrong way, the simulator shows it rather than hiding it.

## 11. Automation hub (`core/automation/`)

All functions are pure and take dataframes plus config. Each returns a dataframe of findings with these columns:

| Column | Values |
|---|---|
| `item_id` | |
| `node` | |
| `check_id` | |
| `severity` | Block, Warn or Info |
| `message` | |
| `recommended_action` | |
| `owner` | |

### 11.1 Attendance ledger (`ledger.py`)

A tamper-evident, hash-chained ledger. It stands in for a blockchain.

- `generate_month(client_row, invoice_row, seed)` produces daily records for one client and month. Hours must reconcile with the invoice's deployed heads, absence rate and OT hours.
- Record fields:
  - `seq`, `date`, `employee_id`, `shift`
  - `check_in`, `check_out`, `method`
  - `normal_hours`, `ot_hours`, `ot_approval_ref`
  - `prev_hash`, `hash`
- `hash = sha256(canonical_json(record_without_hash) + prev_hash)`. The genesis `prev_hash` is 64 zeros.
- **Daily seal:** at the end of each day both parties sign the last hash of that day with `hmac_sha256(key, hash)`. The supplier key and client key come from config and are for demo only.
- `verify(records, seals)` returns `(ok, first_bad_seq, reason)`. It recomputes every hash and checks every seal.
- `tamper(records, seq, field, value)` returns a modified copy for the demo.
- The UI shows the chain, a "Verify" button, a "Tamper with a record" control, the failed verification and the exact record that broke.
- A note in the UI explains what this proves (any edit after the seal is detectable) and what it does not (it doesn't stop a wrong entry at capture time). It also names the upgrade path to a permissioned shared ledger as future work.

### 11.2 LPO guard (`lpo_guard.py`)

These checks run on `current_batch` joined to `lpos`:

| check_id | Rule | Severity |
|---|---|---|
| LPO-01 | No LPO referenced | Block |
| LPO-02 | LPO not yet renewed (`lpo_status == "Not yet renewed"`) | Block |
| LPO-03 | Balance < invoice amount | Block |
| LPO-04 | Balance after this invoice < `low_balance_pct` of LPO value | Warn |
| LPO-05 | `valid_to` within `expiry_warn_months` | Warn |

Each finding recommends "Request renewal or top-up from client procurement".

### 11.3 Invoice QA (`invoice_qa.py`)

| check_id | Rule | Severity |
|---|---|---|
| QA-01 | `timesheet_status == "Unsigned"` | Block |
| QA-02 | `timesheet_status == "Signed with remarks"` | Warn |
| QA-03 | `lpo_valid == 0` (see LPO guard) | Block |
| QA-04 | `rate_matches_contract == 0` | Block |
| QA-05 | `docs_attached == 0` | Block |
| QA-06 | `ot_preapproved == 0` and `ot_hours_per_head > ot_hours_per_head_warn` | Warn |
| QA-07 | `headcount_gap_pct > headcount_gap_warn_pct` | Warn (check SLA deduction) |
| QA-08 | `timesheet_variance_hours > timesheet_variance_warn_hours` | Warn |

Invoice result:
- **Block** if any check returns Block.
- **Warn** if any check returns Warn and none return Block.
- **Pass** otherwise.

Each row also shows the classifier's P(dispute) and P(late) from the saved models.

### 11.4 WPS compliance (`wps_check.py`)

| check_id | Rule | Severity |
|---|---|---|
| WPS-01 | `pay_date > wps_due_date` | Block |
| WPS-02 | `ot_rate_multiplier_used < ot_multiplier_min` | Block |
| WPS-03 | `ot_hours > ot_hours_month_max` | Warn |
| WPS-04 | `days_paid > days_in_month` | Block |
| WPS-05 | `iban_on_file == 0` | Block |
| WPS-06 | Monthly share of employees paid on time < `establishment_on_time_min` | Block (establishment level) |

Planted counts the tests should find:

| Issue | Rows |
|---|---|
| Late pay | 411 |
| OT at 1.0x | 304 |
| OT > 60 h | 283 |
| days_paid > days_in_month | 38 |
| Missing IBAN | 75 |

Also chart late payroll against that client's invoice late rate. It's the cash squeeze made visible.

Stretch: export a WPS SIF-style draft (EDR rows plus an SCR summary row) for one month, labelled as a format demo.

### 11.5 Dispute triage (`triage.py`)

**Extractor:**
- Use regexes for `INV-\d{5}`, `inv\s*\d{1,5}` and `invoice\s*no\.?\s*\d{1,5}`, then normalise to `INV-%05d`.
- Confirm the invoice exists and belongs to the sender's `client_id`.
- If nothing is found, use the client's most recent disputed or unpaid invoice before `received_date` and mark it `low_confidence`.
- Evaluate against `invoice_id_true` and report the extraction accuracy.

**Classifier:**
- Labels: use a `MultiLabelBinarizer` over `labels`. Labels with fewer than `min_label_examples` training rows are excluded and routed to a human.
- Text: `subject + " " + body`, lowercased, with greetings and signature lines stripped by simple rules.
- Features: a `FeatureUnion` of TF-IDF word 1 to 2 grams and TF-IDF char_wb 3 to 5 grams. Character n-grams handle typos such as "attendence".
- Models to compare:
  - `OneVsRestClassifier(LogisticRegression(class_weight="balanced", max_iter=2000))`
  - `OneVsRestClassifier(CalibratedClassifierCV(LinearSVC(class_weight="balanced")))`
  - `OneVsRestClassifier(ComplementNB())`
- Split: sort by `received_date`; the first 75% is train, the last 25% is test.
- Metrics:
  - micro and macro F1, Hamming loss, subset accuracy
  - per-label precision, recall and F1
  - `multilabel_confusion_matrix` shown per label
  - dispute vs not-dispute accuracy
- Keep the best model by macro F1.

**Evidence tools.** Each one returns a dict:

| Tool | Returns |
|---|---|
| `evidence_timesheet(inv)` | status, variance hours, sign-off date |
| `evidence_ot(inv)` | OT hours, OT per head, pre-approved flag |
| `evidence_headcount(inv)` | contracted, deployed, gap %, relief share |
| `evidence_lpo(inv, lpos)` | number, status, balance, validity |
| `evidence_rate(inv)` | match flag |
| `evidence_docs(inv)` | attached flag |
| `evidence_sla(inv)` | clause, gap, deduction |
| `evidence_ledger(inv)` | ledger verification status for that client and month |

**Verdict rules.** Each verdict is one of `supports_client`, `supports_us` or `unclear`:

| Label | Supports us | Supports client | Action |
|---|---|---|---|
| TS_MISMATCH | Signed and variance ≤ 8 h | Unsigned, or variance > 20 h | Send signed timesheet and ledger extract / credit the variance |
| HC_DISCREPANCY | Gap ≤ 2% | Gap > 5% | Send deployment evidence / credit shortfall |
| OT_UNAPPROVED | `ot_preapproved == 1` | `ot_preapproved == 0` | Send approval reference / remove OT line and fix process |
| LPO_ISSUE | LPO Valid with balance | Otherwise | Quote valid LPO / request renewal, hold invoice |
| RATE_DISPUTE | Rate matches | Rate mismatch | Share rate clause / reissue at contract rate |
| DOCS_MISSING | Docs attached | Docs missing | Resend pack with all documents |
| SLA_PENALTY | No clause or gap ≤ 8% | Clause and gap > 8% | Contest with attendance / accept and issue credit note |

**Reply templates:** one per (label, verdict) pair, filled with invoice-specific facts. If there are several labels, concatenate the paragraphs.

**Routing to a human:** any of the following sends the email to a human:
- max label probability < `confidence_threshold`
- low-confidence extraction
- an excluded label
- any `unclear` verdict
- `NOT_DISPUTE` with a payment question, which goes to collections

**Decision log:** append to `data/runtime/triage_log.csv` with these fields:
- `email_id`
- predicted labels
- verdicts
- action
- human decision (approve, edit or reject)
- edited text
- timestamp

### 11.6 Collections (`collections.py`)

- Open invoices: priority = P(late) × amount × (1 + days_overdue / `overdue_weight_days`).
- Draft invoices: priority = P(late) × amount.

Actions by status and segment:
- not due and high risk → D-10 reminder
- 1 to 15 days overdue → D+1 reminder
- more than 15 days overdue → D+15 call
- more than 60 days overdue → escalate to the account manager

The reminder templates are tuned per segment. For example, government clients get a portal follow-up rather than a payment demand.

### 11.7 Router (`router.py`)

1. Concatenate the findings from LPO guard, invoice QA, WPS, triage routing and collections.
2. Assign an owner from the node:
   - attendance → Operations
   - LPO → Account manager
   - QA → Billing
   - WPS → Payroll
   - dispute → Account manager
   - collections → Collections
3. Sort by severity, then by AED at risk.

This is the single "today's actions" table on the Automation Hub page.

## 12. UI requirements

Every page has:
- a one-line purpose at the top
- an expander titled **"Why this technique"**, which gives the rationale required by the brief
- a download button for its main table

The sidebar holds the data source (bundled or uploaded), the snapshot date and model status.

| Page | Contents |
|---|---|
| Home | Process flow diagram (8 stages), headline KPIs, how to use the platform, data is synthetic notice |
| 1 Data and Cleaning | Raw sample, data quality summary (nulls, duplicates, typos), cleaning log table, data dictionary viewer |
| 2 Descriptive | KPI cards, DSO trend, breakdowns with a selector, aging, cash gap |
| 3 Diagnostic | Stage waterfalls, dispute Pareto, association rules with filters, attendance comparison |
| 4 Predictive | Tabs: Late payment, Dispute, Days to pay, Client segments, Leakage demo |
| 5 Prescriptive | Segment policy table, what-if sliders, before/after metrics, cash released waterfall, caveats |
| 6 Automation Hub | Tabs: Today's actions (router), Invoice QA, LPO guard, Attendance ledger, WPS check |
| 7 Dispute Triage | Model comparison metrics; inbox selector; one email processed step by step (extracted invoice, labels with probabilities, evidence cards, verdicts, draft reply in an editable text area, Approve / Edit / Reject buttons); decision log |
| 8 Collections | Ranked queue, filters by segment and status, template preview |

Use `st.cache_data` for data and descriptive results, and `st.cache_resource` for models. On the first run, load the models from `models/` if present. Otherwise train them and show a spinner.

## 13. Non-functional requirements

| Area | Requirement |
|---|---|
| Offline | No network calls at runtime; no API keys |
| Start-up | Cold start including training under 90 s on a normal laptop; warm start under 5 s |
| Reproducibility | `random_state=42` everywhere; data generators seeded |
| Portability | Works on Windows, macOS and Linux via Docker or a plain venv |
| Security | No secrets in the repo; demo HMAC keys are labelled as demo |
| Code quality | Type hints, docstrings, functions under about 60 lines, no logic in pages beyond layout |
| Honesty | Every estimate labelled; synthetic data notice on Home and in the README |

## 14. Testing (`tests/`)

| Test file | Checks |
|---|---|
| `test_cleaning.py` | 9 duplicates removed; sector values in the allowed set; no blanks in imputed columns; 5 amount fixes |
| `test_leakage.py` | Feature lists do not intersect `LEAKY`; train max service month < test min; for 50 random rows, recompute `prev_avg_days_to_pay` from invoices paid before `invoice_date` and match the column |
| `test_models.py` | Every classifier AUC > 0.6 on test; the best late model beats the majority-class baseline on recall; the leakage demo accuracy is higher than the clean accuracy; the regression MAE beats the baseline |
| `test_cluster.py` | k selection returns a value in range; every client gets exactly one segment |
| `test_rules.py` | Association rules have outcome-only consequents |
| `test_ledger.py` | Clean chain verifies; tampering seq 37 fails at seq 37; a broken seal is detected |
| `test_qa_lpo_wps.py` | Known synthetic cases give the expected severities; WPS counts match the planted counts |
| `test_triage.py` | Extractor accuracy ≥ 0.9 on emails that contain an explicit reference; best classifier macro F1 above a majority-label baseline; verdict rules give the expected outputs on fixed cases |
| `test_app.py` | `AppTest.from_file` runs every page without exceptions |

Run with `pytest -q`. CI is optional (GitHub Actions running pytest).

## 15. Packaging and deployment

**requirements.txt** (versions are minimums; pin after the first successful build)

```
pandas>=2.2
numpy>=1.26
scikit-learn>=1.4
mlxtend>=0.23
streamlit>=1.36
plotly>=5.20
pyyaml>=6.0
joblib>=1.3
pytest>=8.0
```

**Dockerfile:**
- base image `python:3.11-slim`
- non-root user
- `pip install --no-cache-dir -r requirements.txt`
- copy the repo
- `RUN python -m core.train`, so models are baked in
- `EXPOSE 8501`
- `HEALTHCHECK` on `/_stcore/health`
- `CMD ["streamlit", "run", "app/Home.py", "--server.address=0.0.0.0"]`

**docker-compose.yml:**
- one service
- port 8501:8501
- volume `./data/runtime:/app/data/runtime`

**Streamlit Community Cloud:**
1. Push to GitHub.
2. Create a new app with main file `app/Home.py` and Python 3.11.

**Submission zip:**
- the repository without `models/`, `data/runtime/` and `.git`
- the report
- a one-page `HOW_TO_RUN.md` covering Docker and a plain venv

## 16. Known limitations to state in the report

- Synthetic data: the patterns were partly designed in.
- Recent invoices are excluded from modelling because of censoring, so the model doesn't learn from the very latest behaviour.
- The prescriptive simulator is associational, not causal.
- The triage classifier is trained on generated text with limited variety. Real emails will be messier, and the logged human decisions are the path to retraining.
- The hash-chained ledger proves integrity after sealing, not truth at capture.
