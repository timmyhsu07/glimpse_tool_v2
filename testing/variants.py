"""Candidate improvements to ECLIPSE, each with a reason to exist.

ECLIPSE picks the top two eigenvectors of a blend M of four interest
matrices.  Three things about that recipe are worth questioning, and each
question turns into a variant that the benchmark can settle.
"""
import numpy as np
import scipy.linalg as sla

from lab import build_S, select_weights
from projections import Caps, _LinearProjection


class _BlendBase(_LinearProjection):
    caps = Caps(linear=True, supervised=True, invertible=True,
                out_of_sample=True, model_aware=True)

    def __init__(self, weights=None, name=None):
        self.weights = weights
        if name:
            self.name = name

    def _blend(self, X, y, ctx):
        S = build_S(X, ctx["w"], ctx["ell"], ctx.get("mask"))
        w = self.weights
        if w is None:
            w = select_weights(X, y, ctx["w"], ctx["ell"], ctx.get("mask"))
        w = np.asarray(w, float)
        for i in range(4):
            if np.trace(S[i]) < 1e-12:
                w[i] = 0.0
        w = w / w.sum()
        self.weights_used = w
        return np.einsum("i,ijk->jk", w, S) + 1e-6 * S[0]

    def _orient(self, X, y):
        """Keep class 0 on the right, as the shipped lens does."""
        emb = self._embed(X)
        if emb[y == 0, 0].mean() < emb[y == 1, 0].mean():
            self.comp[0] *= -1.0


class SufficiencyEclipse(_BlendBase):
    """Axis 1 IS the model direction w; axis 2 is the best of what is left.

    Why: under shared-covariance Gaussian classes, w = Sigma^-1 (mu1 - mu0)
    is a sufficient statistic for y -- all the label information sits on that
    one axis.  Pinning axis 1 to w makes the score an EXACT function of the
    on-screen x-coordinate instead of an approximate one, and frees axis 2 to
    carry something the score cannot (spread, disagreement, imputation).
    """
    name = "ECLIPSE-suff"

    def _fit(self, X, y, ctx):
        M = self._blend(X, y, ctx)
        a1 = np.asarray(ctx["w"], float)
        a1 = a1 / np.linalg.norm(a1)
        P = np.eye(len(a1)) - np.outer(a1, a1)          # orthogonal complement of w
        vals, vecs = np.linalg.eigh(P @ M @ P)
        a2 = vecs[:, -1]
        a2 = a2 - (a2 @ a1) * a1
        a2 /= np.linalg.norm(a2)
        self.mean, self.comp = X.mean(axis=0), np.vstack([a1, a2])
        self._orient(X, y)


class GeneralizedEclipse(_BlendBase):
    """Maximise interest PER UNIT OF SPREAD: solve M v = lambda Sigma v.

    Why: ECLIPSE treats every direction as equally cheap, but a direction the
    data barely varies along cannot show anything on screen.  The generalized
    problem is the same move LDA makes (between- over within-scatter), and it
    is where the Sigma^-1 in the Gaussian posterior direction comes from.
    """
    name = "ECLIPSE-gen"

    def _fit(self, X, y, ctx):
        M = self._blend(X, y, ctx)
        d = X.shape[1]
        Sig = np.cov(X.T)
        Sig = Sig + 1e-3 * np.trace(Sig) / d * np.eye(d)
        vals, vecs = sla.eigh(M, Sig)
        c = vecs[:, [-1, -2]].T
        self.mean = X.mean(axis=0)
        self.comp = c / np.linalg.norm(c, axis=1, keepdims=True)
        self._orient(X, y)


class CeilingAwareEclipse(_BlendBase):
    """Only buy the disagreement axis when the geometry can actually pay.

    Why: kappa_2 is a hard ceiling on how well ANY plane can show
    disagreement, computable before fitting.  When kappa_2 is low, weight
    spent on the disagreement term is wasted -- it buys ordering that cannot
    exist -- so spend it on the score instead.
    """
    name = "ECLIPSE-ceil"

    def __init__(self, kappa_lo=0.55, name=None):
        super().__init__(None, name)
        self.kappa_lo = kappa_lo

    def _fit(self, X, y, ctx):
        from lab import rash_ceiling
        k2 = rash_ceiling(X, ctx["ell"])
        self.kappa2 = k2
        S = build_S(X, ctx["w"], ctx["ell"], ctx.get("mask"))
        has_miss = np.trace(S[3]) > 1e-12
        if k2 < self.kappa_lo:
            w = [0.45, 0.55, 0.0, 0.0]            # disagreement is hopeless here
        elif has_miss:
            w = [0.40, 0.25, 0.25, 0.10]
        else:
            w = [0.40, 0.30, 0.30, 0.0]
        self.weights = np.asarray(w, float)
        M = self._blend(X, y, ctx)
        vals, vecs = np.linalg.eigh(M)
        self.mean, self.comp = X.mean(axis=0), vecs[:, [-1, -2]].T.copy()
        self._orient(X, y)


def ablations():
    """ECLIPSE with each interest term isolated, to see what each one buys."""
    from projections import EclipseProj
    return [
        EclipseProj([1, 0, 0, 0], name="abl:spread(=PCA)"),
        EclipseProj([0, 1, 0, 0], name="abl:model only"),
        EclipseProj([0, 0, 1, 0], name="abl:disagree only"),
        EclipseProj([0.5, 0.5, 0, 0], name="abl:spread+model"),
        EclipseProj([1 / 3, 1 / 3, 1 / 3, 0], name="abl:equal thirds"),
        EclipseProj(None, name="ECLIPSE(auto)"),
    ]


def candidates():
    """The shipped lens plus the three proposed replacements."""
    from projections import EclipseProj, PCAProj
    return [PCAProj(), EclipseProj(None, name="ECLIPSE(auto)"),
            SufficiencyEclipse(), GeneralizedEclipse(), CeilingAwareEclipse()]
