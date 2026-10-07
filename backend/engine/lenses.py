"""ECLIPSE projection and validation helpers."""
import numpy as np
from scipy.stats import spearmanr
from sklearn.manifold import trustworthiness
from sklearn.model_selection import train_test_split

SCORE_SAMPLE = 600
SELECT_VAL_MAX = 800
TAU = 0.05
N_GRID = 17


def _aug(X):
    return np.hstack([X, np.ones((len(X), 1))])


def disagreement(ell, X):
    """Half-width of the logit interval across the Rashomon ellipsoid."""
    return np.linalg.norm(_aug(X) @ ell.Q_inv_sqrt, axis=1)


def _build_S(X, w_vec, ell, missing_mask):
    """Build the unit-trace interest matrices."""
    d = X.shape[1]
    S = np.zeros((4, d, d))
    S[0] = np.cov(X.T)
    S[1] = np.outer(w_vec, w_vec)
    Qinv = ell.Q_inv_sqrt @ ell.Q_inv_sqrt
    dis = np.maximum(disagreement(ell, X), 1e-12)
    G = (_aug(X) @ Qinv)[:, :d] / dis[:, None]
    S[2] = G.T @ G / len(X)
    if missing_mask is not None and missing_mask.any():
        f = missing_mask.mean(axis=0)
        s2 = np.array([np.var(X[~missing_mask[:, j], j])
                       if (~missing_mask[:, j]).any() else 0.0
                       for j in range(d)])
        S[3] = np.diag(f * s2)
    for i in range(4):
        tr = np.trace(S[i])
        if tr > 1e-12:
            S[i] /= tr
    return S


class EclipseLens:
    is_linear = True
    key = "eclipse"
    label = "ECLIPSE"
    extra = ""
    blurb = ("A straight-line map tilted toward the model: left-to-right "
             "roughly tracks the score, and the plane keeps the directions "
             "where equally-good models disagree and where values had to be "
             "imputed. Exactly reversible, like PCA.")

    def __init__(self, weights):
        self.weights = np.asarray(weights, float)

    def fit(self, X, w_vec, ell, missing_mask=None, S=None):
        if S is None:
            S = _build_S(X, w_vec, ell, missing_mask)
        w = self.weights.copy()
        for i in range(4):
            if np.trace(S[i]) < 1e-12:
                w[i] = 0.0
        w = w / w.sum()
        # Keep a stable second axis when the blend is nearly rank one.
        M = np.einsum("i,ijk->jk", w, S) + 1e-6 * S[0]
        vals, vecs = np.linalg.eigh(M)
        self.comp = vecs[:, [-1, -2]].T.copy()
        self.mean = X.mean(axis=0)
        self.weights_used = w
        return self

    def pin_orientation(self, X_all, y_all):
        # Keep class 0 on the right side of the plot.
        emb = self.embed(X_all)
        if emb[y_all == 0, 0].mean() < emb[y_all == 1, 0].mean():
            self.comp[0] *= -1.0

    def embed(self, X):
        return (np.atleast_2d(np.asarray(X, float)) - self.mean) @ self.comp.T

    def invert(self, Z):
        return np.atleast_2d(np.asarray(Z, float)) @ self.comp + self.mean

    def grid(self, xlim, ylim, res=300):
        xs, ys = np.linspace(*xlim, res), np.linspace(*ylim, res)
        XX, YY = np.meshgrid(xs, ys)
        return XX, YY, self.invert(np.column_stack([XX.ravel(), YY.ravel()]))

    def linear_logit_coeffs(self, theta):
        w, b = theta[:-1], theta[-1]
        return self.comp @ w, float(w @ self.mean + b)

    def score(self, Xte, rng_seed=0):
        rng = np.random.default_rng(rng_seed)
        idx = (np.arange(len(Xte)) if len(Xte) <= SCORE_SAMPLE
               else rng.choice(len(Xte), SCORE_SAMPLE, replace=False))
        Xs = np.asarray(Xte, float)[idx]
        Z = self.embed(Xs)
        Xr = self.invert(Z)
        Z2 = self.embed(Xr)
        spread = max(float(np.linalg.norm(Z - Z.mean(0), axis=1).mean()), 1e-12)
        self.quality = {
            "recon": round(float(np.abs(Xr - Xs).mean()), 3),
            "trust": round(float(trustworthiness(Xs, Z, n_neighbors=10)), 3),
            "rt": round(float(np.linalg.norm(Z2 - Z, axis=1).mean() / spread), 3),
        }


def _select_weights(X_tr, y_tr, w_vec, ell, mask_tr, tau=TAU, n_grid=N_GRID):
    """Select blend weights on a validation split."""
    idx_sub, idx_val = train_test_split(np.arange(len(X_tr)), test_size=0.25,
                                        random_state=0, stratify=y_tr)
    if len(idx_val) > SELECT_VAL_MAX:
        idx_val = np.random.default_rng(0).choice(idx_val, SELECT_VAL_MAX,
                                                  replace=False)
    X_sub, X_val = X_tr[idx_sub], X_tr[idx_val]
    m_sub = mask_tr[idx_sub] if mask_tr is not None else None
    S = _build_S(X_sub, w_vec, ell, m_sub)

    mixes = [(0.5, 0.5, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    if np.trace(S[3]) > 1e-12:
        mixes.append((1 / 3, 1 / 3, 1 / 3))

    # Spearman correlation does not depend on the intercept.
    logit_val = X_val @ w_vec
    dis_val = disagreement(ell, X_val)

    best_crit, best_lam, best_mix, floor = -np.inf, 0.0, np.asarray(mixes[0]), None
    for mix in (np.asarray(m, float) for m in mixes):
        mix = mix / mix.sum()
        for lam in np.linspace(0.0, 1.0, n_grid):
            if lam == 0.0 and floor is not None:
                continue
            lens = EclipseLens(np.concatenate([[1 - lam], lam * mix]))
            lens.fit(X_sub, w_vec, ell, S=S)
            Z = lens.embed(X_val)
            Xh = lens.invert(Z)
            tr = trustworthiness(X_val, Z, n_neighbors=10)
            if floor is None:
                floor = tr - tau
            if tr < floor:
                continue
            sv = spearmanr(logit_val, Xh @ w_vec)[0]
            rv = spearmanr(dis_val, disagreement(ell, Xh))[0]
            crit = max(sv, 0.0) * max(rv, 0.0)
            if crit > best_crit:
                best_crit, best_lam, best_mix = crit, lam, mix
    return np.concatenate([[1 - best_lam], best_lam * best_mix])


def fit_eclipse(data, model, ell):
    """Fit and score the ECLIPSE lens for one dataset."""
    X = np.asarray(data.X, float)
    y = np.asarray(data.y, int)
    idx_tr, idx_te = train_test_split(np.arange(len(X)), test_size=0.2,
                                      random_state=0, stratify=y)
    mask = getattr(data, "missing_mask", None)
    mask_tr = mask[idx_tr] if mask is not None else None

    weights = _select_weights(X[idx_tr], y[idx_tr], model.w, ell, mask_tr)
    lens = EclipseLens(weights).fit(X[idx_tr], model.w, ell, mask_tr)
    lens.pin_orientation(X, y)
    lens.score(X[idx_te])

    cov = np.cov(X.T)
    kept = float(np.trace(lens.comp @ cov @ lens.comp.T) / np.trace(cov))
    names = ("spread", "model", "disagreement", "imputation")
    parts = "/".join(f"{n} {v:.2f}" for n, v in zip(names, lens.weights_used)
                     if v > 0.005)
    lens.extra = (f"auto weights: {parts} · keeps {round(kept * 100)}% of "
                  "variance · exact inverse")
    return lens
