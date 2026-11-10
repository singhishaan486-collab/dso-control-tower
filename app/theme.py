"""Design tokens for the dark charcoal theme. Imported by app/components.py and core/charts.py.

Colour meaning is fixed: orange is risk, late, slow, overdue or action needed. Cyan is the main data colour and
means healthy or neutral. Slate is the secondary series. Two series are never told apart by colour alone.
"""

BG = "#121619"
SURFACE = "#1A1F23"
SURFACE_2 = "#232A30"
BORDER = "#333C44"
TEXT = "#ECF0F2"
MUTED = "#7D99AA"
CYAN = "#66F4FF"
ORANGE = "#FFC067"
SLATE = "#7D99AA"
LIGHT = TEXT  # light neutral, used as the fourth series

# Grid lines: faint white, so they read on glass and stay behind the data.
GRID = "rgba(255, 255, 255, 0.08)"

# System fonts only. Nothing is downloaded, so the app works offline.
FONT_UI = "Segoe UI, system-ui, -apple-system, sans-serif"
FONT_NUM = "Consolas, ui-monospace, Menlo, monospace"

# Badges and avatars cycle through the palette only.
BADGE_CYCLE = [CYAN, SLATE, ORANGE, LIGHT]

# Ordered ramp from slate (low risk) to orange (high risk), for aging buckets and variance bands.
# Every step clears 5:1 against the surface.
RAMP = ["#7D99AA", "#97A19D", "#B1A98F", "#CBB082", "#E5B874", "#FFC067"]
