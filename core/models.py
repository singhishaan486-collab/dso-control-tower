"""Predictive models: late payment, disputes, days to pay, client segments and the leakage demo.

Run `python -m core.models` to retrain everything and save it to models/.
"""
import hashlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, fbeta_score, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score, recall_score, roc_auc_score, roc_curve,
                             silhouette_score)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from core.config import load_config
from core.features import FEATURES, NUMERIC, add_invoice_month, build_preprocessor, get_xy, time_split

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
RESULTS_FILE = MODELS_DIR / "results.joblib"
MODEL_VERSION = "phase2-v2"
RS = load_config()["random_state"]

CLASSIFIERS = {
    "KNN": lambda: KNeighborsClassifier(n_neighbors=15, weights="distance"),
    "Decision tree": lambda: DecisionTreeClassifier(max_depth=6, min_samples_leaf=20, class_weight="balanced",
                                                    random_state=RS),
    "Random forest": lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=5,
                                                    class_weight="balanced_subsample", random_state=RS, n_jobs=-1),
    "Gradient boosting": lambda: HistGradientBoostingClassifier(learning_rate=0.1, max_iter=200, random_state=RS),
}
REGRESSORS = {
    "Linear regression": lambda: LinearRegression(),
    "Random forest": lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=RS, n_jobs=-1),
    "Gradient boosting": lambda: HistGradientBoostingRegressor(random_state=RS),
}
LEAK_DEMO_COLUMNS = ["dispute_raised", "stage_ack_days", "was_chased", "short_paid_aed"]
CLUSTER_FEATURES = {
    "mean_days_to_pay": "Average days to pay", "mean_days_overdue": "Average days overdue",
    "late_rate": "Share paid late", "dispute_rate": "Dispute rate",
    "mean_resolution_days": "Average dispute resolution days", "payment_terms_days": "Payment terms",
    "revenue_share": "Share of revenue", "unapproved_ot_rate": "Share with unapproved OT",
    "unsigned_rate": "Share invoiced unsigned",
}


def _pipeline(estimator, numeric: list[str] | None = None) -> Pipeline:
    return Pipeline([("prep", build_preprocessor(numeric)), ("model", estimator)])


def _validation_split(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold back the last three training months to choose the threshold and the best model."""
    period = pd.PeriodIndex(train["service_month"], freq="M")
    cut = period.max() - 2
    return train[period < cut], train[period >= cut]


def _beta() -> float:
    return float(load_config()["classification"]["threshold_metric"].lstrip("fF"))


def best_threshold(y, proba) -> float:
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    scores = [fbeta_score(y, proba >= t, beta=_beta(), zero_division=0) for t in grid]
    return float(grid[int(np.argmax(scores))])


def classification_metrics(y, proba, threshold: float) -> dict:
    predicted = proba >= threshold
    return dict(accuracy=accuracy_score(y, predicted), precision=precision_score(y, predicted, zero_division=0),
                recall=recall_score(y, predicted, zero_division=0), f1=f1_score(y, predicted, zero_division=0),
                roc_auc=roc_auc_score(y, proba))


def confusion(y, proba, threshold: float) -> np.ndarray:
    """Rows are the actual class (0, 1), columns the predicted class."""
    return confusion_matrix(y, proba >= threshold, labels=[0, 1])


def _importance(model, x, y, scoring: str) -> pd.DataFrame:
    result = permutation_importance(model, x, y, scoring=scoring, n_repeats=10, random_state=RS, n_jobs=-1)
    table = pd.DataFrame({"feature": x.columns, "importance": result.importances_mean,
                          "std": result.importances_std})
    return table.sort_values("importance", ascending=False).head(15).reset_index(drop=True)


def train_classifiers(inv: pd.DataFrame, target: str) -> dict:
    """Fit all four models, choose each threshold and the best model on the last three training months."""
    train, test = time_split(inv)
    fit_part, val = _validation_split(train)
    x_test, y_test = get_xy(test, target)
    rows, models, probas, curves = [], {}, {}, {}
    for name, make in CLASSIFIERS.items():
        tuning = _pipeline(make()).fit(*get_xy(fit_part, target))
        x_val, y_val = get_xy(val, target)
        val_proba = tuning.predict_proba(x_val)[:, 1]
        threshold = best_threshold(y_val, val_proba)
        model = _pipeline(make()).fit(*get_xy(train, target))
        proba = model.predict_proba(x_test)[:, 1]
        for kind, cut in (("0.5", 0.5), ("Tuned", threshold)):
            rows.append(dict(model=name, threshold_type=kind, threshold=cut,
                             validation_auc=roc_auc_score(y_val, val_proba), **classification_metrics(y_test, proba, cut)))
        fpr, tpr, _ = roc_curve(y_test, proba)
        models[name], probas[name], curves[name] = model, proba, (fpr, tpr)
    metrics = pd.DataFrame(rows)
    best = metrics.loc[metrics["validation_auc"].idxmax(), "model"]
    majority = int(y_test.mode().iat[0])
    baseline = dict(accuracy=float((y_test == majority).mean()), recall=float(majority == 1), majority_class=majority)
    return dict(target=target, metrics=metrics, best=best, model=models[best],
                threshold=float(metrics.query("model == @best and threshold_type == 'Tuned'")["threshold"].iat[0]),
                y_test=y_test.to_numpy(), probas=probas, roc=curves, baseline=baseline,
                importance=_importance(models[best], x_test, y_test, "roc_auc"),
                rows=dict(train=len(train), test=len(test), validation=len(val)))


def _baseline_days(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """The client's own past average; for new clients, terms plus the usual days past terms."""
    extra = (train["days_to_pay"] - train["payment_terms_days"]).mean()
    return test["prev_avg_days_to_pay"].fillna(test["payment_terms_days"] + extra).to_numpy()


def _regression_metrics(y, predicted) -> dict:
    return dict(mae=mean_absolute_error(y, predicted), rmse=float(np.sqrt(mean_squared_error(y, predicted))),
                r2=r2_score(y, predicted))


def train_regressors(inv: pd.DataFrame) -> dict:
    """Predict days to pay and compare against the naive baseline."""
    train, test = time_split(inv)
    fit_part, val = _validation_split(train)
    x_test, y_test = get_xy(test, "days_to_pay")
    rows = [dict(model="Baseline (client's past average)",
                 validation_mae=mean_absolute_error(val["days_to_pay"], _baseline_days(fit_part, val)),
                 **_regression_metrics(y_test, _baseline_days(train, test)))]
    predictions, models = {"Baseline (client's past average)": _baseline_days(train, test)}, {}
    for name, make in REGRESSORS.items():
        tuning = _pipeline(make()).fit(*get_xy(fit_part, "days_to_pay"))
        x_val, y_val = get_xy(val, "days_to_pay")
        val_mae = mean_absolute_error(y_val, tuning.predict(x_val))
        model = _pipeline(make()).fit(*get_xy(train, "days_to_pay"))
        predictions[name], models[name] = model.predict(x_test), model
        rows.append(dict(model=name, validation_mae=val_mae, **_regression_metrics(y_test, predictions[name])))
    metrics = pd.DataFrame(rows)
    learned = metrics[metrics["model"].isin(REGRESSORS)]
    best = learned.loc[learned["validation_mae"].idxmin(), "model"]
    baseline_wins = bool(metrics.loc[0, "validation_mae"] <= learned["validation_mae"].min())
    return dict(metrics=metrics, best=best, baseline_wins=baseline_wins, model=models[best],
                y_test=y_test.to_numpy(), predictions=predictions,
                test_ids=test["invoice_id"].to_numpy(), importance=_importance(models[best], x_test, y_test,
                                                                               "neg_mean_absolute_error"))


def client_features(inv: pd.DataFrame) -> pd.DataFrame:
    """One row per client from full paid history. Describes clients; never used as a model feature."""
    paid = inv[inv["invoice_status"] == "Paid"].copy()
    paid["unapproved_ot"] = (paid["ot_preapproved"] == 0).astype(int)
    paid["unsigned"] = (paid["timesheet_status"] == "Unsigned").astype(int)
    table = paid.groupby("client_id").agg(
        mean_days_to_pay=("days_to_pay", "mean"), mean_days_overdue=("days_overdue", "mean"),
        late_rate=("paid_late", "mean"), dispute_rate=("dispute_raised", "mean"),
        mean_resolution_days=("stage_dispute_resolution_days", "mean"),
        payment_terms_days=("payment_terms_days", "first"), revenue=("invoice_amount_aed", "sum"),
        unapproved_ot_rate=("unapproved_ot", "mean"), unsigned_rate=("unsigned", "mean"),
        client_ownership=("client_ownership", "first"), sector=("sector", "first"), invoices=("invoice_id", "size"))
    table["mean_resolution_days"] = table["mean_resolution_days"].fillna(0)
    table["revenue_share"] = table["revenue"] / table["revenue"].sum()
    return table


def _name_segments(centroids: pd.DataFrame) -> dict:
    """Name each cluster from its centroid, measured in standard deviations from the average client."""
    names = {}
    for cluster, row in centroids.iterrows():
        if row["dispute_rate"] > 0.5:
            name = "Dispute prone"
        elif row["mean_days_to_pay"] < -0.3:
            name = "Fast and clean"
        elif row["mean_days_to_pay"] > 0.3:
            name = "Slow but clean"
        else:
            name = "Average"
        taken = sum(n.split(" (")[0] == name for n in names.values())
        names[cluster] = name if not taken else f"{name} ({taken + 1})"
    return names


def segment_clients(inv: pd.DataFrame) -> dict:
    """K-means on standardised client behaviour, k chosen by the best silhouette score."""
    table = client_features(inv)
    scaled = StandardScaler().fit_transform(table[list(CLUSTER_FEATURES)])
    search = []
    for k in range(2, 7):
        km = KMeans(n_clusters=k, n_init=load_config()["clustering"]["n_init"], random_state=RS).fit(scaled)
        search.append(dict(k=k, inertia=km.inertia_, silhouette=silhouette_score(scaled, km.labels_)))
    search = pd.DataFrame(search)
    best_k = int(search.loc[search["silhouette"].idxmax(), "k"])
    km = KMeans(n_clusters=best_k, n_init=load_config()["clustering"]["n_init"], random_state=RS).fit(scaled)
    centroids = pd.DataFrame(km.cluster_centers_, columns=list(CLUSTER_FEATURES))
    names = _name_segments(centroids)
    table["segment"] = pd.Series(km.labels_, index=table.index).map(names)
    xy = PCA(n_components=2, random_state=RS).fit(scaled)
    table[["pc1", "pc2"]] = xy.transform(scaled)
    profile = table.groupby("segment").agg(clients=("invoices", "size"), **{
        col: (col, "mean") for col in CLUSTER_FEATURES}).reset_index()
    return dict(search=search, best_k=best_k, clients=table.reset_index(), profile=profile,
                pca_variance=xy.explained_variance_ratio_)


def _with_leaks(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["was_chased"] = out["first_followup_date"].notna().astype(int)
    return out


def leakage_demo(inv: pd.DataFrame) -> dict:
    """The same random forest with and without columns only known after the invoice. For teaching only."""
    train, test = (_with_leaks(part) for part in time_split(inv))
    leaky_numeric = NUMERIC + LEAK_DEMO_COLUMNS
    y_train, y_test = train["paid_late"].astype(int), test["paid_late"].astype(int)
    rows, importance = [], None
    for label, numeric, columns in (("Clean (invoice-day features only)", NUMERIC, FEATURES),
                                    ("Leaky (adds post-invoice columns)", leaky_numeric,
                                     FEATURES + LEAK_DEMO_COLUMNS)):
        model = _pipeline(CLASSIFIERS["Random forest"](), numeric).fit(
            add_invoice_month(train)[columns], y_train)
        x_test = add_invoice_month(test)[columns]
        proba = model.predict_proba(x_test)[:, 1]
        rows.append(dict(model=label, **classification_metrics(y_test, proba, 0.5)))
        if label.startswith("Leaky"):
            importance = _importance(model, x_test, y_test, "roc_auc").head(10)
    return dict(metrics=pd.DataFrame(rows), importance=importance, leak_columns=LEAK_DEMO_COLUMNS)


def data_fingerprint() -> str:
    raw = (ROOT / "data" / "invoices.csv").read_bytes()
    return hashlib.sha256(raw + MODEL_VERSION.encode()).hexdigest()[:16]


def train_all(inv: pd.DataFrame) -> dict:
    """Train every model once and save the models and their results to models/."""
    results = dict(fingerprint=data_fingerprint(), paid_late=train_classifiers(inv, "paid_late"),
                   dispute_raised=train_classifiers(inv, "dispute_raised"), days_to_pay=train_regressors(inv),
                   segments=segment_clients(inv), leakage=leakage_demo(inv))
    MODELS_DIR.mkdir(exist_ok=True)
    for target in ("paid_late", "dispute_raised"):
        part = results[target]
        joblib.dump(dict(model=part["model"], threshold=part["threshold"], name=part["best"],
                         metrics=part["metrics"]), MODELS_DIR / f"clf_{target}.joblib")
    joblib.dump(dict(model=results["days_to_pay"]["model"], name=results["days_to_pay"]["best"]),
                MODELS_DIR / "reg_days_to_pay.joblib")
    joblib.dump(results, RESULTS_FILE)
    return results


def load_or_train(inv: pd.DataFrame) -> dict:
    """Reuse saved results when they match the current data and code version, otherwise retrain."""
    if RESULTS_FILE.exists():
        results = joblib.load(RESULTS_FILE)
        if results.get("fingerprint") == data_fingerprint():
            return results
    return train_all(inv)


if __name__ == "__main__":
    from core import data

    out = train_all(data.load_all()["inv"])
    print("saved to", MODELS_DIR)
