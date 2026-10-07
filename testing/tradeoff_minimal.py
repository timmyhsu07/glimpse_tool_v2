"""The distance-vs-confidence tradeoff on one dataset, in plain steps.

    cd improving_glimpse/testing && ../../.venv/bin/python tradeoff_minimal.py

A stripped-down version of tradeoff.py + the benchmark harness, for reading.
It reproduces the Pima rows of overleaf/scripts/results/tradeoff_empirical.csv.
"""
import numpy as np
from scipy.stats import spearmanr
from sklearn.manifold import trustworthiness
from sklearn.model_selection import cross_val_predict
from sklearn.neighbors import KNeighborsRegressor

from lab import fit_glimpse

# 1. Data and model: 80/20 split, logistic regression fitted on the 80%.
g = fit_glimpse("pima", lens=None)
X_train, X_test = g.X[g.idx_tr], g.X[g.idx_te]
w = g.model.w                      # the model's weights = the direction it uses
score = g.model.logit(X_test)      # the model's score for each unseen person

# 2. The two ingredients, each scaled so its trace is 1.
spread = np.cov(X_train.T)         # how people are spread out
spread /= np.trace(spread)
model = np.outer(w, w)             # the model's direction
model /= w @ w


def eclipse_axes(lam):
    """Top two eigenvectors of the blend = the two axes of the map."""
    M = (1 - lam) * spread + lam * model + 1e-6 * spread
    vals, vecs = np.linalg.eigh(M)            # eigenvalues come out smallest first
    return vecs[:, [-1, -2]].T                # (2, d): the two largest


# 3. The two scores.
def keeps_neighbours(X, Z):
    """Trustworthiness: are your 10 nearest dots on the map your real neighbours?"""
    return trustworthiness(X, Z, n_neighbors=10)


def shows_confidence(Z, s):
    """Guess each person's score from their 15 nearest dots, then rank-correlate."""
    guess = cross_val_predict(KNeighborsRegressor(n_neighbors=15), Z, s, cv=5)
    return spearmanr(s, guess).statistic


# 4. Slide lambda from 0 (PCA) to 1 and score each map on the unseen people.
print(" lambda   trust   score_read")
for lam in np.linspace(0, 1, 21):
    A = eclipse_axes(lam)
    Z = (X_test - X_train.mean(axis=0)) @ A.T     # everyone's 2-D position
    print(f"  {lam:.2f}   {keeps_neighbours(X_test, Z):.4f}   "
          f"{shows_confidence(Z, score):.4f}")
