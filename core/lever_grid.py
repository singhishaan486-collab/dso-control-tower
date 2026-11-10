"""Works out the two-lever grid in its own Python process, so the 25 simulator runs can use several CPU cores
without touching the Streamlit server. Usage:

    python -m core.lever_grid "<lever A>" "<lever B>" <signoff days> <output csv>

Every cell is core.prescriptive.simulate, unchanged. Runs locally, no network.
"""
import sys

from core import data, models, viz

if __name__ == "__main__":
    lever_a, lever_b, days, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    inv = data.load_all()["inv"]
    results = models.load_or_train(inv)
    grid = viz.lever_grid(inv, results["dispute_raised"]["model"], results["days_to_pay"]["model"], lever_a,
                          lever_b, days, parallel=True)
    grid.to_csv(out, index=False)
