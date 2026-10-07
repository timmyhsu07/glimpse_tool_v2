"""The distance-preservation vs confidence-score tradeoff.

ECLIPSE's two-term blend  M(lam) = (1-lam) Sigma/tr(Sigma) + lam w w'/|w|^2
has an exact reading.  For a plane with orthonormal basis P (d x 2):

    tr(P' M P) = (1-lam) V(P) + lam C(P)

    V(P) = tr(P' Sigma P) / tr(Sigma)   fraction of total squared pairwise
                                         distance the plane keeps
    C(P) = |P' w|^2 / |w|^2             fraction of the model direction in the
                                         plane (C = 1: the logit, hence the
                                         confidence score, is an exact affine
                                         function of map position)

The top-2 eigenvectors of M(lam) maximise that weighted sum (Ky Fan), so for
lam in (0, 1) each is Pareto-optimal: no linear plane keeps more distance AND
more of the model direction.  Sweeping lam traces the frontier.

``theory_frontier`` computes the exact (V, C) curve; ``empirical_sweep`` runs
the same planes through the benchmark harness so the curve sits on the same
held-out axes (trust, score_read) as the 13-method benchmark.
"""
import numpy as np
import pandas as pd

from lab import EclipseLens, build_S

LAMS = np.round(np.linspace(0.0, 1.0, 21), 3)


def orthonormal(comp):
    """Orthonormal basis (d x 2) for the span of a (2, d) axis matrix."""
    q, _ = np.linalg.qr(np.asarray(comp, float).T)
    return q[:, :2]


def captured_variance(comp, Sigma):
    P = orthonormal(comp)
    return float(np.trace(P.T @ Sigma @ P) / np.trace(Sigma))


def captured_weight(comp, w):
    P = orthonormal(comp)
    w = np.asarray(w, float)
    return float(np.sum((P.T @ w) ** 2) / (w @ w))


def linear_score_r2(comp, Sigma, w):
    """Best linear R^2 of the logit from map coordinates, over the data law.

    Unlike C(P) this weighs the hidden part of w by how much the data varies
    along it, so it is the quantity a reader actually experiences.
    """
    A = np.asarray(comp, float)
    w = np.asarray(w, float)
    Sw = Sigma @ w
    B = A @ Sigma @ A.T
    return float((A @ Sw) @ np.linalg.solve(B, A @ Sw) / (w @ Sw))


def blend_plane(X, w, lam, ell=None, mask=None):
    """Exactly the shipped EclipseLens with weights (1-lam, lam, 0, 0)."""
    S = build_S(X, w, ell, mask) if ell is not None else _spread_model_S(X, w)
    lens = EclipseLens([1.0 - lam, lam, 0.0, 0.0]).fit(X, w, ell, mask, S=S)
    return lens.comp


def _spread_model_S(X, w):
    d = X.shape[1]
    S = np.zeros((4, d, d))
    S[0] = np.cov(X.T) / np.trace(np.cov(X.T))
    S[1] = np.outer(w, w) / (w @ w)
    return S


def theory_frontier(X, w, lams=None):
    """Exact (V, C, R^2) along the lam sweep, on the data it is fitted to."""
    lams = np.linspace(0.0, 1.0, 201) if lams is None else lams
    Sigma = np.cov(np.asarray(X, float).T)
    rows = []
    for lam in lams:
        comp = blend_plane(X, w, float(lam))
        rows.append({"lam": float(lam),
                     "V": captured_variance(comp, Sigma),
                     "C": captured_weight(comp, w),
                     "R2": linear_score_r2(comp, Sigma, w)})
    return pd.DataFrame(rows)


def dominated_by_frontier(V, C, frontier, tol=1e-9):
    """True if some frontier plane keeps at least as much of BOTH."""
    f = frontier
    return bool(((f["V"] >= V - tol) & (f["C"] >= C - tol)).any())


def _blend_proj(lam):
    """The lam-plane as a benchmark projection, fitted on the whole train half.

    The shipped EclipseProj refits on an internal 80% subsample; fitting on
    the same rows as PCAProj instead makes lam = 0 identical to PCA, so the
    curve and the PCA marker share one origin.
    """
    from projections import Caps, _LinearProjection

    class BlendProj(_LinearProjection):
        caps = Caps(linear=True, supervised=True, invertible=True,
                    out_of_sample=True, model_aware=True)
        name = f"lam={lam:.3f}"

        def _fit(self, X, y, ctx):
            self.comp = blend_plane(X, ctx["w"], lam, ctx["ell"], ctx.get("mask"))
            self.mean = X.mean(axis=0)

    return BlendProj()


def empirical_sweep(key, lams=LAMS, eps=0.03, **kw):
    """Score the lam-planes on the held-out split, benchmark protocol.

    Also returns the train half's Sigma and w, so the exact (V, C) of every
    row can be computed on the same data the planes were fitted to.
    """
    from benchmark import run_dataset, _cap
    from lab import fit_glimpse
    from projections import EclipseProj, PCAProj

    methods = [_blend_proj(float(lam)) for lam in lams]
    methods += [PCAProj(), EclipseProj()]
    df = run_dataset(key, methods, eps=eps, verbose=False, **kw)
    df["lam"] = [float(m.split("=")[1]) if m.startswith("lam=") else np.nan
                 for m in df["method"]]
    g = fit_glimpse(key, eps=eps, lens=None)
    itr = _cap(g.idx_tr, kw.get("max_train", 2500))
    Xtr = g.X[itr]
    mask = getattr(g.data, "missing_mask", None)
    return df, {"X": Xtr, "y": g.y[itr], "w": g.model.w, "ell": g.ell,
                "mask": mask[itr] if mask is not None else None,
                "Sigma": np.cov(Xtr.T), "methods": methods, "glimpse": g}
