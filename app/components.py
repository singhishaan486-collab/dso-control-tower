"""Shared page pieces: styling, data loading, the rationale expander, CSV downloads and HTML card rows."""
import base64
import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import data  # noqa: E402
from core.config import load_config  # noqa: E402

import theme as T  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
BADGE_COLORS = T.BADGE_CYCLE

_TOKENS = (f":root {{ --bg: {T.BG}; --surface: {T.SURFACE}; --surface-2: {T.SURFACE_2}; --border: {T.BORDER}; "
           f"--text: {T.TEXT}; --muted: {T.MUTED}; --cyan: {T.CYAN}; --slate: {T.SLATE}; --orange: {T.ORANGE}; "
           f"--font-ui: {T.FONT_UI}; --font-num: {T.FONT_NUM}; }}")

STYLE = "<style>" + _TOKENS + """
:root { --glass: rgba(26, 31, 35, 0.58); --glass-edge: rgba(255, 255, 255, 0.10); --glass-top: rgba(255, 255, 255, 0.18);
  --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  --inner: rgba(255, 255, 255, 0.04); --field: rgba(255, 255, 255, 0.05); --field-edge: rgba(255, 255, 255, 0.12);
  --ring: 0 0 0 3px rgba(102, 244, 255, 0.22); --radius: 16px; --ease-out: cubic-bezier(0.23, 1, 0.32, 1); }

/* Page background: charcoal with soft colour fields and faint diagonal lines, fixed behind everything.
   The strong part of each field sits in a corner under the sidebar or header, so text on the page
   never sits on more than about 8% tint and muted text stays above 4.5:1. */
[data-testid="stApp"] { background: var(--bg); isolation: isolate; color: var(--text); font-family: var(--font-ui); }
[data-testid="stApp"]::before { content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background:
    radial-gradient(circle at 0% 0%, rgba(102, 244, 255, 0.14) 0, rgba(102, 244, 255, 0.07) 22vw, transparent 52vw),
    radial-gradient(circle at 100% 0%, rgba(255, 192, 103, 0.12) 0, rgba(255, 192, 103, 0.06) 16vw, transparent 44vw),
    radial-gradient(ellipse 70vw 45vh at 50% 125%, rgba(125, 153, 170, 0.16) 0, rgba(125, 153, 170, 0.07) 60%, transparent 100%),
    repeating-linear-gradient(135deg, rgba(255, 255, 255, 0.04) 0 1px, transparent 1px 14px),
    var(--bg); }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stBottom"] > div { background: transparent; }
[data-testid="stHeader"] { background: rgba(18, 22, 25, 0.82); }
.block-container { padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1440px; }
h1 { font-size: 2rem !important; }
h1, h2, h3, h4 { color: var(--text); letter-spacing: -0.01em; }
[data-testid="stCaptionContainer"], .stCaption { color: var(--muted); font-size: 13px; opacity: 1 !important; }

/* Glass: cards, stand-alone metrics and stand-alone charts. Only the outermost box blurs. */
[class*="st-key-card"],
[data-testid="stMetric"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *),
[data-testid="stPlotlyChart"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *) {
  background: var(--glass); -webkit-backdrop-filter: blur(16px) saturate(140%); backdrop-filter: blur(16px) saturate(140%);
  border: 1px solid var(--glass-edge); border-top-color: var(--glass-top); border-radius: var(--radius);
  box-shadow: var(--glass-shadow); padding: 18px 20px;
  transition: transform 150ms var(--ease-out), border-color 150ms ease; }
/* Stand-alone charts keep the glass fill and edge but not the blur, so a chart-heavy page stays within about
   12 blurred elements. The fill is a little more opaque to make up for it. Streamlit sizes the chart to the
   card's full box, so any padding would push it past the edge: spacing comes from the figure margins. */
[data-testid="stPlotlyChart"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *) {
  padding: 0; overflow: hidden; background: rgba(26, 31, 35, 0.72);
  -webkit-backdrop-filter: none; backdrop-filter: none; }
/* Anything inside a card or an expander is flat: no blur, no second border. */
[class*="st-key-card"] [data-testid="stMetric"], [class*="st-key-card"] [data-testid="stPlotlyChart"],
[data-testid="stExpander"] [data-testid="stMetric"], [data-testid="stExpander"] [data-testid="stPlotlyChart"] {
  background: transparent; border: none; padding: 0; box-shadow: none; }

/* Expanders and the tab bar use the glass fill without blur, to keep the blur count low. */
[data-testid="stExpander"] details { background: rgba(26, 31, 35, 0.78); border: 1px solid var(--glass-edge);
  border-top-color: var(--glass-top); border-radius: var(--radius); box-shadow: var(--glass-shadow); }
[data-testid="stExpander"] summary { color: var(--text); transition: color 150ms ease; }
[data-testid="stExpander"] summary:hover { color: var(--cyan); }

/* Metrics: muted label, large tabular value, delta as a small pill. */
[data-testid="stMetricLabel"] p { color: var(--muted); font-size: 13px; }
[data-testid="stMetricValue"] { color: var(--text); font-family: var(--font-num); font-size: 36px; font-weight: 600; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums; line-height: 1.15; }
[data-testid="stMetricDelta"] { border-radius: 999px; padding: 2px 9px; font-size: 12px; font-weight: 600; }
[data-testid="stMetricChart"] svg { background-color: transparent !important; }
[data-testid="stMetricChart"] .mark-area path { fill: rgba(102, 244, 255, 0.16) !important; }
[data-testid="stMetricChart"] .mark-line path, [data-testid="stMetricChart"] .mark-area path { stroke: var(--cyan) !important; }

/* Charts never sit on a white box. */
[data-testid="stPlotlyChart"] > div, .js-plotly-plot .plotly .main-svg { background: transparent !important; }

/* Tables: solid surface, no blur. */
[data-testid="stDataFrame"], [data-testid="stTable"] { background: var(--surface); border: 1px solid var(--glass-edge);
  border-radius: 12px; overflow: hidden; }
[data-testid="stTable"] table { color: var(--text); font-variant-numeric: tabular-nums; }
[data-testid="stTable"] th { background: var(--surface-2); color: var(--muted); font-weight: 400; }
[data-testid="stTable"] td, [data-testid="stTable"] th { border-color: var(--border); }

/* Tabs: a pill bar, the active tab a lighter pill, no underline. */
[data-testid="stTabs"] [role="tablist"] { display: inline-flex; width: fit-content; max-width: 100%; gap: 4px;
  padding: 4px; background: rgba(26, 31, 35, 0.78); border: 1px solid var(--glass-edge);
  border-top-color: var(--glass-top); border-radius: 999px; box-shadow: var(--glass-shadow); }
[data-testid="stTabs"] [role="tablist"]::before, [data-testid="stTabs"] [role="tablist"]::after { display: none; }
[data-testid="stTab"] { border-radius: 999px; padding: 6px 16px; height: auto; color: var(--muted);
  background: transparent; border: none; transition: background-color 150ms ease, color 150ms ease; }
[data-testid="stTab"] p { font-size: 14px; color: inherit; }
[data-testid="stTab"]:hover { color: var(--text); }
[data-testid="stTab"][aria-selected="true"] { background: rgba(255, 255, 255, 0.10); color: var(--text); }
[data-testid="stTab"]:focus-visible { box-shadow: var(--ring); outline: none; }
[data-testid="stTabs"] .react-aria-SelectionIndicator { display: none; }

/* Inputs, selects and sliders. */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] {
  background: var(--field) !important; border-color: var(--field-edge) !important;
  transition: border-color 150ms ease, box-shadow 150ms ease; }
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {
  border-color: var(--cyan) !important; box-shadow: var(--ring); }
[data-baseweb="popover"] ul { background: var(--surface-2); }
[data-testid="stWidgetLabel"] p { color: var(--muted); font-size: 13px; }
[data-testid="stSlider"] [role="slider"] { background: var(--cyan); box-shadow: 0 0 0 3px rgba(102, 244, 255, 0.18); }
[data-testid="stSlider"] [role="slider"]:focus-visible { box-shadow: var(--ring); }
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {
  color: var(--muted); font-family: var(--font-num); font-size: 13px; }

/* Buttons, including downloads. */
.stButton button, [data-testid="stDownloadButton"] button { background: var(--field); color: var(--text);
  border: 1px solid var(--field-edge); border-radius: 10px;
  transition: border-color 150ms ease, color 150ms ease, transform 150ms var(--ease-out); }
.stButton button:hover, [data-testid="stDownloadButton"] button:hover { border-color: var(--cyan); color: var(--cyan); }
.stButton button:active, [data-testid="stDownloadButton"] button:active { transform: scale(0.97); }
.stButton button:focus-visible, [data-testid="stDownloadButton"] button:focus-visible { box-shadow: var(--ring); }

/* Sidebar: the same glass recipe, the current page a lighter pill with cyan text. */
[data-testid="stSidebar"] { background: var(--glass) !important; -webkit-backdrop-filter: blur(16px) saturate(140%);
  backdrop-filter: blur(16px) saturate(140%); border-right: 1px solid var(--glass-edge); }
[data-testid="stSidebar"] > div, [data-testid="stSidebarContent"], [data-testid="stSidebarHeader"] { background: transparent; }
[data-testid="stSidebarNavLink"] { border-radius: 999px; transition: background-color 150ms ease; }
[data-testid="stSidebarNavLink"]:hover { background: rgba(255, 255, 255, 0.06); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(255, 255, 255, 0.10); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: var(--cyan) !important; }
[data-testid="stSidebarNavSeparator"] { border-color: var(--glass-edge); }

[data-testid="stAlert"] { border-radius: 12px; }

/* Without blur support, or when the viewer asks for less transparency, glass becomes a solid surface. */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  [class*="st-key-card"], [data-testid="stMetric"]:not([class*="st-key-card"] *),
  [data-testid="stPlotlyChart"]:not([class*="st-key-card"] *), [data-testid="stSidebar"] { background: var(--surface) !important; }
}
@media (prefers-reduced-transparency: reduce) {
  [class*="st-key-card"], [data-testid="stMetric"]:not([class*="st-key-card"] *),
  [data-testid="stPlotlyChart"]:not([class*="st-key-card"] *), [data-testid="stSidebar"] {
    background: var(--surface) !important; -webkit-backdrop-filter: none; backdrop-filter: none; }
  [class*="st-key-card"] [data-testid="stMetric"], [class*="st-key-card"] [data-testid="stPlotlyChart"] { background: transparent !important; }
}

/* Motion: cards fade in and rise 12px on page load, staggered by column. Opacity and transform only.
   "backwards" fill means the rest state is the normal style, so hover can still move the card. */
@keyframes dso-rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
@keyframes dso-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
[class*="st-key-card"],
[data-testid="stMetric"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *),
[data-testid="stPlotlyChart"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *) {
  animation: dso-rise 350ms var(--ease-out) backwards; }
[data-testid="stColumn"]:nth-child(2) [class*="st-key-card"], [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"],
[data-testid="stColumn"]:nth-child(2) [data-testid="stPlotlyChart"] { animation-delay: 60ms; }
[data-testid="stColumn"]:nth-child(3) [class*="st-key-card"], [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"],
[data-testid="stColumn"]:nth-child(3) [data-testid="stPlotlyChart"] { animation-delay: 120ms; }
[data-testid="stColumn"]:nth-child(4) [class*="st-key-card"], [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"],
[data-testid="stColumn"]:nth-child(4) [data-testid="stPlotlyChart"] { animation-delay: 180ms; }
[data-testid="stColumn"]:nth-child(n+5) [class*="st-key-card"], [data-testid="stColumn"]:nth-child(n+5) [data-testid="stMetric"],
[data-testid="stColumn"]:nth-child(n+5) [data-testid="stPlotlyChart"] { animation-delay: 240ms; }
.ov-fill { transform-origin: left center; animation: dso-grow 500ms var(--ease-out) 150ms backwards; }
@media (hover: hover) and (pointer: fine) {
  [class*="st-key-card"]:hover,
  [data-testid="stMetric"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *):hover,
  [data-testid="stPlotlyChart"]:not([class*="st-key-card"] *):not([data-testid="stExpander"] *):hover {
    transform: translateY(-2px); border-color: rgba(102, 244, 255, 0.55); }
}
@media (prefers-reduced-motion: reduce) {
  [class*="st-key-card"], [data-testid="stMetric"], [data-testid="stPlotlyChart"], .ov-fill, .mt-bar span,
  [data-testid="stTab"], .stButton button, [data-testid="stDownloadButton"] button {
    animation: none !important; transition: none !important; }
  [class*="st-key-card"]:hover, [data-testid="stMetric"]:hover, [data-testid="stPlotlyChart"]:hover { transform: none !important; }
}

/* Overview rows: badge, name, progress bar and value. */
.ov-title { font-size: 15px; font-weight: 600; color: var(--text); }
.ov-sub { font-size: 13px; color: var(--muted); }
.ov-row { display: grid; grid-template-columns: 40px 1fr 104px; gap: 14px; align-items: center; padding: 9px 0; }
.ov-badge { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center;
  justify-content: center; color: var(--bg); font-weight: 700; font-size: 12px; font-family: var(--font-num); }
.ov-name { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 7px; }
.ov-track { height: 8px; border-radius: 6px; overflow: hidden; background: rgba(255, 255, 255, 0.08); }
.ov-fill { height: 100%; border-radius: 6px; }
.ov-warm .ov-fill { background: var(--orange); }
.ov-cool .ov-fill { background: var(--cyan); }
.ov-val { font-size: 14px; font-weight: 600; color: var(--text); text-align: right; white-space: nowrap;
  font-family: var(--font-num); font-variant-numeric: tabular-nums; }
.ov-val span { display: block; color: var(--muted); font-weight: 400; font-size: 13px; font-family: var(--font-ui); }

/* Leaderboard rows: avatar, name and detail, rank and rank change. */
.lb-row { display: grid; grid-template-columns: 40px 1fr 32px 22px; gap: 12px; align-items: center;
  padding: 10px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
.lb-row:last-child { border-bottom: none; }
.lb-avatar { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; color: var(--bg); font-weight: 700; font-size: 12px; font-family: var(--font-num); }
.lb-name { font-size: 14px; font-weight: 600; color: var(--text); }
.lb-detail { font-size: 13px; color: var(--muted); }
.lb-rank { font-size: 16px; font-weight: 700; color: var(--text); text-align: right; font-family: var(--font-num); }
.lb-up { color: var(--cyan); } .lb-down { color: var(--orange); } .lb-same { color: var(--muted); }

/* Segmented control: a small pill group like the tab bar. */
[data-testid="stButtonGroup"] button { border-radius: 999px; background: var(--field); border-color: var(--field-edge);
  color: var(--muted); transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease; }
[data-testid="stButtonGroup"] button:hover { color: var(--text); border-color: var(--field-edge); }
[data-testid="stButtonGroup"] button[kind*="Active"] { background: rgba(255, 255, 255, 0.10); color: var(--text);
  border-color: rgba(102, 244, 255, 0.55); }

/* Model comparison table: solid surface, plain headers, value plus a thin bar, best row outlined in cyan. */
.mt-wrap { background: var(--surface); border: 1px solid var(--glass-edge); border-radius: 12px; overflow: hidden; }
.mt { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-size: 14px; }
.mt th { color: var(--muted); font-size: 13px; font-weight: 400; text-align: right; vertical-align: bottom;
  padding: 10px 12px; line-height: 1.3; background: var(--surface-2); border-bottom: 1px solid var(--border); }
.mt th abbr { text-decoration: none; cursor: help; border-bottom: 1px dotted rgba(125, 153, 170, 0.6); }
.mt th small { display: block; font-size: 13px; color: var(--muted); }
.mt th:first-child, .mt td:first-child { text-align: left; }
.mt td { padding: 9px 12px; height: 36px; color: var(--text); border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  vertical-align: middle; }
.mt tr:last-child td { border-bottom-color: transparent; }
.mt-num { text-align: right; font-family: var(--font-num); font-variant-numeric: tabular-nums; }
.mt-bar { display: block; height: 3px; margin-top: 5px; border-radius: 2px; overflow: hidden;
  background: rgba(255, 255, 255, 0.08); }
.mt-bar span { display: block; height: 100%; border-radius: 2px; background: var(--cyan); transform-origin: left center;
  animation: dso-grow 500ms var(--ease-out) 150ms backwards; }
.mt-best td { background: rgba(102, 244, 255, 0.05); border-top: 1px solid var(--cyan); border-bottom: 1px solid var(--cyan); }
.mt-best td:first-child { border-left: 1px solid var(--cyan); border-radius: 10px 0 0 10px; }
.mt-best td:last-child { border-right: 1px solid var(--cyan); border-radius: 0 10px 10px 0; }
.mt-chip { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 999px; background: var(--cyan);
  color: var(--bg); font-size: 12px; font-weight: 700; vertical-align: 1px; }
.mt-summary { margin: 10px 2px 0; color: var(--text); font-size: 15px; }

/* Association rules: plain-English chips, outcome pill, lift and confidence bars. Solid surface, no blur. */
.rv-wrap { background: var(--surface); border: 1px solid var(--glass-edge); border-radius: 12px; overflow: hidden; }
.rv-row { display: grid; grid-template-columns: minmax(0, 1fr) 158px; gap: 16px; padding: 14px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.rv-row:last-child { border-bottom: none; }
.rv-sel { background: rgba(102, 244, 255, 0.06); box-shadow: inset 3px 0 0 var(--cyan); }
.rv-rule { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.chip { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 999px; font-size: 13px;
  line-height: 1.35; border: 1px solid transparent; white-space: normal; }
.chip-risk { background: rgba(255, 192, 103, 0.14); border-color: rgba(255, 192, 103, 0.35); color: var(--orange); }
.chip-good { background: rgba(102, 244, 255, 0.12); border-color: rgba(102, 244, 255, 0.32); color: var(--cyan); }
.chip-info { background: rgba(125, 153, 170, 0.16); border-color: rgba(125, 153, 170, 0.35); color: var(--text); }
.rv-plus { color: var(--muted); font-size: 13px; }
.rv-arrow { color: var(--muted); font-size: 16px; margin: 0 2px; }
.rv-out { display: inline-flex; padding: 3px 11px; border-radius: 999px; font-size: 13px; font-weight: 700; }
.rv-out-filled { background: var(--orange); color: var(--bg); border: 1px solid var(--orange); }
.rv-out-outline { border: 1px solid var(--orange); color: var(--orange); }
.rv-sentence { margin: 9px 0 0; color: var(--text); font-size: 14px; line-height: 1.45; }
.rv-stats { display: flex; flex-direction: column; gap: 8px; }
.rv-big { font-family: var(--font-num); font-size: 26px; font-weight: 600; color: var(--text); line-height: 1;
  font-variant-numeric: tabular-nums; }
.rv-cap { color: var(--muted); font-size: 13px; }
.rv-line { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.rv-num { font-family: var(--font-num); font-variant-numeric: tabular-nums; color: var(--text); font-size: 14px; }
.rv-bar { display: block; height: 4px; margin-top: 4px; border-radius: 2px; overflow: hidden;
  background: rgba(255, 255, 255, 0.08); }
.rv-bar span { display: block; height: 100%; border-radius: 2px; background: var(--cyan); transform-origin: left center;
  animation: dso-grow 500ms var(--ease-out) 150ms backwards; }
.rv-small { color: var(--muted); font-size: 13px; }
.rv-legend { display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 2px 0 10px; color: var(--muted); font-size: 13px; }
.rv-legend b { color: var(--text); font-weight: 600; }
@media (prefers-reduced-motion: reduce) { .rv-bar span { animation: none !important; } }
.lg { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 2px 0 8px; font-size: 13px; color: var(--text); }
.lg span { display: inline-flex; align-items: center; gap: 8px; }
.lg i { display: inline-block; width: 22px; height: 4px; border-radius: 2px; }
.lg em { font-style: normal; color: var(--muted); }
</style>
"""


@st.cache_data(show_spinner=False)
def _background_css() -> str:
    """If app/assets/bg.jpg exists, use it behind a 70% charcoal overlay. Otherwise the CSS background stays."""
    image = ASSETS / "bg.jpg"
    if not image.exists():
        return ""
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    return ("<style>[data-testid=\"stApp\"]::before { background: "
            "linear-gradient(rgba(18, 22, 25, 0.70), rgba(18, 22, 25, 0.70)), "
            f"url(\"data:image/jpeg;base64,{encoded}\") center / cover no-repeat; }}</style>")


def apply_style() -> None:
    st.html(STYLE + _background_css())


def _initials(name: str) -> str:
    words = [w for w in str(name).replace("LLC", "").split() if w]
    digits = "".join(ch for ch in str(name) if ch.isdigit())
    return (words[0][0] + digits[-2:]) if digits else "".join(w[0] for w in words[:2]).upper()


def progress_rows(rows: list[dict], tone: str) -> None:
    """Rows with a badge, a name, a gradient progress bar and a value. tone is 'warm' or 'cool'.

    Each row needs name, fill (0 to 1), value (the bold text) and suffix (the grey text).
    """
    parts = []
    for i, row in enumerate(rows):
        color = BADGE_COLORS[i % len(BADGE_COLORS)]
        width = max(0.0, min(1.0, float(row["fill"]))) * 100
        parts.append(
            f'<div class="ov-row"><div class="ov-badge" style="background:{color}">'
            f'{html.escape(_initials(row["name"]))}</div>'
            f'<div><div class="ov-name">{html.escape(str(row["name"]))}</div>'
            f'<div class="ov-track"><div class="ov-fill" style="width:{width:.0f}%"></div></div></div>'
            f'<div class="ov-val">{html.escape(row["value"])} <span>{html.escape(row["suffix"])}</span></div></div>')
    st.html(f'<div class="ov-{tone}">{"".join(parts)}</div>')


def leaderboard_rows(rows: list[dict]) -> None:
    """Rows with an avatar, a name and detail, a rank and a rank-change arrow."""
    parts = []
    for i, row in enumerate(rows):
        change = int(row["change"])
        arrow = ('<span class="lb-up" title="Up since the previous period">&#9650;</span>' if change > 0 else
                 '<span class="lb-down" title="Down since the previous period">&#9660;</span>' if change < 0 else
                 '<span class="lb-same" title="No change">&#9679;</span>')
        parts.append(
            f'<div class="lb-row"><div class="lb-avatar" style="background:{BADGE_COLORS[i % len(BADGE_COLORS)]}">'
            f'{html.escape(_initials(row["name"]))}</div>'
            f'<div><div class="lb-name">{html.escape(str(row["name"]))}</div>'
            f'<div class="lb-detail">{html.escape(row["detail"])}</div></div>'
            f'<div class="lb-rank">{int(row["rank"])}</div><div>{arrow}</div></div>')
    st.html("".join(parts))


# Model comparison table ---------------------------------------------------------------------------------------

_THRESHOLD_VIEWS = {"Tuned threshold": "Tuned", "Standard 0.5": "0.5"}


def _model_columns(columns, caught: str, noun: str, adj: str) -> dict:
    """Plain header, second header line and help text for each metric column that exists."""
    both_auc = "validation_auc" in columns and "roc_auc" in columns
    spec = {
        "validation_auc": ("AUC, validation", "months" if both_auc else "(AUC)",
                           "How well the model ranks invoices from safe to risky on the validation months, the "
                           "last three training months used to pick the model. 0.5 is a coin toss and 1 is perfect."),
        "roc_auc": ("AUC, test" if both_auc else "Ranking quality", "months" if both_auc else "(AUC)",
                    "How well the model ranks invoices from safe to risky on the unseen test months. "
                    "0.5 is a coin toss and 1 is perfect."),
        "recall": (caught, "(recall)", f"Share of {noun} in the test months that the model flagged."),
        "precision": ("Flags that were right", "(precision)", f"Share of flagged invoices that were truly {adj}."),
        "f1": ("Balance", "(F1)", "One score that balances recall and precision. Higher is better."),
        "accuracy": ("Overall correct", "(accuracy)", "Share of all test invoices the model got right."),
        "threshold": ("Flags at", "(threshold)", "The model flags an invoice when its probability is at least this."),
    }
    out = {c: spec[c] for c in spec if c in columns}
    for c in columns:  # never drop a column that exists
        if c not in out and c not in ("model", "threshold_type"):
            out[c] = (str(c).replace("_", " ").capitalize(), "", "")
    return out


def _metric_cell(value, bar: bool) -> str:
    if pd.isna(value):
        return '<td class="mt-num">n/a</td>'
    if not isinstance(value, (int, float)):
        return f'<td>{html.escape(str(value))}</td>'
    text = html.escape(f"{float(value):.3f}" if bar else f"{float(value):.2f}")
    if not bar:
        return f'<td class="mt-num">{text}</td>'
    width = max(0.0, min(1.0, float(value))) * 100
    return (f'<td class="mt-num">{text}<span class="mt-bar" aria-hidden="true">'
            f'<span style="width:{width:.1f}%"></span></span></td>')


@st.fragment
def model_table(metrics: pd.DataFrame, best_name: str, key: str, caught: str = "Late invoices caught",
                noun: str = "late invoices", adj: str = "late") -> None:
    """One row per model with a threshold switch, plain headers, inline bars and the best model outlined.

    Only filters and formats the rows it is given. The best model comes from the results, not from this table.
    """
    view = st.segmented_control("Threshold", list(_THRESHOLD_VIEWS), default="Tuned threshold", required=True,
                                key=f"{key}_threshold_view", label_visibility="collapsed")
    kind = _THRESHOLD_VIEWS.get(view or "Tuned threshold", "Tuned")
    rows = metrics
    if "threshold_type" in metrics.columns:
        rows = metrics[metrics["threshold_type"].astype(str) == kind]
    columns = _model_columns(list(metrics.columns), caught, noun, adj)

    head = ['<th style="width:24%">Model</th>']
    for main, sub, tip in columns.values():
        label = f'<abbr title="{html.escape(tip)}">{html.escape(main)}</abbr>' if tip else html.escape(main)
        head.append(f'<th>{label}<small>{html.escape(sub)}</small></th>')
    body = []
    for _, row in rows.iterrows():
        name = str(row.get("model", ""))
        best = name == best_name
        chip = '<span class="mt-chip">Best</span>' if best else ""
        cells = [f'<td>{html.escape(name)}{chip}</td>']
        cells += [_metric_cell(row[c], c != "threshold") for c in columns]
        body.append(f'<tr class="{"mt-best" if best else ""}">{"".join(cells)}</tr>')
    st.html(f'<div class="mt-wrap"><table class="mt"><thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')

    best_rows = rows[rows["model"] == best_name] if "model" in rows.columns else rows.iloc[0:0]
    if not best_rows.empty:
        best_row = best_rows.iloc[0]
        auc_col = "validation_auc" if "validation_auc" in best_row else "roc_auc"
        where = "tuned" if kind == "Tuned" else "standard 0.5"
        sentence = f"{best_name} ranks best (AUC {best_row[auc_col]:.3f})."
        if "recall" in best_row and "precision" in best_row:
            sentence += (f" At the {where} threshold it catches {best_row['recall']:.0%} of {noun}, and "
                         f"{best_row['precision']:.0%} of its flags are truly {adj}.")
        st.html(f'<p class="mt-summary">{html.escape(sentence)}</p>')


# Column settings for st.dataframe -----------------------------------------------------------------------------

def col_text(label: str, help: str | None = None, width: int = 140):
    return st.column_config.TextColumn(label, help=help, width=width)


def col_number(label: str, help: str, fmt: str = "%.3f", width: int = 110):
    return st.column_config.NumberColumn(label, help=help, format=fmt, width=width)


def col_date(label: str, help: str | None = None, fmt: str = "D MMM YYYY", width: int = 110):
    return st.column_config.DateColumn(label, help=help, format=fmt, width=width)


def col_datetime(label: str, help: str | None = None, width: int = 150):
    return st.column_config.DatetimeColumn(label, help=help, format="D MMM YYYY, HH:mm", width=width)


def col_money(label: str, help: str, width: int = 130):
    """AED amounts with thousands separators. The label should say AED."""
    return st.column_config.NumberColumn(label, help=help, format="localized", width=width)


def col_share(label: str, help: str, width: int = 130):
    """A 0 to 1 share as a cyan bar with a whole percent. table() shows it on a 0 to 100 scale."""
    return st.column_config.ProgressColumn(label, help=help, format="%.0f%%", min_value=0.0, max_value=100.0,
                                           color=T.CYAN, width=width)


def _is_share(config) -> bool:
    return isinstance(config, dict) and config.get("type_config", {}).get("type") == "progress"


def table(df, column_config: dict, height="auto", hide: tuple = (), row_height: int = 36) -> None:
    """Every plain table: no index, same row height, stretched to the container so nothing is clipped.

    Share columns are multiplied by 100 in a display copy only, so they read as whole percents. The data
    passed in, and every download, keep the original 0 to 1 values.
    """
    shares = [c for c, cfg in column_config.items() if _is_share(cfg)]
    money = [c for c, cfg in column_config.items()
             if isinstance(cfg, dict) and cfg.get("type_config", {}).get("format") == "localized"]
    if (shares or money) and isinstance(df, pd.DataFrame):
        df = df.copy()
        df[shares] = df[shares] * 100
        df[money] = df[money].round(0)  # whole dirhams in the display copy only
    order = [c for c in df.columns if c not in hide] if hide and isinstance(df, pd.DataFrame) else None
    st.dataframe(df, hide_index=True, width="stretch", column_config=column_config, row_height=row_height,
                 height=height, column_order=order)


def chip_style(df: pd.DataFrame, column: str, mask, formats: dict | None = None):
    """Styler that paints the given column as an orange chip on the rows in mask, for a warning row."""
    style = f"background-color: {T.ORANGE}; color: {T.BG}; font-weight: 600"
    styler = df.style.apply(lambda col: [style if flag else "" for flag in mask] if col.name == column
                            else [""] * len(col), axis=0)
    return styler.format(formats) if formats else styler


# Association rules and reason pairs ---------------------------------------------------------------------------

RULES_LEGEND = ('<div class="rv-legend"><span><b>Lift</b> how many times more likely the outcome is than normal'
                '</span><span><b>Confidence</b> share of matching invoices that end in the outcome</span>'
                '<span><b>Support</b> share of all paid invoices that match the rule</span></div>')


def _chip(label: str, tone: str) -> str:
    return f'<span class="chip chip-{tone}">{html.escape(label)}</span>'


def _bar(share: float) -> str:
    width = max(0.0, min(1.0, float(share))) * 100
    return f'<span class="rv-bar" aria-hidden="true"><span style="width:{width:.1f}%"></span></span>'


def rules_view(frame: pd.DataFrame, selected=frozenset()) -> None:
    """Rule rows in plain English. frame is core.viz.rules_frame output with a rule_id column."""
    from core import viz
    if frame.empty:
        st.html('<div class="rv-wrap"><div class="rv-row"><span class="rv-small">No rules match these settings. '
                'Lower the minimum lift or pick another outcome.</span></div></div>')
        return
    top_lift = float(frame["lift"].max()) or 1.0
    rows = []
    for _, r in frame.iterrows():
        chips = '<span class="rv-plus">+</span>'.join(_chip(*viz.item_info(item)[:2]) for item in r["items"])
        outcome = viz.OUTCOMES.get(r["then"], dict(label=r["then"], style="outline"))
        pill = f'<span class="rv-out rv-out-{outcome["style"]}">{html.escape(outcome["label"])}</span>'
        stats = (f'<div><span class="rv-big">{r["lift"]:.1f}x</span>'
                 f'<div class="rv-cap">more likely than normal</div>{_bar(r["lift"] / top_lift)}</div>'
                 f'<div><div class="rv-line"><span class="rv-cap">Confidence</span>'
                 f'<span class="rv-num">{r["confidence"]:.1%}</span></div>{_bar(r["confidence"])}</div>'
                 f'<div class="rv-small">{r["support"]:.1%} of invoices, {int(r["invoices"]):,} invoices</div>')
        cls = "rv-row rv-sel" if r["rule_id"] in selected else "rv-row"
        rows.append(f'<div class="{cls}"><div><div class="rv-rule">{chips}<span class="rv-arrow">&#8594;</span>'
                    f'{pill}</div><p class="rv-sentence">{html.escape(r["sentence"])}</p></div>'
                    f'<div class="rv-stats">{stats}</div></div>')
    st.html(f'<div class="rv-wrap">{"".join(rows)}</div>')


def pairs_view(pairs: pd.DataFrame) -> None:
    """Dispute reasons that appear together, as chips, with how often against chance."""
    from core import viz
    if pairs.empty:
        st.html('<div class="rv-wrap"><div class="rv-row"><span class="rv-small">No two reasons appear together '
                'often enough to pass the minimum support.</span></div></div>')
        return
    rows = []
    for _, r in pairs.iterrows():
        a = _chip(viz.REASON_LABELS.get(r["reason_a"], r["reason_a"]), "risk")
        b = _chip(viz.REASON_LABELS.get(r["reason_b"], r["reason_b"]), "risk")
        word = "less often than chance" if r["lift"] < 1 else "more often than chance"
        rows.append(f'<div class="rv-row"><div><div class="rv-rule">{a}<span class="rv-plus">with</span>{b}</div>'
                    f'<p class="rv-sentence">Together on {int(r["invoices"]):,} disputed invoices, '
                    f'{r["support"]:.1%} of all disputes.</p></div>'
                    f'<div class="rv-stats"><div><span class="rv-big">{r["lift"]:.2f}x</span>'
                    f'<div class="rv-cap">{word}</div></div></div></div>')
    st.html(f'<div class="rv-wrap">{"".join(rows)}</div>')



def legend_html(colors: dict, counts: dict | None = None, unit: str = "") -> str:
    """A small HTML legend: a coloured line, the name and an optional count, for charts without their own legend."""
    items = []
    for name, color in colors.items():
        count = f" <em>{int(counts[name])} {html.escape(unit)}</em>" if counts and name in counts else ""
        items.append(f'<span><i style="background:{html.escape(color)}"></i>{html.escape(str(name))}{count}</span>')
    return f'<div class="lg">{"".join(items)}</div>'

SYNTHETIC_NOTICE = ("All data in this platform is synthetic. It was generated to match published UAE ranges, "
                    "so the patterns show how the pipeline works, not facts about a real company.")


@st.cache_data(show_spinner="Loading and cleaning the data...")
def get_data() -> dict:
    return data.load_all()


@st.cache_resource(show_spinner="Loading the models. The first run trains them, which takes about a minute...")
def get_models() -> dict:
    from core import models
    return models.load_or_train(get_data()["inv"])


@st.cache_data(show_spinner=False)
def get_emails():
    return data.load_emails()


@st.cache_resource(show_spinner="Training the triage classifiers...")
def get_triage() -> dict:
    from core import triage
    return triage.train_triage(get_emails())


def config() -> dict:
    return load_config()


def explainer(text: str) -> None:
    """The rationale box every page carries."""
    with st.expander("Why this technique"):
        st.markdown(text)


def chart(fig, key: str, where=None, config: dict | None = None, **kwargs):
    """Every Plotly chart: Streamlit's own chart theme off so dso_dark applies, the shared mode bar, a stable key."""
    from core import charts
    target = where if where is not None else st
    return target.plotly_chart(fig, theme=None, config=config or charts.PLOT_CONFIG, width="stretch", key=key,
                               **kwargs)


def download_csv(df: pd.DataFrame, filename: str, label: str = "Download as CSV") -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=filename, mime="text/csv",
                       key=f"download_{filename}")


def page_header(title: str, purpose: str) -> None:
    apply_style()
    st.title(title)
    st.caption(purpose)
