"""Logistic models, Rashomon ellipsoids, and counterfactual search."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression


def _sigmoid(z):
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)),
                    np.exp(z) / (1.0 + np.exp(z)))


@dataclass
class LinearModel:
    """A logistic regression model used by ElliCE."""
    clf: LogisticRegression
    w: np.ndarray
    b: float

    @property
    def theta(self):
        """Return the model parameters with the intercept last."""
        return np.concatenate([self.w, [self.b]])

    def logit(self, X):
        return np.atleast_2d(X) @ self.w + self.b

    def proba(self, X):
        return _sigmoid(self.logit(X))


def train_logreg(X, y, C=1.0, random_state=0):
    """Fit an L2-regularized logistic regression."""
    clf = LogisticRegression(C=C, max_iter=5000, random_state=random_state)
    clf.fit(X, y)
    return LinearModel(clf, clf.coef_.ravel().astype(np.float64),
                       float(clf.intercept_[0]))


class RashomonEllipsoid:
    """Ellipsoidal approximation of the eps-Rashomon set for a linear model."""

    def __init__(self, X, theta, eps=0.02, reg=1e-4):
        """Build the ellipsoid from standardized features and model parameters."""
        self.theta = np.asarray(theta, float)
        self.eps = float(eps)
        self.w, self.b = self.theta[:-1], self.theta[-1]

        Xa = np.hstack([X, np.ones((X.shape[0], 1))])
        p = _sigmoid(Xa @ self.theta)
        W = p * (1.0 - p)
        n, m = Xa.shape
        H = (Xa * W[:, None]).T @ Xa / n + reg * np.eye(m)

        self.Q = H / (2.0 * self.eps)
        self.Q_inv_sqrt = _inv_sqrt(self.Q)
        self.m = m

        # Exclude the intercept from the feature-space curvature block.
        self.H_xx = H[:-1, :-1]
        self.H_xx_inv = np.linalg.inv(self.H_xx)

    def robust_logit(self, X, target_class=1):
        """Return the worst-case signed margin toward the target class."""
        s = 1.0 if target_class == 1 else -1.0
        Xa = _aug(X)
        center = Xa @ self.theta
        penalty = np.linalg.norm(Xa @ self.Q_inv_sqrt, axis=1)
        return s * center - penalty

    def worst_model(self, x, target_class=1):
        """Return the least-favourable model for one input."""
        xa = np.append(np.asarray(x, float), 1.0)
        u = self.Q_inv_sqrt @ xa
        nu = np.linalg.norm(u)
        if nu < 1e-12:
            return self.theta.copy()
        s = 1.0 if target_class == 1 else -1.0
        return self.theta - s * (self.Q_inv_sqrt @ u) / nu

    def sample_models(self, k, random_state=0):
        """Draw parameter vectors uniformly from the ellipsoid."""
        rng = np.random.default_rng(random_state)
        u = rng.standard_normal((k, self.m))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        r = rng.random((k, 1)) ** (1.0 / self.m)
        return (self.Q_inv_sqrt @ (u * r).T).T + self.theta

    def standard_cf(self, x0, target_class=1, t=0.0, margin=0.0,
                    hessian_reg=False, fixed=None):
        """Return the closest point that flips the fitted model."""
        x0 = np.asarray(x0, float)
        s = 1.0 if target_class == 1 else -1.0
        target_logit = t + s * margin
        logit = self.w @ x0 + self.b
        if s * (target_logit - logit) <= 0:
            return x0.copy()
        if hessian_reg:
            step_dir = self.H_xx_inv @ self.w
            return x0 + (target_logit - logit) / (self.w @ step_dir) * step_dir
        if fixed is not None:
            wf = self.w * (~np.asarray(fixed, bool))
            denom = float(wf @ wf)
            if denom < 1e-12:
                return x0.copy()
            return x0 + (target_logit - logit) / denom * wf
        return x0 + (target_logit - logit) / (self.w @ self.w) * self.w

    def robust_cf(self, x0, target_class=1, t=0.0, margin=0.0,
                  hessian_reg=False, fixed=None):
        """Return the closest point with the requested worst-case margin."""
        x0 = np.asarray(x0, float)
        s = 1.0 if target_class == 1 else -1.0

        def con(x):
            return self.robust_logit(x, target_class)[0] - margin

        def con_grad(x):
            xa = np.append(x, 1.0)
            g = self.Q_inv_sqrt @ xa
            ng = np.linalg.norm(g)
            return s * self.w - (self.Q_inv_sqrt @ g / max(ng, 1e-12))[:-1]

        if hessian_reg:
            obj = lambda x: float((x - x0) @ self.H_xx @ (x - x0))
            jac = lambda x: 2.0 * self.H_xx @ (x - x0)
        else:
            obj = lambda x: np.sum((x - x0) ** 2)
            jac = lambda x: 2.0 * (x - x0)

        bnds = None
        if fixed is not None:
            fixed = np.asarray(fixed, bool)
            bnds = [(x0[j], x0[j]) if fixed[j] else (None, None)
                    for j in range(len(x0))]

        x_init = self.standard_cf(x0, target_class, t, margin, hessian_reg, fixed)
        res = minimize(obj, x_init, jac=jac, method="SLSQP", bounds=bnds,
                       constraints=[{"type": "ineq", "fun": con, "jac": con_grad}],
                       options={"maxiter": 200, "ftol": 1e-9})
        return res.x


def _aug(X):
    X = np.atleast_2d(np.asarray(X, float))
    return np.hstack([X, np.ones((X.shape[0], 1))])


def _inv_sqrt(Q, ridge=1e-6):
    """Symmetric inverse square root via eigendecomposition."""
    w, V = np.linalg.eigh(Q + ridge * np.eye(Q.shape[0]))
    return (V * np.clip(w, ridge, None) ** -0.5) @ V.T
