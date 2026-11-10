# CLAUDE.md

Project: **DSO Control Tower**, a prototype analytics and automation platform for a UAE manpower company. Student project for a Data Analytics course, built under time pressure. Owner: Ishaan.

## Scope
`docs/BUILD_PLAN.md` defines what to build. It overrides the BRD and TRD where they differ. Use `docs/TRD.md` for detail on listed items only. Do not build anything outside the plan. Prefer simple, working code over complete code.

## Read first
- `docs/BUILD_PLAN.md`: phases, scope, fixed model settings
- `docs/TRD.md`: module specs, feature lists, rules
- `docs/DATA_DICTIONARY.md`: every column and when it becomes known
- `docs/BRD.md`: business context (reference only)

## Non-negotiable rules
1. **No data leakage.** Models predicting at invoice stage may only use columns whose `known_at` is Contract or Invoice. The canonical lists are `FEATURES` and `LEAKY` in `core/features.py`. Never add a LEAKY column to a feature list (except in the clearly labelled leakage demo).
2. **Time-based splits only.** Never shuffle invoices or emails across time. Train on earlier months, test on later months.
3. **No LLMs, no API keys, no network calls at runtime.** It must run offline on the professor's laptop.
4. **Thresholds live in `config/config.yaml`.**
5. **Pages are layout only.** Logic goes in `core/`.
6. **Every automated output is a recommendation.** Nothing sends, pays or deletes.
7. **Label estimates honestly.** Prescriptive numbers state they are model estimates on synthetic data.
8. **Do not change the data generators or `core/data.py` logic.** Extend `core/data.py` only if needed (for example `load_emails()`).
9. **UI text:** plain, human sentences, sentence case headings. Never use em dashes or en dashes.

## Commands
```bash
pip install -r requirements.txt
python data/generate_data.py && python data/generate_emails.py
streamlit run app/Home.py
pytest -q
```

## Definition of done for each phase
- `pytest -q` passes.
- Every finished page opens without errors.
- Every page has a "Why this technique" expander and a download button.
- Stop and summarise at the end of each phase. Do not start the next phase until asked.
