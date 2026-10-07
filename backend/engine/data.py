"""Dataset loading, preprocessing, and display metadata."""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
try:
    import pandas as pd
except ImportError:
    pd = None
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score


# Labels and units shown in the web interface.
FEATURE_META = {
    "pima": {
        "Pregnancies": ("Pregnancies", "count", "Number of times pregnant"),
        "Glucose": ("Glucose", "mg/dL", "Plasma glucose after a 2-hour glucose-tolerance test"),
        "BloodPressure": ("Blood pressure", "mm Hg", "Diastolic blood pressure"),
        "SkinThickness": ("Skin fold", "mm", "Triceps skin-fold thickness"),
        "Insulin": ("Insulin", "µU/mL", "2-hour serum insulin"),
        "BMI": ("BMI", "kg/m²", "Body-mass index"),
        "DiabetesPedigreeFunction": ("Family-history score", "score",
                                     "Diabetes likelihood from family history"),
        "Age": ("Age", "years", "Age"),
    },
    "heloc": {
        "ExternalRiskEstimate": ("External risk score", "points",
                                 "Consolidated external risk estimate (higher = safer)"),
        "MSinceOldestTradeOpen": ("Age of oldest account", "months",
                                  "Months since your oldest credit account was opened"),
        "MSinceMostRecentTradeOpen": ("Age of newest account", "months",
                                      "Months since your most recent account was opened"),
        "AverageMInFile": ("Average account age", "months",
                           "Average age of the accounts on file"),
        "NumSatisfactoryTrades": ("Accounts in good standing", "count",
                                  "Number of accounts in good standing"),
        "NumTrades60Ever2DerogPubRec": ("Accounts 60+ days late (ever)", "count",
                                        "Accounts ever 60+ days late or with a derogatory record"),
        "NumTrades90Ever2DerogPubRec": ("Accounts 90+ days late (ever)", "count",
                                        "Accounts ever 90+ days late or with a derogatory record"),
        "PercentTradesNeverDelq": ("% accounts never late", "%",
                                   "Percent of accounts that were never delinquent"),
        "MSinceMostRecentDelq": ("Months since last late", "months",
                                 "Months since your most recent delinquency"),
        "MaxDelq2PublicRecLast12M": ("Worst late (last 12 mo)", "code",
                                     "Worst delinquency / public record in the last 12 months"),
        "MaxDelqEver": ("Worst late (ever)", "code", "Worst delinquency ever recorded"),
        "NumTotalTrades": ("Total accounts", "count", "Total number of credit accounts"),
        "NumTradesOpeninLast12M": ("New accounts (12 mo)", "count",
                                   "Accounts opened in the last 12 months"),
        "PercentInstallTrades": ("% installment loans", "%",
                                 "Percent of accounts that are installment loans"),
        "MSinceMostRecentInqexcl7days": ("Months since last inquiry", "months",
                                         "Months since your most recent credit inquiry"),
        "NumInqLast6M": ("Inquiries (6 mo)", "count", "Credit inquiries in the last 6 months"),
        "NumInqLast6Mexcl7days": ("Inquiries (6 mo, adj.)", "count",
                                  "Credit inquiries in the last 6 months (excluding the last 7 days)"),
        "NetFractionRevolvingBurden": ("Revolving utilization", "%",
                                       "Revolving balance as a percent of your credit limit"),
        "NetFractionInstallBurden": ("Installment burden", "%",
                                     "Installment balance as a percent of the original loan"),
        "NumRevolvingTradesWBalance": ("Revolving accounts w/ balance", "count",
                                       "Revolving accounts that carry a balance"),
        "NumInstallTradesWBalance": ("Installment accounts w/ balance", "count",
                                     "Installment accounts that carry a balance"),
        "NumBank2NatlTradesWHighUtilization": ("Accounts near their limit", "count",
                                               "Bank / national accounts with high utilization"),
        "PercentTradesWBalance": ("% accounts w/ balance", "%",
                                  "Percent of accounts that carry a balance"),
    },
    "cancer": {},
}


def _pretty(name):
    """Create a label for a feature without display metadata."""
    s = str(name).replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else str(name)


def _onehot_groups(names, Xr):
    """Return groups of mutually exclusive binary columns."""
    Xb = np.round(np.asarray(Xr, float), 6)
    binary = [set(np.unique(Xb[:, j]).tolist()) <= {0.0, 1.0}
              for j in range(Xb.shape[1])]
    cand = {}
    for j, nm in enumerate(names):
        if not binary[j]:
            continue
        for i, ch in enumerate(nm):
            if ch == "_":
                cand.setdefault(nm[:i + 1], []).append(j)
    good = set()
    for prefix, cols in cand.items():
        if len(cols) < 2:
            continue
        rowsum = Xb[:, cols].sum(axis=1)
        if float((rowsum <= 1.0 + 1e-9).mean()) >= 0.99:
            good.add(prefix)
    groups = {}
    for j, nm in enumerate(names):
        if not binary[j]:
            continue
        best = None
        for i, ch in enumerate(nm):
            if ch == "_" and nm[:i + 1] in good:
                best = nm[:i + 1]
        if best is not None:
            groups[nm] = best
    return groups


# Locate the shared dataset directory used by the lab projects.
def _datasets_dir():
    for parent in Path(__file__).resolve().parents:
        cand = parent / "datasets"
        if (cand / "pima").is_dir() or (cand / "heloc").is_dir() or (cand / "mnist").is_dir():
            return cand
    raise FileNotFoundError(
        "Could not find the shared 'TRACE AI Lab/datasets' folder above "
        f"{Path(__file__).resolve()}. Expected datasets/{{pima,heloc,mnist}}/."
    )


DATASETS = _datasets_dir()
PIMA_CSV = DATASETS / "pima" / "diabetes.csv"
HELOC_CSV = DATASETS / "heloc" / "fico_heloc.csv"


@dataclass
class Dataset:
    X: np.ndarray
    y: np.ndarray
    feature_names: list
    scaler: StandardScaler
    missing_mask: np.ndarray
    class_names: tuple
    name: str
    key: str = ""

    @property
    def n(self):
        return self.X.shape[0]

    @property
    def d(self):
        return self.X.shape[1]

    @property
    def X_real(self):
        """Return the feature matrix in its original units."""
        return self.scaler.inverse_transform(self.X)

    def to_std(self, values_real):
        """Standardize one or more rows."""
        v = np.atleast_2d(np.asarray(values_real, float))
        return ((v - self.scaler.mean_) / self.scaler.scale_).astype(np.float64)

    def to_real(self, x_std):
        """Convert a standardized row to its original units."""
        return self.scaler.mean_ + self.scaler.scale_ * np.asarray(x_std, float)

    def feature_meta(self):
        """Return display metadata and real-unit summary statistics."""
        table = FEATURE_META.get(self.key, {})
        Xr = self.X_real
        groups = _onehot_groups(self.feature_names, Xr)
        out = []
        for j, name in enumerate(self.feature_names):
            label, unit, desc = table.get(name, (_pretty(name), "", ""))
            col = Xr[:, j]
            lo, med, hi = (float(np.percentile(col, p)) for p in (5, 50, 95))
            gk = groups.get(name)
            out.append({
                "name": name, "label": label, "unit": unit, "desc": desc,
                "min": float(col.min()), "p5": lo, "median": med,
                "p95": hi, "max": float(col.max()),
                # Allow for float32 round-trip noise on integer columns.
                "integer": bool(np.abs(col - np.round(col)).max() < 1e-3),
                "group": gk or "",
                "group_label": _pretty(gk.rstrip("_")) if gk else "",
                "value_label": name[len(gk):] if gk else "",
                "group_share": float(np.round(col).mean()) if gk else 0.0,
            })
        return out


# Stored zeros in these fields represent missing values.
_PIMA_ZERO_IS_MISSING = ["Glucose", "BloodPressure", "SkinThickness",
                         "Insulin", "BMI"]


def load_pima(path=None):
    """768 people, 8 features. Label 1 = diabetes ('bad' outcome)."""
    if path is None:
        path = PIMA_CSV
    df = pd.read_csv(path)
    features = [c for c in df.columns if c != "Outcome"]
    y = df["Outcome"].to_numpy().astype(int)
    Xdf = df[features].astype(float).copy()

    missing = np.zeros(Xdf.shape, dtype=bool)
    for col in _PIMA_ZERO_IS_MISSING:
        j = features.index(col)
        m = Xdf[col].to_numpy() == 0
        missing[:, j] = m
        Xdf.loc[m, col] = np.nan

    Xdf = Xdf.fillna(Xdf.median())
    scaler = StandardScaler().fit(Xdf.to_numpy())
    X = scaler.transform(Xdf.to_numpy()).astype(np.float32)
    return Dataset(X, y, features, scaler, missing,
                   class_names=("No diabetes", "Diabetes"), name="Pima", key="pima")


_HELOC_SENTINELS = [-7, -8, -9]


def load_heloc(path=None, random_state=0, balance=True):
    """Load and clean the FICO HELOC data. Label 1 is bad risk."""
    if path is None:
        path = HELOC_CSV
    df = pd.read_csv(path)
    df.replace(_HELOC_SENTINELS, np.nan, inplace=True)

    target = 'RiskPerformance'
    feat = [c for c in df.columns if c != target]

    topk = df[feat].isna().mean().nlargest(3).index.tolist()
    df.drop(columns=topk, inplace=True)
    feat = [c for c in df.columns if c != target]

    df = df.loc[df[feat].isna().mean(axis=1) <= 0.40].copy()

    y = (df[target].to_numpy() == 'Bad').astype(int)
    Xdf = df[feat].astype(float).copy()
    missing = Xdf.isna().to_numpy()
    Xdf = Xdf.fillna(Xdf.median())

    X = Xdf.to_numpy()
    if balance: 
        rng = np.random.default_rng(random_state)
        classes, counts = np.unique(y, return_counts=True)
        m = counts.min()
        idx = np.concatenate(
            [rng.choice(np.where(y == c)[0], m, replace=False) for c in classes])
        rng.shuffle(idx)
        X, y, missing = X[idx], y[idx], missing[idx]

    scaler = StandardScaler().fit(X)
    X = scaler.transform(X).astype(np.float32)
    return Dataset(X, y, feat, scaler, missing,
                   class_names=("Good risk", "Bad risk"), name="HELOC", key="heloc")


# Scikit-learn uses 0 for malignant; this project uses 1 for the bad class.
def load_breast_cancer_ds():
    """569 tumours, 30 features. Label 1 = malignant ('bad' outcome)."""
    from sklearn.datasets import load_breast_cancer
    b = load_breast_cancer()
    X_raw = b.data.astype(float)
    y = (b.target == 0).astype(int)
    scaler = StandardScaler().fit(X_raw)
    X = scaler.transform(X_raw).astype(np.float32)
    missing = np.zeros(X.shape, dtype=bool)
    return Dataset(X, y, list(b.feature_names), scaler, missing,
                   class_names=("Benign", "Malignant"), name="Breast cancer", key="cancer")


# Load datasets described by a CSV file and glimpse.json.
def load_custom_csv(folder, cfg):
    folder = Path(folder)
    csv = cfg.get("csv")
    if csv is None:
        csvs = sorted(folder.glob("*.csv"))
        if len(csvs) != 1:
            raise ValueError(f"{folder.name}: 'csv' not set and the folder "
                             f"holds {len(csvs)} csv files")
        csv = csvs[0].name
    df = pd.read_csv(folder / csv)
    df.drop(columns=[c for c in cfg.get("drop", []) if c in df], inplace=True)

    target = cfg["target"]
    if target not in df:
        raise ValueError(f"{folder.name}: target column '{target}' not in {csv}")
    y = (df[target] == cfg["positive"]).to_numpy().astype(int)

    feat_df = df.drop(columns=[target])
    non_num = [c for c in feat_df.columns
               if not pd.api.types.is_numeric_dtype(feat_df[c])]
    if non_num:
        print(f"[data] {folder.name}: dropping non-numeric columns {non_num}")
        feat_df = feat_df.drop(columns=non_num)
    feat = list(feat_df.columns)
    Xdf = feat_df.astype(float).copy()

    if cfg.get("sentinels"):
        Xdf.replace(cfg["sentinels"], np.nan, inplace=True)
    for col in cfg.get("zero_missing", []):
        if col in Xdf:
            Xdf.loc[Xdf[col] == 0, col] = np.nan
    missing = Xdf.isna().to_numpy()
    Xdf = Xdf.fillna(Xdf.median())

    X, yv = Xdf.to_numpy(), y
    if cfg.get("balance"):
        rng = np.random.default_rng(0)
        classes, counts = np.unique(yv, return_counts=True)
        m = counts.min()
        idx = np.concatenate(
            [rng.choice(np.where(yv == c)[0], m, replace=False) for c in classes])
        rng.shuffle(idx)
        X, yv, missing = X[idx], yv[idx], missing[idx]

    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X).astype(np.float32)
    names = cfg.get("class_names",
                    [f"not {cfg['positive']}", str(cfg['positive'])])
    return Dataset(Xs, yv, feat, scaler, missing,
                   class_names=tuple(names), name=cfg.get("label", folder.name),
                   key=folder.name)


def discover_custom(base=None):
    """Return custom dataset loaders found under the dataset directory."""
    import functools
    import json
    base = Path(base) if base is not None else DATASETS
    found = {}
    for cfg_path in sorted(base.glob("*/glimpse.json")):
        folder = cfg_path.parent
        try:
            cfg = json.loads(cfg_path.read_text())
            loader = functools.partial(load_custom_csv, folder, cfg)
            found[folder.name] = (cfg.get("label", folder.name), loader)
        except Exception as e:
            print(f"[data] skipping {folder.name}: {e}")
    return found


LOADERS = {"pima": load_pima, "heloc": load_heloc,
           "cancer": load_breast_cancer_ds}
DATASET_CHOICES = [{"key": "pima", "label": "Pima diabetes"},
                   {"key": "heloc", "label": "FICO HELOC"},
                   {"key": "cancer", "label": "Breast cancer (WDBC)"}]
for _key, (_label, _loader) in discover_custom().items():
    if _key not in LOADERS:
        LOADERS[_key] = _loader
        DATASET_CHOICES.append({"key": _key, "label": _label})

def evaluate(model, X, y):
    """Return accuracy and AUC."""
    if hasattr(model, "predict_proba"):
        p = model.predict_proba(X)[:, 1]
    else:
        p = model.proba(X)
    acc = ((p >= 0.5).astype(int) == y).mean()
    return float(acc), float(roc_auc_score(y, p))


if __name__ == "__main__":
    for key in LOADERS:
        d = LOADERS[key]()
        print(f"{d.name:6s}  n={d.n:5d}  d={d.d:2d}  "
              f"positives={int(d.y.sum())}/{d.n}  "
              f"missing cells={int(d.missing_mask.sum())}")
