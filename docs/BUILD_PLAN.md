# Build plan (lean, about 3.5 hours)

This plan **overrides the scope** of BRD.md and TRD.md. Build only what is listed here. Use the TRD for detail on anything listed. Anything in the BRD or TRD not listed here is out of scope.

| Phase | Builds | Time |
|---|---|---|
| 0 | Set up folders, generate data, skeleton app, Data and Cleaning page | 25 min |
| 1 | Descriptive and Diagnostic pages | 50 min |
| 2 | Predictive page (classification, regression, clustering, leakage demo) | 60 min |
| 3 | Prescriptive page | 30 min |
| 4 | Automation page (invoice QA with LPO checks, attendance ledger, WPS check) | 30 min |
| 5 | Dispute triage page, final check, optional deploy | 35 min |

**Leave about 1.5 hours for your report.** It has to be in your own words. After each phase, write 3 or 4 lines on what the page shows and what you learned. Those notes become the report.

## Out of scope (do not build)
Upload of user files, separate collections page, router, decision log file, Docker testing, hyperparameter grid searches, CI, most tests. Keep only `tests/test_leakage.py` and `tests/test_app.py`.

## Fixed model settings (no grid search)
| Model | Settings |
|---|---|
| KNN | `n_neighbors=15, weights="distance"` |
| Decision tree | `max_depth=6, min_samples_leaf=20, class_weight="balanced"` |
| Random forest | `n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample"` |
| Gradient boosting | `HistGradientBoostingClassifier(learning_rate=0.1, max_iter=200)` |
| Regression | `LinearRegression`, `RandomForestRegressor(300, min_samples_leaf=5)`, `HistGradientBoostingRegressor()` |
| K-means | k from 2 to 6, pick best silhouette, `n_init=20` |
| Triage | TF-IDF (word 1 to 2 grams + char_wb 3 to 5 grams) with `OneVsRest(LogisticRegression(class_weight="balanced"))` vs `OneVsRest(ComplementNB())` |

All `random_state=42`.

---

## Prompts to paste into Claude Code

### Phase 0: setup and data page
```
Read CLAUDE.md and docs/BUILD_PLAN.md first. BUILD_PLAN.md defines the scope. Skim docs/TRD.md and docs/DATA_DICTIONARY.md for detail.

1. Arrange the files I gave you into this layout (create folders as needed):
   CLAUDE.md, requirements.txt at the root
   docs/BRD.md, docs/TRD.md, docs/DATA_DICTIONARY.md, docs/BUILD_PLAN.md
   config/config.yaml
   core/__init__.py (empty), core/data.py
   data/generate_data.py, data/generate_emails.py
2. pip install -r requirements.txt
3. Run: python data/generate_data.py then python data/generate_emails.py
4. Create core/features.py per TRD section 6 (FEATURES, LEAKY, invoice_month, build_preprocessor, time_split, get_xy).
5. Create app/Home.py (8-stage process flow as a simple table or diagram, headline KPIs placeholder, a clear "synthetic data" notice) and app/components.py (explainer expander titled "Why this technique", CSV download button).
6. Create app/pages/1_Data_and_Cleaning.py: raw sample, data quality summary, the cleaning log from core/data.py load_all(), and the data dictionary.
7. Create tests/test_leakage.py (feature lists do not intersect LEAKY; train max month < test min month) and tests/test_app.py (AppTest runs every page without exceptions).
8. Run pytest and streamlit. Fix errors. Summarise and stop.
```

### Phase 1: descriptive and diagnostic
```
Phase 1. Create core/descriptive.py per TRD section 7 (kpis, dso_trend, breakdown, aging, cash_gap) and page 2_Descriptive.py.
Create core/diagnostic.py per TRD section 8: stage waterfall disputed vs not disputed, dispute Pareto with mean resolution days, association rules (mlxtend apriori, outcome-only consequents, sorted by lift), dispute rate by attendance method AND by timesheet variance band with a short note on confounding. Page 3_Diagnostic.py.
Put real KPIs on Home. Every page gets the "Why this technique" expander and a download button. Run tests. Show me the top 10 association rules and stop.
```

### Phase 2: predictive
```
Phase 2. Create core/models.py using the fixed settings in BUILD_PLAN.md (no grid search):
- classification for paid_late and dispute_raised with KNN, decision tree, random forest, gradient boosting; time split from core/features.py; metrics accuracy, precision, recall, F1, ROC AUC; confusion matrices; permutation importance top 15 for the best model
- regression for days_to_pay with linear, RF, gradient boosting and the baseline from TRD 9.2; MAE, RMSE, R2; predicted vs actual chart
- k-means client segments per TRD 9.3 with elbow, silhouette, rule-based segment names, PCA scatter, profile table
- leakage demo per TRD 9.1
- a train_all() function that trains everything once and saves to models/ with joblib; cache it in the app with st.cache_resource
Page 4_Predictive.py with tabs: Late payment, Dispute, Days to pay, Client segments, Leakage demo. In the classification tabs, explain false negatives and false positives in business terms (TRD 9.1).
Run tests. Report all metrics in one table and stop.
```

### Phase 3: prescriptive
```
Phase 3. Create core/prescriptive.py per TRD section 10: segment policy table and the what-if simulator with adoption sliders for automated attendance, OT pre-approval, LPO guard, invoice QA and faster sign-off (skip portal and triage speed-up). Reuse the saved models. Show before/after P(dispute), predicted days to pay, DSO change and cash released in AED, with the caveats from TRD 10.2.
Page 5_Prescriptive.py. Run tests. Show me the result at 80% adoption for every lever and stop.
```

### Phase 4: automation
```
Phase 4. Create core/automation.py with:
- invoice_qa(current_batch, lpos, config): checks QA-01 to QA-08 from TRD 11.3 plus LPO-01 to LPO-05 from TRD 11.2; overall Pass/Warn/Block per invoice; add P(dispute) and P(late) from the saved models; sort by risk x amount
- attendance ledger per TRD 11.1: generate one client-month of daily records, SHA-256 hash chain, daily HMAC seals with the demo keys in config, verify(), tamper()
- wps_check(payroll, config): checks WPS-01 to WPS-06 from TRD 11.4, summary by month and client, and a chart of payroll late rate vs that client's invoice late rate
Page 6_Automation.py with tabs: Invoice QA (this month's drafts), Attendance ledger (verify and tamper demo), WPS check. Run tests. Report Pass/Warn/Block counts and WPS violation counts. Stop.
```

### Phase 5: dispute triage and finish
```
Phase 5. Create core/triage.py per TRD 11.5, simplified: invoice extractor (regex + fallback), the two classifiers in BUILD_PLAN.md compared on a time split (per-label precision, recall, F1, macro F1), evidence functions, verdict rules table, reply templates, and routing to a human when confidence < 0.5, extraction is low confidence, or any verdict is unclear. No decision log file; keep approve/edit/reject in session state.
Page 7_Dispute_Triage.py: model comparison at the top, then pick an email and show each step (extracted invoice, labels with probabilities, evidence, verdicts, editable draft reply, Approve/Edit/Reject).
Then: run the full test suite, open every page, fix anything broken, check there are no em dashes in any UI text, and write README.md with run instructions. Stop and summarise.
```

### Optional, only if time remains
```
Deploy: push to GitHub and set up Streamlit Community Cloud with main file app/Home.py. Give me the steps.
```

## Your checks after each phase
- Open the page and click everything.
- Ask Claude Code "which columns does this model use?" and compare against the data dictionary.
- Write your 3 or 4 lines of notes.
