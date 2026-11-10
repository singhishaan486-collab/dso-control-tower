# DSO Control Tower

A prototype analytics and automation platform for a UAE manpower and facility services company. It shows where cash gets stuck between paying staff through WPS and getting paid by clients, predicts which invoices will be late or disputed, estimates what process changes would release, and runs checks before invoices and payroll go out.

Built for the Data Analytics (DIVA) course, MGB June 2026, SP Jain School of Global Management, Dubai.

> **All data is synthetic.** It was generated to match published UAE ranges. The patterns show how the pipeline works, not facts about a real company, and some of them were built into the generator.

Everything runs offline. There are no API keys, no language models and no network calls.

## How to run

You need Python 3.11 or newer. The project was tested on Python 3.12 with pandas 3.1, scikit-learn 1.9 and Streamlit 1.67.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe data\generate_data.py
.venv\Scripts\python.exe data\generate_emails.py
.venv\Scripts\python.exe -m streamlit run app\Home.py
```

**macOS or Linux**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python data/generate_data.py
.venv/bin/python data/generate_emails.py
.venv/bin/streamlit run app/Home.py
```

The app opens at http://localhost:8501. The data files are already in `data/`, so the two generator commands are only needed to rebuild them.

The first visit to a model page trains every model, which takes about a minute. The results are saved in `models/`, so later starts take a few seconds. If the data changes, the models retrain automatically. To retrain by hand:

```bash
python -m core.models
```

**Run the tests**

```bash
python -m pytest -q
```

The tests check that no model can use a column that only exists after the invoice is sent, that training months come before test months, and that every page opens without errors.

## Pages

| Page | What it answers | Techniques |
|---|---|---|
| Overview | Headline KPIs with trends, monthly activity, slowest and fastest payers, client and sector leaderboards, the 8-stage process | Filters, rank changes |
| 1 Data and cleaning | What was wrong with the raw data and every fix applied | Cleaning log, data dictionary |
| 2 Descriptive | Where DSO stands, which segments drive it, how long the cash gap is | DSO, aging, breakdowns |
| 3 Diagnostic | Which stage loses the days and which conditions lead to disputes | Stage waterfall, Pareto, association rules (apriori) |
| 4 Predictive | Will this invoice be late or disputed, and how many days will it take | KNN, decision tree, random forest, gradient boosting, regression, k-means, leakage demo |
| 5 Prescriptive | What policy fits each client segment, and what each process change would release | Segment policies, what-if simulator |
| 6 Automation | Which draft invoices to stop, whether attendance records were changed, whether payroll is WPS compliant | Rule engines, SHA-256 hash chain with HMAC seals |
| 7 Dispute triage | Which invoice a dispute email is about, why, what the evidence says and what to reply | Regular expressions, TF-IDF text classification, written verdict rules |

Every page has a **Why this technique** box and download buttons for its tables.

## How leakage is prevented

A model that predicts on invoice day may only use what is known on invoice day.

- `docs/DATA_DICTIONARY.md` tags every column with when it becomes known: Contract, Invoice or Later.
- `core/features.py` holds the allowed `FEATURES` and the forbidden `LEAKY` list, and a test checks they never overlap.
- Models train on earlier service months and are tested on later ones. Nothing is shuffled across time.
- Invoices from the most recent months are left out of modelling because many have not been paid yet.
- The Predictive page includes a labelled leakage demo that shows what happens when the rule is broken.

## Project layout

```
app/                Streamlit pages (layout only)
  Home.py           entry point: sidebar navigation
  components.py     styling, shared loading, explainer box, downloads, card rows
  assets/           logo
  pages/            Overview and pages 1 to 7
core/               all logic
  data.py           loading, cleaning, cleaning log, DSO
  features.py       feature lists, leakage guard, time split, preprocessor
  overview.py       Overview filters, KPI cards, activity, leaderboards
  descriptive.py    KPIs, DSO trend, breakdowns, aging, cash gap
  diagnostic.py     stage waterfall, dispute Pareto, association rules
  models.py         classification, regression, clustering, leakage demo
  prescriptive.py   segment policies, what-if simulator
  automation.py     invoice QA, LPO guard, attendance ledger, WPS check
  triage.py         invoice extractor, text classifiers, evidence, verdicts, replies
  charts.py         shared Plotly charts
config/config.yaml  every threshold
data/               synthetic data and its generators
docs/               BRD, TRD, data dictionary, build plan
models/             trained models (created on first run)
tests/              leakage and page tests
```

## Known limitations

- The data is synthetic, and some patterns were designed into the generator.
- Recent invoices are left out of modelling because they have not settled yet, so the models miss the very latest behaviour.
- The days-to-pay regression does not beat the simple baseline of each client's own past average.
- The what-if simulator is associational, not causal. It can move a prediction the wrong way, and it shows that when it happens.
- The triage classifier scores near perfectly because the synthetic emails reuse a fixed set of phrases. Real emails would score lower.
- The hash-chained ledger proves records were not changed after sealing, not that they were right when captured.
- WPS rules come from secondary reporting of Ministerial Resolution 340 of 2026 and must be checked against MOHRE before real use.
