"""Every projection method under test, behind one interface.

Each method exposes the same things so the benchmark can treat them alike:

    .fit(X, y, ctx)    ctx = {'w':..., 'ell':..., 'mask':...} for model-aware lenses
    .embed(X)          (n, 2)   -- raises if the method has no out-of-sample map
    .invert(Z)         (n, d)   -- None if the method has no inverse
    .caps              the capability flags GLIMPSE actually needs

`caps` is the honest half of the comparison: a method that scores well but
cannot place a new person on the map, cannot be inverted, and does not draw
straight boundaries cannot be GLIMPSE's lens, whatever its numbers say.
"""
import time
import warnings

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.decomposition import PCA, KernelPCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.manifold import Isomap, TSNE
from sklearn.neighbors import NeighborhoodComponentsAnalysis
from sklearn.random_projection import GaussianRandomProjection

from lab import fit_eclipse

SEED = 0


class Caps:
    """What a lens can do, as opposed to how well it scores."""

    def __init__(self, linear, supervised, invertible, out_of_sample,
                 model_aware=False):
        self.linear = linear                  # straight boundaries + straight CF paths
        self.supervised = supervised          # uses y
        self.invertible = invertible          # can map a click back to a person
        self.out_of_sample = out_of_sample    # can place a NEW person on the map
        self.model_aware = model_aware        # uses the classifier / Rashomon set

    def as_dict(self):
        return {k: bool(v) for k, v in self.__dict__.items()}


class Projection:
    """Base class.  Subclasses implement _fit / _embed / _invert."""
    name = "base"
    caps = Caps(False, False, False, False)

    def fit(self, X, y=None, ctx=None):
        t0 = time.perf_counter()
        self._fit(np.asarray(X, float), y, ctx or {})
        self.fit_seconds = time.perf_counter() - t0
        return self

    def embed(self, X):
        return np.atleast_2d(self._embed(np.asarray(X, float)))

    def invert(self, Z):
        if not self.caps.invertible:
            return None
        return np.atleast_2d(self._invert(np.atleast_2d(np.asarray(Z, float))))

    def _invert(self, Z):
        raise NotImplementedError


class _LinearProjection(Projection):
    """Anything of the form z = (x - mean) @ comp.T with comp of shape (2, d)."""

    def _embed(self, X):
        return (X - self.mean) @ self.comp.T

    def _invert(self, Z):
        # comp rows need not be orthonormal (LDA, NCA, PLS), so use the pseudo-inverse.
        return Z @ np.linalg.pinv(self.comp).T + self.mean

    @property
    def axes(self):
        return self.comp


# ------------------------------------------------------------ linear, unsupervised

class PCAProj(_LinearProjection):
    name = "PCA"
    caps = Caps(linear=True, supervised=False, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        p = PCA(n_components=2, random_state=SEED).fit(X)
        self.mean, self.comp = p.mean_, p.components_
        self.var_explained = float(p.explained_variance_ratio_[:2].sum())


class RandomProj(_LinearProjection):
    """Control.  A method that cannot beat this has told us nothing."""
    name = "Random"
    caps = Caps(linear=True, supervised=False, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        rp = GaussianRandomProjection(n_components=2, random_state=SEED).fit(X)
        self.mean = X.mean(axis=0)
        c = rp.components_
        self.comp = c / np.linalg.norm(c, axis=1, keepdims=True)


# ------------------------------------------------------------ linear, supervised

class LDAProj(_LinearProjection):
    """Two classes give LDA only ONE discriminant direction, so axis 2 is the
    leading PCA direction of what is left over.  That is the fair way to use
    LDA as a 2-D lens, and the rank-1 limit is itself a finding."""
    name = "LDA"
    caps = Caps(linear=True, supervised=True, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto").fit(X, y)
        a = lda.coef_.ravel()
        a = a / np.linalg.norm(a)
        Xc = X - X.mean(axis=0)
        resid = Xc - np.outer(Xc @ a, a)          # project the discriminant out
        b = PCA(n_components=1, random_state=SEED).fit(resid).components_[0]
        self.mean, self.comp = X.mean(axis=0), np.vstack([a, b])
        self.n_discriminants = 1


class PLSProj(_LinearProjection):
    name = "PLS"
    caps = Caps(linear=True, supervised=True, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p = PLSRegression(n_components=2, scale=False).fit(X, np.asarray(y, float))
        c = p.x_rotations_.T                       # (2, d)
        self.mean = X.mean(axis=0)
        self.comp = c / np.linalg.norm(c, axis=1, keepdims=True)


class NCAProj(_LinearProjection):
    name = "NCA"
    caps = Caps(linear=True, supervised=True, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        n = NeighborhoodComponentsAnalysis(n_components=2, random_state=SEED,
                                           max_iter=80).fit(X, y)
        c = n.components_
        self.mean = X.mean(axis=0)
        self.comp = c / np.linalg.norm(c, axis=1, keepdims=True)


# ------------------------------------------------------------ nonlinear

class KernelPCAProj(Projection):
    name = "KernelPCA"
    caps = Caps(linear=False, supervised=False, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        self.kp = KernelPCA(n_components=2, kernel="rbf", gamma=1.0 / X.shape[1],
                            fit_inverse_transform=True, random_state=SEED,
                            alpha=1e-3).fit(X)

    def _embed(self, X):
        return self.kp.transform(X)

    def _invert(self, Z):
        return self.kp.inverse_transform(Z)


class IsomapProj(Projection):
    name = "Isomap"
    caps = Caps(linear=False, supervised=False, invertible=False, out_of_sample=True)

    def _fit(self, X, y, ctx):
        self.iso = Isomap(n_components=2, n_neighbors=10).fit(X)

    def _embed(self, X):
        return self.iso.transform(X)


class TSNEProj(Projection):
    """No transform() at all: a new person can never be placed on the map."""
    name = "t-SNE"
    caps = Caps(linear=False, supervised=False, invertible=False, out_of_sample=False)

    def _fit(self, X, y, ctx):
        self.X_fit = X
        self.Z_fit = TSNE(n_components=2, random_state=SEED, init="pca",
                          perplexity=min(30, max(5, len(X) // 4))).fit_transform(X)

    def _embed(self, X):
        if X.shape == self.X_fit.shape and np.allclose(X, self.X_fit):
            return self.Z_fit
        raise NotImplementedError("t-SNE cannot embed out-of-sample points")


class UMAPProj(Projection):
    name = "UMAP"
    caps = Caps(linear=False, supervised=False, invertible=True, out_of_sample=True)

    def _fit(self, X, y, ctx):
        import umap
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.um = umap.UMAP(n_components=2, random_state=SEED,
                                n_neighbors=15, min_dist=0.1).fit(X)

    def _embed(self, X):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.um.transform(X)

    def _invert(self, Z):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.um.inverse_transform(Z)


class PaCMAPProj(Projection):
    name = "PaCMAP"
    caps = Caps(linear=False, supervised=False, invertible=False, out_of_sample=True)

    def _fit(self, X, y, ctx):
        import pacmap
        self.pm = pacmap.PaCMAP(n_components=2, random_state=SEED)
        self.Z_fit = self.pm.fit_transform(X.copy())
        self.X_fit = X

    def _embed(self, X):
        if X.shape == self.X_fit.shape and np.allclose(X, self.X_fit):
            return self.Z_fit
        return self.pm.transform(X.copy(), basis=self.X_fit)


# ------------------------------------------------------------ autoencoders

class _AEBase(Projection):
    """d -> 64 -> 32 -> 2 -> 32 -> 64 -> d, trained with Adam."""
    hidden = (64, 32)
    epochs = 200
    lr = 1e-3
    weight_recon = 1.0
    weight_class = 0.0

    def _fit(self, X, y, ctx):
        import torch
        import torch.nn as nn
        torch.manual_seed(SEED)
        d = X.shape[1]
        h1, h2 = self.hidden
        self.enc = nn.Sequential(nn.Linear(d, h1), nn.ReLU(),
                                 nn.Linear(h1, h2), nn.ReLU(), nn.Linear(h2, 2))
        self.dec = nn.Sequential(nn.Linear(2, h2), nn.ReLU(),
                                 nn.Linear(h2, h1), nn.ReLU(), nn.Linear(h1, d))
        self.head = nn.Linear(2, 1)
        params = list(self.enc.parameters()) + list(self.dec.parameters())
        if self.weight_class > 0:
            params += list(self.head.parameters())
        opt = torch.optim.Adam(params, lr=self.lr)
        Xt = torch.tensor(X, dtype=torch.float32)
        yt = torch.tensor(np.asarray(y, float), dtype=torch.float32)[:, None]
        mse, bce = torch.nn.MSELoss(), torch.nn.BCEWithLogitsLoss()

        n, bs = len(Xt), min(256, len(Xt))
        for _ in range(self.epochs):
            perm = torch.randperm(n)
            for i in range(0, n, bs):
                idx = perm[i:i + bs]
                z = self.enc(Xt[idx])
                loss = self.weight_recon * mse(self.dec(z), Xt[idx])
                if self.weight_class > 0:
                    loss = loss + self.weight_class * bce(self.head(z), yt[idx])
                opt.zero_grad()
                loss.backward()
                opt.step()
        self.enc.eval()
        self.dec.eval()

    def _embed(self, X):
        import torch
        with torch.no_grad():
            return self.enc(torch.tensor(X, dtype=torch.float32)).numpy()

    def _invert(self, Z):
        import torch
        with torch.no_grad():
            return self.dec(torch.tensor(Z, dtype=torch.float32)).numpy()


class AEProj(_AEBase):
    name = "Autoencoder"
    caps = Caps(linear=False, supervised=False, invertible=True, out_of_sample=True)


class SAEProj(_AEBase):
    """Supervised autoencoder: same net plus a classifier head off the 2-D code."""
    name = "SAE"
    caps = Caps(linear=False, supervised=True, invertible=True, out_of_sample=True)
    weight_class = 3.0                  # wr ~ 3 was the best setting in earlier work


# ------------------------------------------------------------ GLIMPSE's own lens

class EclipseProj(_LinearProjection):
    name = "ECLIPSE"
    caps = Caps(linear=True, supervised=True, invertible=True, out_of_sample=True,
                model_aware=True)

    def __init__(self, weights=None, name=None):
        self.weights = weights          # None => run the auto rule
        if name:
            self.name = name

    def _fit(self, X, y, ctx):
        lens = fit_eclipse(X, y, ctx["w"], ctx["ell"], ctx.get("mask"),
                           weights=self.weights)
        self.lens = lens
        self.mean, self.comp = lens.mean, lens.comp
        self.weights_used = lens.weights_used
        self.extra = lens.extra


def all_methods(include_slow=True):
    """The full roster, in a sensible reading order."""
    m = [PCAProj(), RandomProj(), LDAProj(), PLSProj(), NCAProj(),
         KernelPCAProj(), IsomapProj(), TSNEProj(), UMAPProj(), PaCMAPProj(),
         AEProj(), SAEProj(), EclipseProj()]
    if not include_slow:
        drop = {"UMAP", "PaCMAP", "Autoencoder", "SAE", "t-SNE", "Isomap"}
        m = [p for p in m if p.name not in drop]
    return m
