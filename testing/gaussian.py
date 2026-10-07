"""Tools for the question 'p(y|x) comes from a Gaussian'.

The claim, stated properly.  Assume each class is a Gaussian blob and the two
blobs have the SAME shape:

    x | y=0 ~ N(mu0, Sigma),   x | y=1 ~ N(mu1, Sigma),   P(y=1) = pi

Then Bayes' rule gives the posterior in closed form, and the quadratic terms
cancel because Sigma is shared:

    log p(y=1|x)/p(y=0|x) = w . x + b
    w = Sigma^-1 (mu1 - mu0)
    b = -0.5 (mu1+mu0)' Sigma^-1 (mu1-mu0) + log(pi/(1-pi))

so  p(y=1|x) = sigmoid(w.x + b)  EXACTLY.  Logistic regression is not an
approximation under this model; it is the truth.  That is the sense in which
p(y|x) 'comes from a Gaussian'.

Everything in this module either derives from that fact or tests whether it
holds on real data.
"""
import numpy as np
from scipy.stats import kurtosis, skew
from sklearn.discriminant_analysis import (LinearDiscriminantAnalysis,
                                           QuadraticDiscriminantAnalysis)
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict, StratifiedKFold

from lab import sigmoid


# ------------------------------------------------------------ the exact result

def bayes_logit(mu0, mu1, Sigma, pi=0.5):
    """The exact (w, b) implied by shared-covariance Gaussian classes."""
    Si = np.linalg.inv(Sigma)
    w = Si @ (mu1 - mu0)
    b = -0.5 * (mu1 + mu0) @ w + np.log(pi / (1 - pi))
    return w, float(b)


def make_gaussian_data(n=2000, d=8, sep=1.2, pi=0.5, cond=8.0, seed=0,
                       shared_cov=True, cov_scale=2.5):
    """Sample from the model above.  Returns X, y and the TRUE (w, b).

    ``shared_cov=False`` breaks the assumption on purpose: class 1 gets a
    stretched covariance, the quadratic terms no longer cancel, and the true
    log-odds stops being linear.  ``w``/``b`` are then only the best linear
    stand-in and ``is_linear`` is False.
    """
    rng = np.random.default_rng(seed)
    # A covariance with a controlled condition number and random orientation.
    ev = np.logspace(0, np.log10(cond), d)
    R = np.linalg.qr(rng.standard_normal((d, d)))[0]
    Sigma = R @ np.diag(ev) @ R.T

    direction = rng.standard_normal(d)
    direction /= np.linalg.norm(direction)
    mu0 = np.zeros(d)
    # Separate the means along a direction that is NOT a principal axis,
    # so PCA and the true signal genuinely disagree.
    mu1 = sep * (R @ (np.ones(d) / np.sqrt(d))) + 0.5 * direction

    y = (rng.random(n) < pi).astype(int)
    L0 = np.linalg.cholesky(Sigma)
    Sigma1 = Sigma * cov_scale if not shared_cov else Sigma
    L1 = np.linalg.cholesky(Sigma1)
    X = np.empty((n, d))
    X[y == 0] = mu0 + rng.standard_normal(((y == 0).sum(), d)) @ L0.T
    X[y == 1] = mu1 + rng.standard_normal(((y == 1).sum(), d)) @ L1.T

    w, b = bayes_logit(mu0, mu1, Sigma, pi)
    return {"X": X, "y": y, "w_true": w, "b_true": b, "Sigma": Sigma,
            "mu0": mu0, "mu1": mu1, "is_linear": shared_cov}


def posterior_curve(X, y, w, b, n_bins=18):
    """Empirical P(y=1 | w.x) against the sigmoid it should follow.

    This is the picture-proof of the claim: bin people by their score and the
    observed fraction with y=1 should land on the logistic curve.
    """
    s = X @ w + b
    edges = np.quantile(s, np.linspace(0, 1, n_bins + 1))
    edges[-1] += 1e-9
    idx = np.clip(np.digitize(s, edges) - 1, 0, n_bins - 1)
    mid, emp, cnt = [], [], []
    for k in range(n_bins):
        m = idx == k
        if m.sum() < 5:
            continue
        mid.append(float(s[m].mean()))
        emp.append(float(y[m].mean()))
        cnt.append(int(m.sum()))
    mid = np.array(mid)
    return mid, np.array(emp), sigmoid(mid), np.array(cnt)


def cosine(a, b):
    """|cos| between two directions; 1.0 means the same axis."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(abs(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# ------------------------------------------------------------ testing the assumption

def shared_cov_gap(X, y):
    """How far the two classes are from sharing a covariance.

    Returns the mean |log| of the eigenvalues of Sigma0^-1 Sigma1 (0 = equal
    shapes).  Shrinkage keeps it defined when a class is small relative to d.
    """
    d = X.shape[1]
    def cov(Z):
        C = np.cov(Z.T)
        return C + 1e-3 * np.trace(C) / d * np.eye(d)
    ev = np.linalg.eigvals(np.linalg.solve(cov(X[y == 0]), cov(X[y == 1])))
    return float(np.mean(np.abs(np.log(np.abs(ev) + 1e-12))))


def normality_report(X):
    """Marginal non-Gaussianity: mean |skew| and mean |excess kurtosis|.

    Both are 0 for a Gaussian.  Heavy tails show up as large kurtosis, and
    that is exactly what the kappa_2 theory's Gaussian assumption trades on.
    """
    return {"abs_skew": float(np.mean(np.abs(skew(X, axis=0)))),
            "abs_excess_kurt": float(np.mean(np.abs(kurtosis(X, axis=0))))}


def linear_cost(X, y, seed=0):
    """What the linear assumption costs in AUC on this dataset.

    logistic vs QDA (a quadratic log-odds, i.e. unequal Gaussians) vs boosted
    trees (a free-form log-odds).  Small gaps mean the Gaussian/linear story
    is safe here and GLIMPSE's straight boundary is honest.
    """
    cv = StratifiedKFold(5, shuffle=True, random_state=seed)
    out = {}
    models = {"logistic": LogisticRegression(max_iter=5000),
              "lda": LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto"),
              "qda": QuadraticDiscriminantAnalysis(reg_param=0.1),
              "boosted_trees": HistGradientBoostingClassifier(random_state=seed)}
    for name, m in models.items():
        p = cross_val_predict(m, X, y, cv=cv, method="predict_proba")[:, 1]
        out[name] = round(float(roc_auc_score(y, p)), 4)
    out["cost_of_linear"] = round(out["boosted_trees"] - out["logistic"], 4)
    return out


def plugin_direction(X, y, shrink=1e-3):
    """The Gaussian plug-in estimate w = Sigma^-1 (mu1 - mu0)."""
    d = X.shape[1]
    S = np.cov(X.T)
    S = S + shrink * np.trace(S) / d * np.eye(d)
    return np.linalg.solve(S, X[y == 1].mean(0) - X[y == 0].mean(0))


def gaussian_audit(X, y, w_fitted):
    """One row per dataset: does the Gaussian story hold, and does it matter?"""
    r = {**normality_report(X),
         "shared_cov_gap": round(shared_cov_gap(X, y), 3),
         "cos(logreg, Sigma^-1 dmu)": round(cosine(w_fitted, plugin_direction(X, y)), 3),
         "cos(logreg, dmu)": round(
             cosine(w_fitted, X[y == 1].mean(0) - X[y == 0].mean(0)), 3)}
    r.update(linear_cost(X, y))
    r["abs_skew"] = round(r["abs_skew"], 3)
    r["abs_excess_kurt"] = round(r["abs_excess_kurt"], 3)
    return r
