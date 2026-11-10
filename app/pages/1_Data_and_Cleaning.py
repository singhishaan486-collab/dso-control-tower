import pandas as pd
import streamlit as st

import components as ui
from core.quality import quality_summary, read_dictionary

st.set_page_config(page_title="Data and cleaning", layout="wide")
ui.page_header("Data and cleaning",
               "What the raw invoice file looked like, what was wrong with it, and every fix applied.")

d = ui.get_data()
raw, inv = d["raw"], d["inv"]
quality = quality_summary(raw)
log = pd.DataFrame(d["log"]).rename(columns={"step": "Step", "rows_affected": "Rows affected", "why": "Why"})

c1, c2, c3, c4 = st.columns(4)
c1.metric("Raw rows", f"{quality['rows']:,}")
c2.metric("Rows after cleaning", f"{len(inv):,}")
c3.metric("Exact duplicate rows", quality["duplicate_rows"])
c4.metric("Columns with blanks", len(quality["missing"]))

st.subheader("Raw sample")
st.caption("The first 20 rows exactly as they arrived, before any fix.")
st.dataframe(raw.head(20), width="stretch")

st.subheader("Data quality summary")
left, right = st.columns(2)
with left:
    st.markdown("**Blank values by column**")
    st.caption("Some blanks are expected: payment_date is blank for invoices still open, and the dispute "
               "columns are blank for invoices that were never disputed.")
    ui.table(quality["missing"], {
        "column": ui.col_text("Column", "Column name in the raw file.", 200),
        "missing_rows": ui.col_number("Missing rows", "Rows with no value in this column.", "%d", 120),
        "missing_pct": ui.col_number("Missing share", "Missing rows as a share of all rows.", "%.1f%%", 120)})
with right:
    st.markdown("**Sector labels that are not one of the six sectors**")
    st.caption("The same sector typed in different ways would split one group into several.")
    ui.table(quality["sector_variants"], {
        "raw_label": ui.col_text("Label as typed", "The sector text exactly as it appears in the raw file.", 220),
        "rows": ui.col_number("Rows", "Rows that use this label.", "%d", 90)})

st.subheader("Cleaning log")
st.caption("Every step applied, in order, with the number of rows it touched and the reason.")
ui.table(log, {"Step": ui.col_text("Step", width=320),
              "Rows affected": ui.col_number("Rows affected", "Rows this step changed or removed.", "%d", 100),
              "Why": ui.col_text("Why", "Click a cell to read the full reason.", 540)})
ui.download_csv(log, "cleaning_log.csv", "Download the cleaning log")

st.subheader("Data dictionary")
st.caption("known_at decides what a model may use. Contract and Invoice columns are known on invoice day. "
           "Later columns are only known after the invoice goes out, so they can never be model features.")
dictionary = read_dictionary()
known = st.segmented_control("Show columns known at", ["All", "Contract", "Invoice", "Later"], default="All")
shown = dictionary if known in (None, "All") else dictionary[dictionary["known_at"] == known]
ui.table(shown, {"column": ui.col_text("Column", "Column name in the data.", 200),
                 "group": ui.col_text("Group", width=110),
                 "known_at": ui.col_text("Known at", "When the value becomes known: Contract, Invoice or Later. "
                                                     "Models predicting on invoice day may only use Contract and "
                                                     "Invoice columns.", 100),
                 "meaning": ui.col_text("Meaning", width=390), "use": ui.col_text("Use", width=140)})
ui.download_csv(dictionary, "data_dictionary.csv", "Download the data dictionary")

ui.explainer(
    "Models learn whatever is in the data, including mistakes. A duplicated invoice doubles its revenue, a "
    "sector typed five ways becomes five sectors, and an amount with an extra zero distorts DSO. Each fix uses "
    "the most local information available: attendance method comes from the same client's other invoices, "
    "and numeric blanks use that client's median, so one client's habits are not overwritten by another's.\n\n"
    "The data dictionary's known_at column is the leakage rule. A model that predicts on invoice day can only "
    "use what is known on invoice day."
)
