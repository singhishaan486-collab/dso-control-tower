# UI notes

Visual and interaction notes for the DSO Control Tower. Nothing here changes a model, a metric, a threshold or a generator. Every number on screen comes from the same `core/` functions as before.

## Versions

- Streamlit 1.67.0, Plotly 7.1.0, Python 3.12.2, pandas 3.1.1, scikit-learn 1.9.1 (all in `.venv`).
- Every theme option used in `.streamlit/config.toml` is supported by this Streamlit, so no upgrade was needed. `on_select` for chart selections is supported too.

## Theme

- Design tokens live once in `app/theme.py` and are imported by `app/components.py` and `core/charts.py`. Charcoal base: bg `#121619`, surface `#1A1F23`, surface 2 `#232A30`, border `#333C44`, text `#ECF0F2`, muted and slate `#7D99AA`, cyan `#66F4FF`, orange `#FFC067`.
- Colour meaning: orange is risk, late, slow, overdue or action needed. Cyan is the main data and healthy or neutral. Slate is the secondary series. Two series are never told apart by colour alone: marker symbols, line dashes, bar patterns and direct labels do that too.
- Fonts are the system stack only (Segoe UI and system-ui, Consolas for numbers). Nothing is downloaded; the app runs offline.
- Background: no `app/assets/bg.jpg`, so it is CSS only: soft cyan, orange and slate fields with faint diagonal lines, fixed behind the page. If a `bg.jpg` is added later it is used automatically behind a 70% charcoal overlay.
- Glass: cards (`st-key-card*`), stand-alone metrics and the sidebar use the full recipe with a 16px blur. Stand-alone charts, expanders and the tab bar use the glass fill without blur, so no page has more than 12 blurred elements (Overview 12, Descriptive 10, Automation 5 on its visible tab, the rest fewer). Nothing inside a card or expander has its own glass. Tables are a solid surface.
- Without blur support, or with "reduce transparency" on, glass becomes a solid surface.
- Contrast: muted text stays above 4.5:1 inside glass (about 4.8:1 at worst). On the open page the colour fields are kept to 8% or less where text sits, so captions stay above 4.5:1 too.
- Plotly: one template, `dso_dark`, in `core/charts.py`. Every chart is drawn through `ui.chart()`, which passes `theme=None` (so Streamlit does not override the template), the shared `PLOT_CONFIG` (no logo, no scroll zoom, zoom, reset and PNG download kept; lasso and box select only on charts that use selection) and a stable key.

## What animates

All motion is CSS or Plotly, uses only opacity and transform, and is under 600 ms. CSS motion is switched off under `prefers-reduced-motion`.

- Cards, stand-alone metrics and stand-alone charts fade in and rise 12px on page load (350 ms, staggered by 60 ms per column). Widget changes do not replay it, because Streamlit keeps the same elements (checked on Overview).
- Hover on a card, metric or chart: lift 2px and a cyan border (150 ms), only on devices with a fine pointer.
- Buttons press to 97% scale; tabs, buttons, selects and the sidebar links fade colour in 150 ms.
- Bars grow from the left on load: payer progress bars on Overview, the inline bars in the model table, and the lift and confidence bars in the rule list.
- Explorer, "How clients moved over time": Plotly frames with Play, Pause and a month slider, 300 ms transitions between months. It only plays when Play is pressed. Plotly's own animation does not read the reduced-motion setting.

## Fragments

These blocks rerun on their own when one of their widgets changes, so the rest of the page is not redrawn:

- Predictive: `model_table` (the Tuned threshold / Standard 0.5 switch), on the late payment and dispute tabs.
- Diagnostic: `rules_block` (outcome switch, sort, minimum lift, Show more, rule scatter selection).
- Descriptive: `days_spread` (box or violin plot) and `receivables_tree` (sunburst or icicle).
- Prescriptive: `two_levers` (lever pickers, view switch, Work out this pair).
- Explorer: `linked_views` (client selection and everything it filters) and `outcome_triangle` (colour switch).

Heavy work is cached: association rules, daily DSO, Explorer preparation, days-to-pay data and the receivables tree with `st.cache_data`, and the two-lever grid with `st.cache_data(persist="disk")`.

## Tables

Custom HTML helpers (all values passed through `html.escape`):

- `model_table` in `app/components.py`: the model comparison on Predictive, late payment and dispute tabs. One row per model, a threshold switch that only filters existing rows, plain two-line headers with help text, a thin cyan bar per score, the best model (taken from the results, not recomputed) outlined with a Best chip, and one sentence generated from the live numbers.
- `rules_view`: the association rules on Diagnostic, with plain-English chips, an outcome pill, lift and confidence bars and one sentence per rule.
- `pairs_view`: the dispute reason pairs on Diagnostic, with the same chips.

Everything else uses `st.dataframe` through `ui.table()` with `column_config`: plain sentence-case headers, help text on metric columns, 0 to 1 shares as cyan progress bars with whole percents, AED with thousands separators, ratios to 3 decimals, fixed widths, no index, 36px rows.

- Overview: process stages.
- Data and cleaning: missing values, sector variants, cleaning log, data dictionary.
- Descriptive: DSO data table, breakdown by segment, aging, cash gap by client.
- Diagnostic: dispute reasons, what the rule items mean, dispute rate by method and band.
- Predictive: regression metrics (baseline row as an orange chip when the baseline wins), segment profile, clients in a segment, leakage comparison.
- Prescriptive: policy by segment, what each lever changes, simulator steps.
- Automation: invoice QA results, QA findings, attendance chain, daily seals, edited record, WPS by month, WPS by client, WPS findings.
- Dispute triage: model comparison, finding the invoice, per-reason metrics, evidence, decisions this session.
- Explorer: selected clients.

The display copy is the only thing scaled or rounded. Every download button still passes the original, unrenamed DataFrame.

No column used in these tables has a cut-off in `config/config.yaml`, so no table colours values orange.

## Charts added in this round

| Page | Chart | What it is for |
|---|---|---|
| Diagnostic | Rule scatter (support, confidence, lift) | See every association rule at once and select bubbles to highlight their rules in the list. |
| Descriptive | DSO by month with range buttons and slider | Zoom into recent months without losing the history. |
| Descriptive | DSO candles (daily DSO by month) | Show how far DSO swings inside a month, so a month-end figure is read with its timing in mind. |
| Descriptive | Days to pay box or violin, optional dispute split | Show the spread of payment times per group, not just the average. |
| Descriptive | Receivables sunburst or icicle | Show where open, overdue or invoiced money sits by ownership, sector and client, coloured by the overdue share. |
| Descriptive | Box on top of the cash gap histogram | Summarise the same spread (median, quartiles, outliers) in one line. |
| Explorer | Client scatter with linked charts and table | Select a group of clients and see their days to pay, dispute reasons and sector mix. |
| Explorer | Animated client bubbles | Watch clients move over rolling three-month windows. |
| Explorer | Outcome ternary | Show each client's split of on time, late and disputed invoices in one point. |
| Predictive | Segment parallel axes | Show every client on six measures to see which ones separate the segments. |
| Prescriptive | Two-lever map (flat or 3D) | See whether two process changes add up, overlap or work against each other. |

No map charts or anything that needs network files are used.

## Skipped, limited or changed from the request

- Numbers in dataframe cells cannot use Consolas: `st.dataframe` draws cells on a canvas that CSS cannot reach. Header colour is set to muted through config, but header size and weight are Streamlit's.
- Dataframe cells do not wrap in Streamlit 1.67. Long text (policy, cleaning reasons, findings) is cut with an ellipsis on screen; clicking a cell shows all of it, and the downloads have everything.
- Two tables still scroll sideways at 1440 wide: the raw data preview on Data and cleaning (about 70 raw columns, kept raw on purpose because it shows the file as it arrived) and the invoice QA results on Automation (twelve columns need about 1,040px; the headers were shortened, the data was not). Both fit at 1920 except the raw preview. The service month column is hidden in the QA table on screen because it is the same for every row; the caption names it and the download keeps it.
- Two half-width tables moved under their charts so they fit: dispute reasons on Diagnostic and QA findings on Automation.
- HTML table headers are 13px, not 12px, so they follow the rule that muted text is 13px or larger.
- Metric values are 36px with 20px card side padding, so "60/60" and "1,428" fit in the small Overview cards.
- Chart cards have no padding: Streamlit sizes the chart to the card's full box, so padding pushed charts past the card edge. Spacing comes from the figure margins.
- A chart selection cannot be cleared from a button directly. Explorer's "Clear selection" redraws the chart with a fresh key; on Diagnostic the caption says to double-click the chart.
- Two-lever map: one simulator run takes about 2 seconds, so the 25-cell grid cannot meet 300 ms. It is worked out only when "Work out this pair" is pressed, in a separate local Python process (`core/lever_grid.py`) that uses several cores (about 25 to 30 seconds on a 16-core laptop, about 50 seconds if it has to fall back to one cell at a time). Each pair is then stored in Streamlit's disk cache in the user folder and opens in a few seconds after that, even after a restart. Running the cells in parallel inside the Streamlit server was tried and removed: on Windows each worker re-ran the app script.
- Explorer animation: clients bill about once a month, so a three-month window usually holds three invoices and the late rate can only be 0%, 33%, 67% or 100%. Bubbles line up in four columns; the caption says why.
- Ownership colours: four ownership types need all four palette colours. Government, the slowest-paying group in this data, is orange; Private SME cyan, Private large slate, Semi-government the light neutral. Shapes separate them as well.
- Segment colours: on the PCA map both risk segments are orange and differ by shape. Parallel axes cannot use shapes, so there slow but clean is the light neutral.
- Badges cycle cyan, slate, orange and light neutral as asked, so some badges in the fastest-payer list are orange.
- Opening a deep link such as `/Diagnostic` as the very first request after the server starts shows Streamlit's automatic page list instead of the app navigation, because the folder is called `pages`. Opening the app from its root works normally. Not changed, since renaming the folder would touch the tests and the project layout.

## Verification

- `pytest -q`: 15 passed (leakage tests plus every page, including Explorer).
- Every page opened at 1440x900, every tab on Predictive and Automation included: no exceptions, no white boxes, no chart text outside its card, and no page-level sideways scroll. Every table fits except the two listed above.
- Selections checked: four rules box-selected on the Diagnostic scatter moved to the top of the list and matched the data; eleven clients selected on the Explorer scatter filtered the histogram, reasons, sector mix and table, and Clear selection brought back all 60.
- Generated sentences checked against the data: model table (95% caught and 70% of flags right for the tuned random forest), rules (normal rate 24.4%), days to pay medians, sunburst shares, DSO candles (each month's last day equals the month-end DSO on the line chart).
- No em dashes or en dashes in any file under `app/`, `core/` or `.streamlit/`.
