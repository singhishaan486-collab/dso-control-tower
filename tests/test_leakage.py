import pandas as pd
import pytest

from core import data
from core.features import CATEGORICAL, FEATURES, LEAKY, NUMERIC, get_xy, time_split


@pytest.fixture(scope="module")
def inv():
    return data.load_all()["inv"]


def test_feature_lists_do_not_intersect_leaky():
    assert not set(CATEGORICAL + NUMERIC) & set(LEAKY)


def test_days_to_signoff_is_not_a_feature():
    assert "days_to_signoff" not in FEATURES


def test_get_xy_returns_only_allowed_features(inv):
    train, _ = time_split(inv)
    x, _ = get_xy(train, "paid_late")
    assert list(x.columns) == FEATURES
    assert not set(x.columns) & set(LEAKY)


def test_saved_models_use_only_invoice_day_columns(inv):
    from core.models import load_or_train

    results = load_or_train(inv)
    for target in ("paid_late", "dispute_raised", "days_to_pay"):
        used = set(results[target]["model"].named_steps["prep"].feature_names_in_)
        assert used == set(FEATURES), target
        assert not used & set(LEAKY), target


def test_train_months_come_before_test_months(inv):
    train, test = time_split(inv)
    assert len(train) and len(test)
    train_max = pd.PeriodIndex(train["service_month"], freq="M").max()
    test_min = pd.PeriodIndex(test["service_month"], freq="M").min()
    assert train_max < test_min
