"""Entry point: `streamlit run app/Home.py`. Sets up the sidebar navigation and runs the chosen page."""
import streamlit as st

import components as ui

st.set_page_config(page_title="DSO Control Tower", layout="wide")
st.logo(str(ui.ASSETS / "logo.svg"), size="large", icon_image=str(ui.ASSETS / "icon.svg"))
ui.apply_style()

pages = {
    "": [st.Page("pages/0_Overview.py", title="Overview", icon=":material/trending_up:", default=True)],
    "Analytics": [
        st.Page("pages/1_Data_and_Cleaning.py", title="Data and cleaning", icon=":material/table_chart:"),
        st.Page("pages/2_Descriptive.py", title="Descriptive", icon=":material/bar_chart:"),
        st.Page("pages/3_Diagnostic.py", title="Diagnostic", icon=":material/troubleshoot:"),
        st.Page("pages/4_Predictive.py", title="Predictive", icon=":material/insights:"),
        st.Page("pages/5_Prescriptive.py", title="Prescriptive", icon=":material/tune:"),
        st.Page("pages/8_Explorer.py", title="Explorer", icon=":material/explore:"),
    ],
    "Operations": [
        st.Page("pages/6_Automation.py", title="Automation", icon=":material/bolt:"),
        st.Page("pages/7_Dispute_Triage.py", title="Dispute triage", icon=":material/forum:"),
    ],
}
st.navigation(pages).run()
