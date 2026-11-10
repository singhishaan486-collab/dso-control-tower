"""Plotly figures shared by the pages. Colours come from the design tokens in app/theme.py.

Orange means risk, late, slow or action needed. Cyan is the main data and means healthy or neutral. Slate is the
secondary series. Series are also told apart by marker symbol, line dash or bar pattern, never by colour alone.
"""
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from app import theme as T

BRAND = T.CYAN
ACCENT = T.CYAN
SECOND = T.SLATE
ORANGE = T.ORANGE
MUTED = T.MUTED
RAMP = T.RAMP
SERIES = [T.CYAN, T.ORANGE, T.SLATE, T.LIGHT]
SYMBOLS = ["circle", "square", "diamond", "triangle-up"]
DASHES = ["solid", "dash", "dot", "dashdot"]
PATTERNS = ["", "/", ".", "x"]
SEQUENTIAL = [[0, T.SURFACE_2], [1, T.CYAN]]
TEMPLATE = "dso_dark"

_AXIS = dict(gridcolor=T.GRID, zerolinecolor=T.GRID, linecolor=T.BORDER, tickcolor=T.BORDER,
             tickfont=dict(color=T.MUTED, size=13, family=T.FONT_UI), title=dict(font=dict(color=T.TEXT, size=13)))
_LAYOUT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
               font=dict(family=T.FONT_UI, color=T.TEXT, size=13),
               hoverlabel=dict(bgcolor=T.SURFACE_2, bordercolor=T.BORDER,
                               font=dict(color=T.TEXT, family=T.FONT_UI, size=13)),
               legend=dict(font=dict(color=T.TEXT, size=13), bgcolor="rgba(0,0,0,0)"))
pio.templates[TEMPLATE] = go.layout.Template(layout=dict(
    **_LAYOUT, colorway=SERIES, xaxis=_AXIS, yaxis=_AXIS,
    annotationdefaults=dict(font=dict(color=T.MUTED, size=13))))
pio.templates.default = TEMPLATE

# Mode bar: zoom, reset and PNG download stay. Selection tools are added back only on charts that use them.
_REMOVE = ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines", "hoverClosestCartesian",
           "hoverCompareCartesian", "zoomIn2d", "zoomOut2d"]
PLOT_CONFIG = {"displaylogo": False, "scrollZoom": False, "modeBarButtonsToRemove": _REMOVE,
               "toImageButtonOptions": {"format": "png", "scale": 2}}
SELECT_CONFIG = {**PLOT_CONFIG, "modeBarButtonsToRemove": [b for b in _REMOVE if b not in ("lasso2d", "select2d")]}


def _theme(fig: go.Figure) -> go.Figure:
    """Apply the dark template and set the key colours directly, so Streamlit's chart theme cannot override them."""
    fig.update_layout(template=TEMPLATE, **_LAYOUT)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


def _layout(fig: go.Figure, height: int = 360, x_title: str | None = None, y_title: str | None = None,
            legend: bool = False) -> go.Figure:
    _theme(fig)
    fig.update_layout(height=height, margin=dict(l=18, r=22, t=36 if legend else 18, b=14), showlegend=legend,
                      barcornerradius=4, legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, title_text=""))
    fig.update_xaxes(title_text=x_title, automargin=True)
    fig.update_yaxes(title_text=y_title, automargin=True)
    return fig


def activity_bars(df: pd.DataFrame, value_title: str, value_format: str = ",.0f") -> go.Figure:
    """Monthly bars standing in front of a light full-height track."""
    top = max(df["value"].max(), 1) * 1.08
    fig = go.Figure()
    fig.add_bar(x=df["month"], y=[top] * len(df), marker_color=T.SURFACE_2, width=0.42, hoverinfo="skip",
                showlegend=False)
    fig.add_bar(x=df["month"], y=df["value"], marker_color=BRAND, width=0.42, customdata=df[["period"]],
                hovertemplate=f"%{{customdata[0]}}<br>{value_title}: %{{y:{value_format}}}<extra></extra>",
                showlegend=False)
    _theme(fig)
    fig.update_layout(barmode="overlay", bargap=0.5, barcornerradius=6, height=300, margin=dict(l=30, r=8, t=8, b=28))
    fig.update_xaxes(showgrid=False, showline=False)
    fig.update_yaxes(showgrid=False, showline=False, range=[0, top], tickformat="~s")
    return fig


def line(df: pd.DataFrame, x: str, y: str, y_title: str, y_format: str = ",.1f",
         range_tools: bool = False) -> go.Figure:
    """A monthly line. range_tools adds unified hover, a range slider and 6 month, 12 month and all buttons."""
    if range_tools:
        hover = f"{y_title}: %{{y:{y_format}}}<extra></extra>"
    else:
        hover = f"%{{x|%b %Y}}<br>{y_title}: %{{y:{y_format}}}<extra></extra>"
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines+markers", line=dict(color=ACCENT, width=2),
                               marker=dict(size=7), name=y_title, hovertemplate=hover))
    if not range_tools:
        return _layout(fig, y_title=y_title)
    _layout(fig, height=470, y_title=y_title)
    low, high = float(df[y].min()), float(df[y].max())
    pad = (high - low) * 0.15 or 1.0
    fig.update_yaxes(range=[low - pad, high + pad], fixedrange=True)
    fig.update_layout(hovermode="x unified", margin=dict(t=48, b=36))
    fig.update_xaxes(
        hoverformat="%b %Y", showspikes=True, spikecolor=T.BORDER, spikethickness=1,
        rangeslider=dict(visible=True, thickness=0.09, bgcolor=T.SURFACE, bordercolor=T.BORDER, borderwidth=1),
        rangeselector=dict(
            buttons=[dict(count=6, label="6 months", step="month", stepmode="backward"),
                     dict(count=12, label="12 months", step="month", stepmode="backward"),
                     dict(step="all", label="All")],
            bgcolor=T.SURFACE_2, activecolor="rgba(102, 244, 255, 0.28)", bordercolor=T.BORDER, borderwidth=1,
            font=dict(color=T.TEXT, size=13), x=0, y=1.08, yanchor="bottom"))
    return fig


def ranked_bars(df: pd.DataFrame, label: str, value: str, value_title: str, value_format: str = ",.1f",
                percent: bool = False, height: int | None = None, color: str = ACCENT) -> go.Figure:
    """Horizontal bars, largest on top, one colour."""
    data = df.sort_values(value)
    fmt = ".0%" if percent else value_format
    fig = go.Figure(go.Bar(x=data[value], y=data[label].astype(str), orientation="h", marker_color=color,
                           text=[format(v, fmt) for v in data[value]], textposition="outside", cliponaxis=False,
                           hovertemplate=f"%{{y}}<br>{value_title}: %{{x:{fmt}}}<extra></extra>"))
    fig.update_xaxes(tickformat=".0%" if percent else None)
    _layout(fig, height=height or max(260, 34 * len(data) + 60), x_title=value_title)
    fig.update_layout(margin_r=64)  # room for the value label on the longest bar
    return fig


def columns(df: pd.DataFrame, label: str, value: str, value_title: str, colors: list[str] | str = ACCENT,
            percent: bool = False, value_format: str = ",.0f") -> go.Figure:
    """Vertical bars in the order given, for ordered categories."""
    fmt = ".0%" if percent else value_format
    fig = go.Figure(go.Bar(x=df[label].astype(str), y=df[value], marker_color=colors, width=0.55,
                           text=[format(v, fmt) for v in df[value]], textposition="outside", cliponaxis=False,
                           hovertemplate=f"%{{x}}<br>{value_title}: %{{y:{fmt}}}<extra></extra>"))
    fig.update_yaxes(tickformat=".0%" if percent else None, rangemode="tozero")
    fig.update_xaxes(type="category")  # labels like "2026-06" would otherwise be read as dates, making hairline bars
    return _layout(fig, y_title=value_title)


def histogram(values: pd.Series, x_title: str, marker: float | None = None, marker_label: str = "",
              marginal_box: bool = False) -> go.Figure:
    """Histogram with an optional marker line. marginal_box adds a box plot on top that shares the x axis."""
    hist = go.Histogram(x=values, marker_color=ACCENT, nbinsx=40, name="Invoices",
                        hovertemplate=f"{x_title}: %{{x}}<br>Invoices: %{{y}}<extra></extra>")
    if not marginal_box:
        fig = go.Figure(hist)
        if marker is not None:
            fig.add_vline(x=marker, line=dict(color=MUTED, width=1.5),
                          annotation=dict(text=marker_label, xanchor="left"))
        fig.update_layout(bargap=0.05)
        return _layout(fig, x_title=x_title, y_title="Invoices")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.17, 0.83], vertical_spacing=0.03)
    fig.add_trace(go.Box(x=values, orientation="h", name="", boxmean=True, boxpoints="outliers",
                         marker=dict(color=T.SLATE, size=4), line=dict(color=T.SLATE, width=1.5),
                         fillcolor="rgba(125, 153, 170, 0.22)", hoverinfo="x"), row=1, col=1)
    fig.add_trace(hist, row=2, col=1)
    if marker is not None:
        fig.add_vline(x=marker, line=dict(color=MUTED, width=1.5), row=2, col=1,
                      annotation=dict(text=marker_label, xanchor="left"))
    fig.update_layout(bargap=0.05)
    _layout(fig, height=420, x_title=x_title, y_title="Invoices")
    fig.update_xaxes(title_text=None, row=1, col=1)
    fig.update_yaxes(title_text=None, showticklabels=False, showgrid=False, row=1, col=1)
    return fig


def simple_line(df: pd.DataFrame, x: str, y: str, x_title: str, y_title: str, mark_x=None) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines+markers", line=dict(color=ACCENT, width=2),
                               marker=dict(size=8), hovertemplate=f"{x_title} %{{x}}<br>{y_title}: %{{y:.3f}}"
                                                                  "<extra></extra>"))
    if mark_x is not None:
        fig.add_vline(x=mark_x, line=dict(color=MUTED, width=1.5), annotation=dict(text="Chosen", xanchor="left"))
    return _layout(fig, height=300, x_title=x_title, y_title=y_title)


def roc_lines(curves: dict, aucs: dict, positive: str, negative: str) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", name="Random guess", hoverinfo="skip",
                    line=dict(color=T.BORDER, width=1.5))
    for i, (name, (fpr, tpr)) in enumerate(curves.items()):
        fig.add_scatter(x=fpr, y=tpr, mode="lines", name=f"{name} (AUC {aucs[name]:.3f})",
                        line=dict(color=SERIES[i % len(SERIES)], width=2, dash=DASHES[i % len(DASHES)]),
                        hovertemplate=f"{name}<br>False alarms: %{{x:.0%}}<br>Caught: %{{y:.0%}}<extra></extra>")
    fig.update_xaxes(tickformat=".0%", range=[0, 1])
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
    return _layout(fig, height=420, x_title=f"Share of {negative} invoices flagged (false positive rate)",
                   y_title=f"Share of {positive} invoices caught (recall)", legend=True)


def confusion_heatmap(matrix, labels: list[str], normalise: bool) -> go.Figure:
    values = matrix / matrix.sum(axis=1, keepdims=True) if normalise else matrix
    text = [[f"{v:.0%}" if normalise else f"{int(v):,}" for v in row] for row in values]
    fig = go.Figure(go.Heatmap(z=values, x=[f"Predicted {l}" for l in labels], y=[f"Actual {l}" for l in labels],
                               colorscale=SEQUENTIAL, showscale=False, text=text, xgap=3, ygap=3,
                               hovertemplate="%{y}, %{x}: %{text}<extra></extra>"))
    # Cell labels are annotations so a bright cell gets dark text and a dark cell gets light text.
    top = float(values.max()) or 1.0
    for r, row in enumerate(values):
        for c, v in enumerate(row):
            fig.add_annotation(x=f"Predicted {labels[c]}", y=f"Actual {labels[r]}", text=text[r][c], showarrow=False,
                               font=dict(size=18, family=T.FONT_NUM, color=T.BG if v / top > 0.55 else T.TEXT))
    _layout(fig, height=320)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def predicted_vs_actual(actual, predicted, title: str) -> go.Figure:
    top = max(float(max(actual)), float(max(predicted)))
    fig = go.Figure()
    fig.add_scatter(x=[0, top], y=[0, top], mode="lines", name="Perfect forecast", hoverinfo="skip",
                    line=dict(color=MUTED, width=1.5, dash="dash"))
    fig.add_scatter(x=actual, y=predicted, mode="markers", name=title, marker=dict(color=ACCENT, size=7, opacity=0.6),
                    hovertemplate="Actual %{x:.0f} days<br>Predicted %{y:.0f} days<extra></extra>")
    return _layout(fig, height=420, x_title="Actual days to pay", y_title="Predicted days to pay", legend=True)


def _segment_color(segment: str) -> str:
    """Slow or dispute prone segments are a risk, so they are orange. Fast ones are cyan, the rest slate."""
    name = segment.lower()
    if "dispute" in name or "slow" in name:
        return T.ORANGE
    return T.CYAN if "fast" in name else T.SLATE


def segment_map(clients: pd.DataFrame, variance) -> go.Figure:
    fig = go.Figure()
    for i, (segment, part) in enumerate(clients.groupby("segment")):
        fig.add_scatter(x=part["pc1"], y=part["pc2"], mode="markers", name=segment,
                        marker=dict(color=_segment_color(segment), symbol=SYMBOLS[i % len(SYMBOLS)], size=12,
                                    line=dict(color=T.BG, width=1.5)),
                        customdata=part[["client_id", "mean_days_to_pay", "dispute_rate"]],
                        hovertemplate=f"{segment}<br>%{{customdata[0]}}<br>Days to pay %{{customdata[1]:.0f}}"
                                      "<br>Dispute rate %{customdata[2]:.0%}<extra></extra>")
    return _layout(fig, height=440, x_title=f"First pattern ({variance[0]:.0%} of variation)",
                   y_title=f"Second pattern ({variance[1]:.0%} of variation)", legend=True)


def grouped_bars(df: pd.DataFrame, label: str, series: str, value: str, value_title: str) -> go.Figure:
    """One bar per series inside each category. At most four series."""
    fig = go.Figure()
    for i, (name, part) in enumerate(df.groupby(series, sort=False)):
        fig.add_bar(x=part[label], y=part[value], name=name,
                    marker=dict(color=SERIES[i % len(SERIES)],
                                pattern=dict(shape=PATTERNS[i % len(PATTERNS)], fgcolor=T.BG, fgopacity=0.55, size=7)),
                    hovertemplate=f"{name}<br>%{{x}}: %{{y:.2f}}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.05)
    fig.update_yaxes(range=[0, 1.05])
    return _layout(fig, height=380, y_title=value_title, legend=True)


def xy_scatter(df: pd.DataFrame, x: str, y: str, label: str, x_title: str, y_title: str) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="markers", marker=dict(color=ACCENT, size=10, opacity=0.75,
                                                                             line=dict(color=T.BG, width=1)),
                               customdata=df[[label]],
                               hovertemplate=f"%{{customdata[0]}}<br>{x_title}: %{{x:.0%}}<br>{y_title}: %{{y:.1%}}"
                                             "<extra></extra>"))
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return _layout(fig, height=400, x_title=x_title, y_title=y_title)


def cash_waterfall(steps: pd.DataFrame) -> go.Figure:
    """Cash released by each lever. Bars below zero mean the model expects that lever to slow payment."""
    labels = list(steps["lever"]) + ["Total"]
    values = list(steps["cash_released_aed"]) + [steps["cash_released_aed"].sum()]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=["relative"] * len(steps) + ["total"],
        text=[f"AED {v:,.0f}" for v in values], textposition="outside", cliponaxis=False,
        increasing=dict(marker=dict(color=T.CYAN)), decreasing=dict(marker=dict(color=T.ORANGE)),
        totals=dict(marker=dict(color=T.SLATE)), connector=dict(line=dict(color=T.BORDER, width=1)),
        hovertemplate="%{x}<br>AED %{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=MUTED, width=1))
    return _layout(fig, height=420, y_title="Cash released (AED)")


def waterfall(stages: pd.DataFrame, title_total: str, y_max: float) -> go.Figure:
    """Days added at each stage, ending in the total days from month end to cash."""
    labels = list(stages["stage"]) + [title_total]
    values = list(stages["mean_days"]) + [stages["mean_days"].sum()]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=["relative"] * len(stages) + ["total"],
        text=[f"{v:.1f}" for v in values], textposition="outside", cliponaxis=False,
        increasing=dict(marker=dict(color=T.CYAN)), totals=dict(marker=dict(color=T.SLATE)),
        connector=dict(line=dict(color=T.BORDER, width=1)),
        hovertemplate="%{x}<br>%{y:.1f} days<extra></extra>"))
    fig.update_yaxes(range=[0, y_max])
    return _layout(fig, height=400, y_title="Days")


_RULE_MARKS = {"DISPUTE": ("circle", True), "LATE": ("diamond-open", False), "LATE_30+": ("square-open", False)}


def rules_scatter(frame: pd.DataFrame, x_max: float, y_min: float) -> go.Figure:
    """Each rule as a bubble: support across, confidence up, area by lift. frame is core.viz.rules_frame output
    with a rule_id column. Axis ranges and bubble scale are fixed by the caller so filtering does not jump."""
    from core.viz import OUTCOMES
    fig = go.Figure()
    sizeref = 2.0 * max(float(frame["lift"].max()) if len(frame) else 1.0, 1.0) / (30 ** 2)
    for then, part in frame.groupby("then", sort=False):
        symbol, filled = _RULE_MARKS.get(then, ("circle-open", False))
        info = OUTCOMES.get(then, dict(label=then, clause="have this outcome"))
        fig.add_scatter(
            x=part["support"], y=part["confidence"], mode="markers", name=info["label"],
            marker=dict(size=part["lift"], sizemode="area", sizeref=sizeref, sizemin=7, symbol=symbol,
                        color=T.ORANGE, opacity=0.9,
                        line=dict(color=T.BG if filled else T.ORANGE, width=1.5 if filled else 2.5)),
            customdata=list(zip(part["plain_if"], part["lift"], part["invoices"], part["rule_id"])),
            hovertemplate=(f"<b>%{{customdata[0]}}</b><br>Outcome: {info['label']}<br>"
                           "Matches %{x:.1%} of paid invoices (%{customdata[2]} invoices)<br>"
                           f"%{{y:.1%}} of them {info['clause']}<br>"
                           "%{customdata[1]:.1f}x more likely than normal<extra></extra>"))
    fig.update_xaxes(tickformat=".0%", range=[0, x_max])
    fig.update_yaxes(tickformat=".0%", range=[y_min, 1.0])
    _layout(fig, height=430, x_title="Support: share of paid invoices that match", y_title="Confidence", legend=True)
    fig.update_layout(dragmode="select", clickmode="event+select")
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def days_box(paid: pd.DataFrame, by: str, group_title: str, order: list, split: bool, violin: bool,
             y_max: float) -> go.Figure:
    """Days to pay per group as boxes or violins, mean shown, outliers as points. When split, not disputed is
    cyan circles and disputed is orange diamonds. The y range is fixed by the caller so toggles do not jump."""
    if split:
        parts = [(paid[paid["dispute_raised"] == 0], T.CYAN, "circle", "Not disputed"),
                 (paid[paid["dispute_raised"] == 1], T.ORANGE, "diamond", "Disputed")]
    else:
        parts = [(paid, T.CYAN, "circle", "All paid invoices")]
    fig = go.Figure()
    for part, color, symbol, name in parts:
        common = dict(x=part[by].astype(str), y=part["days_to_pay"], name=name, legendgroup=name,
                      marker=dict(color=color, symbol=symbol, size=6, opacity=0.8),
                      line=dict(color=color, width=1.5), fillcolor=_rgba(color, 0.18))
        if violin:
            fig.add_trace(go.Violin(**common, box_visible=True, meanline_visible=True, points="outliers",
                                    spanmode="hard", scalemode="width", hoveron="violins+points"))
        else:
            fig.add_trace(go.Box(**common, boxmean=True, boxpoints="outliers", hoveron="boxes+points"))
    fig.update_xaxes(categoryorder="array", categoryarray=[str(v) for v in order])
    fig.update_yaxes(range=[0, y_max])
    _layout(fig, height=430, x_title=group_title, y_title="Days to pay", legend=True)
    fig.update_layout(boxmode="group", violinmode="group", boxgroupgap=0.35, violingroupgap=0.35,
                      hovermode="closest")
    return fig


def receivables_tree(frame: pd.DataFrame, measure_title: str, icicle: bool) -> go.Figure:
    """Ownership, sector and client as a sunburst or icicle. Size is the chosen amount, colour is the share of
    open receivables that is overdue: slate when none is overdue, orange as the overdue share rises."""
    trace = go.Icicle if icicle else go.Sunburst
    if icicle:
        # An explicit root, so the first column is "All clients" rather than an unnamed block.
        top = frame[frame["level"] == 0]
        open_total, overdue_total = top["open_aed"].sum(), top["overdue_aed"].sum()
        root_row = dict(id="all", parent="", label="All clients", parent_label="the total", level=-1, client_name="",
                        invoiced_aed=top["invoiced_aed"].sum(), open_aed=open_total, overdue_aed=overdue_total,
                        value=top["value"].sum(), overdue_share=overdue_total / open_total if open_total else 0.0)
        frame = pd.concat([pd.DataFrame([root_row]),
                           frame.assign(parent=frame["parent"].where(frame["level"] != 0, "all"),
                                        parent_label=frame["parent_label"].where(frame["level"] != 0,
                                                                                 "all clients"))],
                          ignore_index=True)
    hover = (f"<b>%{{label}}</b> %{{customdata[2]}}<br>{measure_title}: AED %{{value:,.0f}}<br>"
             "%{customdata[0]} of %{customdata[1]}<br>Overdue share of open receivables: %{color:.0%}"
             "<extra></extra>")
    totals = frame.groupby("parent")["value"].sum()
    share_of_parent = [f"{v / totals[p]:.0%}" if totals.get(p) else "0%"
                       for v, p in zip(frame["value"], frame["parent"])]
    extra = {"tiling": dict(orientation="h")} if icicle else {"insidetextorientation": "horizontal"}
    fig = go.Figure(trace(
        ids=frame["id"], labels=frame["label"], parents=frame["parent"], values=frame["value"],
        branchvalues="total", maxdepth=3 if icicle else 2,
        customdata=list(zip(share_of_parent, frame["parent_label"], frame["client_name"])),
        marker=dict(colors=frame["overdue_share"], colorscale=[[0, "#3A4852"], [0.5, "#9C9A86"], [1, T.ORANGE]],
                    cmin=0, cmax=1, line=dict(color=T.BG, width=1.5),
                    colorbar=dict(title=dict(text="Overdue share of open", side="right", font=dict(color=T.TEXT, size=13)),
                                  tickformat=".0%", thickness=10, len=0.7, outlinewidth=0,
                                  tickfont=dict(color=T.MUTED, size=13))),
        hovertemplate=hover, **extra,
        insidetextfont=dict(family=T.FONT_UI, size=13,
                            color=[T.BG if v > 0.45 else T.TEXT for v in frame["overdue_share"]])))
    _theme(fig)
    fig.update_layout(height=520, margin=dict(l=16, r=90, t=8, b=8))
    return fig


# Explorer -------------------------------------------------------------------------------------------------------

# Ownership keeps one colour and one symbol everywhere. Government clients are the slowest payers in this data,
# so they carry orange; the others use cyan, slate and the light neutral. Symbols separate them without colour.
OWNERSHIP_STYLE = {"Private SME": (T.CYAN, "circle"), "Private large": (T.SLATE, "square"),
                   "Semi-government": (T.LIGHT, "triangle-up"), "Government": (T.ORANGE, "diamond")}
_OWNER_ORDER = ["Private SME", "Private large", "Semi-government", "Government"]


def _owner_style(owner: str) -> tuple[str, str]:
    return OWNERSHIP_STYLE.get(owner, (T.MUTED, "circle-open"))


def _bubble_ref(max_value: float, max_px: int = 38) -> float:
    return 2.0 * max(float(max_value), 1.0) / (max_px ** 2)


def client_scatter(summary: pd.DataFrame, y_max: float, size_max: float) -> go.Figure:
    """Each client as a bubble: late rate across, average days to pay up, area by invoiced AED. Colour and
    symbol by ownership. Ranges and bubble scale come from the caller so they never jump."""
    fig = go.Figure()
    for owner in _OWNER_ORDER + sorted(set(summary["client_ownership"]) - set(_OWNER_ORDER)):
        part = summary[summary["client_ownership"] == owner]
        if part.empty:
            continue
        color, symbol = _owner_style(owner)
        fig.add_scatter(
            x=part["late_rate"], y=part["mean_days_to_pay"], mode="markers", name=owner,
            marker=dict(size=part["invoiced_aed"], sizemode="area", sizeref=_bubble_ref(size_max), sizemin=5,
                        color=color, symbol=symbol, opacity=0.85, line=dict(color=T.BG, width=1)),
            customdata=list(zip(part["client_id"], part["client_name"], part["invoices"], part["dispute_rate"],
                                part["invoiced_aed"])),
            hovertemplate=("<b>%{customdata[0]}</b> %{customdata[1]}<br>" + owner + "<br>"
                           "Paid late: %{x:.0%} of %{customdata[2]} invoices<br>Average days to pay: %{y:.0f} days"
                           "<br>Disputed: %{customdata[3]:.0%}<br>Invoiced: AED %{customdata[4]:,.0f}"
                           "<extra></extra>"))
    fig.update_xaxes(tickformat=".0%", range=[-0.03, 1.03])
    fig.update_yaxes(range=[0, y_max])
    _layout(fig, height=460, x_title="Share of invoices paid late", y_title="Average days to pay", legend=True)
    fig.update_layout(dragmode="select", clickmode="event+select")
    return fig


def animated_clients(monthly: pd.DataFrame, y_max: float) -> go.Figure:
    """Clients moving over service months on a rolling window. One trace per ownership in every frame, ids per
    client so bubbles glide between months. Axes and bubble scale are fixed across all frames."""
    months = sorted(monthly["month"].unique())
    owners = [o for o in _OWNER_ORDER if o in set(monthly["client_ownership"])]
    sizeref = _bubble_ref(monthly["invoiced_aed"].max(), 34)

    def traces(month):
        out = []
        frame = monthly[monthly["month"] == month]
        for owner in owners:
            part = frame[frame["client_ownership"] == owner]
            color, symbol = _owner_style(owner)
            out.append(go.Scatter(
                x=part["late_rate"], y=part["mean_days_to_pay"], ids=part["client_id"], mode="markers", name=owner,
                marker=dict(size=part["invoiced_aed"], sizemode="area", sizeref=sizeref, sizemin=4, color=color,
                            symbol=symbol, opacity=0.85, line=dict(color=T.BG, width=1)),
                customdata=list(zip(part["client_id"], part["invoices"], part["invoiced_aed"])),
                hovertemplate=("<b>%{customdata[0]}</b> " + owner + "<br>Three months to " + month + "<br>"
                               "Paid late: %{x:.0%} of %{customdata[1]} invoices<br>Average days to pay: "
                               "%{y:.0f} days<br>Invoiced: AED %{customdata[2]:,.0f}<extra></extra>")))
        return out

    fig = go.Figure(data=traces(months[0]), frames=[go.Frame(data=traces(m), name=m) for m in months])
    play = dict(label="Play", method="animate",
                args=[None, dict(frame=dict(duration=700, redraw=False), transition=dict(duration=300,
                                 easing="cubic-in-out"), fromcurrent=True, mode="immediate")])
    pause = dict(label="Pause", method="animate",
                 args=[[None], dict(frame=dict(duration=0, redraw=False), transition=dict(duration=0),
                                    mode="immediate")])
    steps = [dict(label=m, method="animate",
                  args=[[m], dict(frame=dict(duration=300, redraw=False), transition=dict(duration=300),
                                  mode="immediate")]) for m in months]
    fig.update_xaxes(tickformat=".0%", range=[-0.03, 1.03])
    fig.update_yaxes(range=[0, y_max])
    _layout(fig, height=520, x_title="Share of invoices paid late (last 3 months)",
            y_title="Average days to pay (last 3 months)", legend=True)
    fig.update_layout(
        margin=dict(b=110),
        updatemenus=[dict(type="buttons", direction="left", showactive=False, x=0, y=-0.2, xanchor="left",
                          yanchor="top", pad=dict(r=8, t=0), bgcolor=T.SURFACE_2, bordercolor=T.BORDER,
                          font=dict(color=T.TEXT, size=13), buttons=[play, pause])],
        sliders=[dict(active=0, steps=steps, x=0.16, len=0.84, y=-0.2, yanchor="top", pad=dict(t=0, b=0),
                      bgcolor=T.SURFACE_2, bordercolor=T.BORDER, activebgcolor=T.CYAN, tickcolor=T.BORDER,
                      font=dict(color=T.MUTED, size=12),
                      currentvalue=dict(prefix="Window ending ", font=dict(color=T.TEXT, size=13)),
                      transition=dict(duration=300))])
    return fig


def outcome_ternary(mix: pd.DataFrame, color_by: str, segment_of: dict | None = None) -> go.Figure:
    """Each client's invoices split three ways that add to 100%: on time, late and disputed. Size by invoiced AED.
    color_by is "Ownership" or "Segment"."""
    fig = go.Figure()
    sizeref = _bubble_ref(mix["invoiced_aed"].max(), 34)
    if color_by == "Segment" and segment_of is not None:
        groups = mix.assign(group=mix["client_id"].map(segment_of).fillna("No segment"))
        names = sorted(groups["group"].unique())
        styles = {g: (_segment_color(g), SYMBOLS[i % len(SYMBOLS)]) for i, g in enumerate(names)}
    else:
        groups = mix.assign(group=mix["client_ownership"])
        names = [o for o in _OWNER_ORDER if o in set(groups["group"])]
        styles = {g: _owner_style(g) for g in names}
    for name in names:
        part = groups[groups["group"] == name]
        color, symbol = styles[name]
        fig.add_trace(go.Scatterternary(
            a=part["on_time_share"], b=part["late_share"], c=part["disputed_share"], mode="markers", name=name,
            marker=dict(size=part["invoiced_aed"], sizemode="area", sizeref=sizeref, sizemin=5, color=color,
                        symbol=symbol, opacity=0.85, line=dict(color=T.BG, width=1)),
            customdata=list(zip(part["client_id"], part["client_name"], part["invoices"], part["invoiced_aed"])),
            hovertemplate=("<b>%{customdata[0]}</b> %{customdata[1]}<br>" + name + "<br>"
                           "On time, no dispute: %{a:.0%}<br>Late, no dispute: %{b:.0%}<br>Disputed: %{c:.0%}<br>"
                           "%{customdata[2]} invoices, AED %{customdata[3]:,.0f}<extra></extra>")))
    axis = dict(tickformat=".0%", tickfont=dict(color=T.MUTED, size=12), linecolor=T.BORDER, gridcolor=T.GRID,
                min=0)
    _theme(fig)
    fig.update_layout(
        height=540, margin=dict(l=80, r=80, t=56, b=70), showlegend=True,
        legend=dict(orientation="v", x=0, y=1, xanchor="left", yanchor="top", title_text=""),
        ternary=dict(bgcolor="rgba(0,0,0,0)", sum=1,
                     aaxis=dict(title=dict(text="On time, no dispute", font=dict(color=T.CYAN, size=13)), **axis),
                     baxis=dict(title=dict(text="Late, no dispute", font=dict(color=T.TEXT, size=13)), **axis),
                     caxis=dict(title=dict(text="Disputed", font=dict(color=T.ORANGE, size=13)), **axis)))
    return fig


# Predictive: segments on parallel axes ---------------------------------------------------------------------------

# Parallel axes cannot use marker shapes, so each segment needs its own colour here. Dispute prone keeps orange,
# slow payers take the light neutral so the two risks stay apart, fast and clean is cyan, the rest slate.
def segment_line_color(segment: str) -> str:
    name = segment.lower()
    if "dispute" in name:
        return T.ORANGE
    if "slow" in name:
        return T.LIGHT
    return T.CYAN if "fast" in name else T.SLATE


_PARCOORD_AXES = [("mean_days_to_pay", "Average days to pay", ".0f"), ("late_rate", "Paid late", ".0%"),
                  ("dispute_rate", "Disputed", ".0%"), ("revenue_share", "Share of revenue", ".1%"),
                  ("payment_terms_days", "Payment terms (days)", ".0f"), ("invoices", "Invoices", ".0f")]


def segment_parcoords(clients: pd.DataFrame) -> go.Figure:
    """One line per client across six measures, coloured by segment with a stepped (discrete) colour scale."""
    names = sorted(clients["segment"].unique())
    code = clients["segment"].map({n: i for i, n in enumerate(names)})
    n = max(len(names), 1)
    scale = []
    for i, name in enumerate(names):
        color = segment_line_color(name)
        scale += [[i / n, color], [(i + 1) / n, color]]
    dims = []
    for column, label, fmt in _PARCOORD_AXES:
        if column in clients:
            values = clients[column]
            dims.append(dict(values=values, label=label, tickformat=fmt,
                             range=[float(values.min()), float(values.max())]))
    fig = go.Figure(go.Parcoords(
        line=dict(color=code, colorscale=scale, cmin=-0.5, cmax=n - 0.5, showscale=False),
        dimensions=dims,
        labelfont=dict(color=T.TEXT, size=13, family=T.FONT_UI, shadow="none"),
        tickfont=dict(color=T.MUTED, size=12, family=T.FONT_NUM, shadow="none"),
        rangefont=dict(color=T.MUTED, size=11, family=T.FONT_NUM, shadow="none"),
        unselected=dict(line=dict(color=T.BORDER, opacity=0.35))))
    _theme(fig)
    fig.update_layout(height=440, margin=dict(l=60, r=60, t=60, b=24))
    return fig


# Prescriptive: two levers together ------------------------------------------------------------------------------

_DIVERGING = [[0, T.CYAN], [0.5, "#3A4248"], [1, T.ORANGE]]


def lever_surface(grid: pd.DataFrame, lever_a: str, lever_b: str, three_d: bool) -> go.Figure:
    """DSO change for every pair of adoption shares. Cyan is DSO falling, orange is DSO rising, centred on zero.
    The flat view is a heatmap with contour lines and the value written in each cell."""
    table = grid.pivot(index="adoption_a", columns="adoption_b", values="dso_change_days").sort_index()
    x = [v * 100 for v in table.columns]
    y = [v * 100 for v in table.index]
    z = table.values
    reach = float(max(abs(z.min()), abs(z.max()), 1e-6))
    hover = (f"{lever_a}: %{{y:.0f}}% of invoices<br>{lever_b}: %{{x:.0f}}% of invoices<br>"
             "DSO change: %{z:+.2f} days<extra></extra>")
    colorbar = dict(title=dict(text="DSO change (days)", side="right", font=dict(color=T.TEXT, size=13)),
                    tickfont=dict(color=T.MUTED, size=12), tickformat="+.2f", thickness=10, outlinewidth=0, len=0.8)
    if three_d:
        fig = go.Figure(go.Surface(x=x, y=y, z=z, colorscale=_DIVERGING, cmin=-reach, cmax=reach, cmid=0,
                                   colorbar=colorbar, hovertemplate=hover,
                                   contours=dict(z=dict(show=True, usecolormap=False, color=T.BORDER, width=1))))
        axis = dict(backgroundcolor="rgba(0,0,0,0)", gridcolor=T.GRID, zerolinecolor=T.BORDER, showbackground=True,
                    color=T.MUTED, tickfont=dict(color=T.MUTED, size=11), title=dict(font=dict(color=T.TEXT, size=12)))
        _theme(fig)
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), scene=dict(
            xaxis=dict(title=dict(text=f"{lever_b} (%)"), **{k: v for k, v in axis.items() if k != "title"}),
            yaxis=dict(title=dict(text=f"{lever_a} (%)"), **{k: v for k, v in axis.items() if k != "title"}),
            zaxis=dict(title=dict(text="DSO change (days)"), **{k: v for k, v in axis.items() if k != "title"}),
            camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9))))
        return fig
    fig = go.Figure(go.Contour(
        x=x, y=y, z=z, colorscale=_DIVERGING, zmin=-reach, zmax=reach, zmid=0, colorbar=colorbar,
        contours=dict(coloring="heatmap", showlabels=True, labelfont=dict(color=T.TEXT, size=11)),
        line=dict(color="rgba(18, 22, 25, 0.55)", width=1), hovertemplate=hover))
    labels = [[f"{v:+.2f}" for v in row] for row in z]
    # Labels on the outer rows and columns are nudged inward so they sit fully on the coloured field.
    def place(xv, yv):
        vertical = "top" if yv == min(y) else "bottom" if yv == max(y) else "middle"
        side = "right" if xv == min(x) else "left" if xv == max(x) else "center"
        return f"{vertical} {side}"
    fig.add_scatter(x=[xv for _ in y for xv in x], y=[yv for yv in y for _ in x], mode="text",
                    textposition=[place(xv, yv) for yv in y for xv in x],
                    text=[t for row in labels for t in row], hoverinfo="skip", showlegend=False, cliponaxis=False,
                    textfont=dict(family=T.FONT_NUM, size=13,
                                  color=[T.BG if abs(v) > reach * 0.55 else T.TEXT for row in z for v in row]))
    fig.update_xaxes(range=[-6, 106], tickvals=x, ticksuffix="%", showgrid=False)
    fig.update_yaxes(range=[-6, 106], tickvals=y, ticksuffix="%", showgrid=False)
    _layout(fig, height=460, x_title=f"{lever_b}: share of invoices", y_title=f"{lever_a}: share of invoices")
    return fig


def dso_candles(ohlc: pd.DataFrame) -> go.Figure:
    """Monthly candles of daily DSO. Rising DSO is bad, so a month that ends higher is orange and a month that ends
    lower is cyan, the reverse of a price chart. A range slider sits underneath."""
    fig = go.Figure(go.Candlestick(
        x=ohlc["month"], open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"], name="DSO",
        increasing=dict(line=dict(color=T.ORANGE, width=1.5), fillcolor=T.ORANGE),
        decreasing=dict(line=dict(color=T.CYAN, width=1.5), fillcolor=T.CYAN),
        customdata=ohlc[["swing"]],
        hovertemplate=("%{x|%B %Y}<br>First day: %{open:.1f} days<br>Highest: %{high:.1f} days<br>"
                       "Lowest: %{low:.1f} days<br>Last day: %{close:.1f} days<br>"
                       "Swing inside the month: %{customdata[0]:.1f} days<extra></extra>")))
    low, high = float(ohlc["low"].min()), float(ohlc["high"].max())
    pad = (high - low) * 0.1 or 1.0
    _layout(fig, height=470, y_title="DSO (days)")
    fig.update_yaxes(range=[low - pad, high + pad], fixedrange=True)
    fig.update_layout(margin=dict(t=18, b=36), hovermode="x")
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.09, bgcolor=T.SURFACE, bordercolor=T.BORDER,
                                      borderwidth=1), hoverformat="%B %Y")
    return fig
