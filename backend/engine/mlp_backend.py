"""Neural-network backend with an ElliCE last-layer split."""
import numpy as np
from scipy.optimize import minimize
from sklearn.neural_network import MLPClassifier

from counterfactuals import RashomonEllipsoid, _sigmoid

N_BISECT = 40


class MLPBackend:
    """A one-layer tanh MLP with an ElliCE last-layer ellipsoid."""

    def __init__(self, X, y, eps=0.03, hidden=16, alpha=1e-3, random_state=0):
        self.clf = MLPClassifier(hidden_layer_sizes=(hidden,), activation="tanh",
                                 alpha=alpha, max_iter=4000,
                                 random_state=random_state)
        self.clf.fit(X, y)
        self.W1 = self.clf.coefs_[0]
        self.b1 = self.clf.intercepts_[0]
        self.w2 = self.clf.coefs_[1].ravel()
        self.b2 = float(self.clf.intercepts_[1][0])

        self.theta = np.concatenate([self.w2, [self.b2]])
        self.H_train = self.embed_h(X)
        self.ell = RashomonEllipsoid(self.H_train, self.theta, eps=eps)

        self.X_train = np.asarray(X, float)
        self.y_train = np.asarray(y, int)

    def embed_h(self, X):
        """Penultimate embedding h(x) = tanh(x W1 + b1)."""
        return np.tanh(np.atleast_2d(np.asarray(X, float)) @ self.W1 + self.b1)

    def logit(self, X):
        return self.embed_h(X) @ self.w2 + self.b2

    def proba(self, X):
        return _sigmoid(self.logit(X))

    def robust_logit(self, X, target_class=1):
        return self.ell.robust_logit(self.embed_h(X), target_class)

    def worst_model(self, x, target_class=1):
        """Return the worst last-layer parameters for one input."""
        return self.ell.worst_model(self.embed_h(x)[0], target_class)

    def logit_of_theta(self, theta, X):
        """Evaluate a last-layer parameter vector."""
        H = self.embed_h(X)
        return H @ theta[:-1] + theta[-1]

    def _h_and_dtanh(self, x):
        h = np.tanh(x @ self.W1 + self.b1)
        return h, 1.0 - h * h

    def _logit_grad(self, x):
        h, dt = self._h_and_dtanh(x)
        return self.W1 @ (dt * self.w2)

    def _robust_grad(self, x, target_class):
        """d/dx [ s * logit(x) - ||Q^{-1/2} h_aug(x)|| ]."""
        s = 1.0 if target_class == 1 else -1.0
        h, dt = self._h_and_dtanh(x)
        ha = np.append(h, 1.0)
        u = self.ell.Q_inv_sqrt @ ha
        g = self.ell.Q_inv_sqrt @ u / max(np.linalg.norm(u), 1e-12)
        return s * self.W1 @ (dt * self.w2) - self.W1 @ (dt * g[:-1])

    def _feasible_init(self, x0, cfun, fixed=None):
        """Find a feasible start along the nearest valid training direction."""
        vals = cfun(self.X_train)
        feas = np.where(vals > 1e-6)[0]
        if len(feas) == 0:
            return None
        anchor = self.X_train[feas[np.argmin(
            np.linalg.norm(self.X_train[feas] - x0, axis=1))]].copy()
        if fixed is not None:
            anchor[fixed] = x0[fixed]
        lo, hi = 0.0, 1.0
        for _ in range(N_BISECT):
            mid = 0.5 * (lo + hi)
            if cfun(x0 + mid * (anchor - x0))[0] > 0:
                hi = mid
            else:
                lo = mid
        return x0 + hi * (anchor - x0)

    def _closest_feasible(self, x0, cfun, cgrad, fixed=None):
        """Find the closest feasible input, optionally fixing selected fields."""
        x0 = np.asarray(x0, float)
        if cfun(x0)[0] >= 0:
            return x0.copy()
        x_init = self._feasible_init(x0, cfun, fixed=fixed)
        if x_init is None:
            return x0.copy()
        bnds = None
        if fixed is not None:
            fixed = np.asarray(fixed, bool)
            bnds = [(x0[j], x0[j]) if fixed[j] else (None, None)
                    for j in range(len(x0))]
        res = minimize(lambda x: np.sum((x - x0) ** 2), x_init,
                       jac=lambda x: 2.0 * (x - x0), method="SLSQP", bounds=bnds,
                       constraints=[{"type": "ineq",
                                     "fun": lambda x: cfun(x[None, :])[0],
                                     "jac": cgrad}],
                       options={"maxiter": 300, "ftol": 1e-9})
        if res.success and cfun(res.x[None, :])[0] > -1e-6 and \
                np.linalg.norm(res.x - x0) <= np.linalg.norm(x_init - x0) + 1e-9:
            return res.x
        return x_init

    def standard_cf(self, x0, target_class=0, margin=0.0, fixed=None):
        """Return the closest input that flips the fitted MLP."""
        s = 1.0 if target_class == 1 else -1.0
        cfun = lambda X: s * self.logit(X) - margin
        cgrad = lambda x: s * self._logit_grad(x)
        return self._closest_feasible(x0, cfun, cgrad, fixed=fixed)

    def robust_cf(self, x0, target_class=0, margin=0.0, fixed=None):
        """Return the closest input whose worst-case logit clears the threshold."""
        cfun = lambda X: self.robust_logit(X, target_class) - margin
        cgrad = lambda x: self._robust_grad(x, target_class)
        return self._closest_feasible(x0, cfun, cgrad, fixed=fixed)
