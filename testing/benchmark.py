"""Fit every method on every dataset and score them on a held-out split.

The protocol is deliberately strict: each lens is fitted on the TRAIN half
only and every number is computed on the TEST half.  That is the setting
GLIMPSE actually runs in -- a person types their own numbers in and has to be
placed on a map that was built without them.
"""
import traceback
import warnings

import numpy as np
import pandas as pd

from lab import fit_glimpse
from lab import evaluate
from lab import rash_ceiling
from metrics import evaluate_projection
from projections import all_methods


def _cap(idx, cap, seed=0):
    if cap is None or len(idx) <= cap:
        return idx
    return np.sort(np.random.default_rng(seed).choice(idx, cap, replace=False))


def run_dataset(key, methods=None, eps=0.03, verbose=True, transductive=True,
                max_train=2500, max_test=1200):
    """Score every method on one dataset.  Returns a DataFrame.

    ``transductive=True`` gives a method with no out-of-sample map (t-SNE) a
    second chance: refit it directly on the evaluation set and score it there.
    Those rows are flagged 'in-sample only' -- they are an upper bound the
    method could never deliver in the live tool, and should be read that way.
    """
    g = fit_glimpse(key, eps=eps, lens=None)
    ctx = {"w": g.model.w, "ell": g.ell,
           "mask": getattr(g.data, "missing_mask", None)}
    # The model and the Rashomon set are always fitted on the FULL train half;
    # only the lens-fitting / scoring sets are capped, to keep UMAP & friends
    # tractable on the bigger datasets.
    itr, ite = _cap(g.idx_tr, max_train), _cap(g.idx_te, max_test)
    Xtr, ytr = g.X[itr], g.y[itr]
    Xte, yte = g.X[ite], g.y[ite]
    if ctx["mask"] is not None:
        ctx["mask"] = ctx["mask"][itr]

    acc, auc = evaluate(g.model, Xte, yte)
    if verbose:
        print(f"\n=== {g.data.name}  (n={g.data.n}, d={g.data.d})  "
              f"test acc {acc:.3f} / AUC {auc:.3f}  "
              f"kappa2 {rash_ceiling(Xtr, g.ell):.3f} ===")

    rows = []
    for proj in (methods or all_methods()):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                proj.fit(Xtr, ytr, ctx)
                r = evaluate_projection(proj, Xte, yte, g.model, g.ell)
        except Exception as e:                            # noqa: BLE001
            if verbose:
                print(f"  {proj.name:12s} FAILED: {type(e).__name__}: {e}")
                traceback.print_exc(limit=1)
            continue

        if transductive and not proj.caps.out_of_sample:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                proj.fit(Xte, yte, ctx)      # refit ON the eval set
                r = evaluate_projection(proj, Xte, yte, g.model, g.ell)
            r["note"] = "in-sample only (refit); cannot place a new person"
        r["dataset"] = key
        rows.append(r)
        if verbose:
            print(f"  {r['method']:12s} trust {r['trust']:.3f}  "
                  f"sep2d {r['sep2d']:.3f}  score {r['score_read']:.3f}  "
                  f"rash {r['rash_read']:.3f}  ({r['fit_s']:.1f}s) {r['note']}")
    cols = ["dataset", "method", "trust", "sep2d", "score_read", "rash_read",
            "recon", "rt", "score_inv", "rash_inv", "linear", "supervised",
            "invertible", "out_of_sample", "model_aware", "fit_s", "note"]
    return pd.DataFrame(rows)[cols]


def run_all(keys, methods_factory=all_methods, eps=0.03, verbose=True, **kw):
    """Sweep several datasets.  A fresh method instance per dataset."""
    out = []
    for k in keys:
        try:
            out.append(run_dataset(k, methods_factory(), eps=eps, verbose=verbose,
                                   **kw))
        except Exception as e:                            # noqa: BLE001
            print(f"[{k}] skipped: {type(e).__name__}: {e}")
    return pd.concat(out, ignore_index=True)


def summarize(df, metric):
    """Datasets as columns, methods as rows, for one metric."""
    t = df.pivot_table(index="method", columns="dataset", values=metric,
                       dropna=False)
    # Keep the canonical roster order, then anything else (variants, ablations)
    # in the order it first appeared -- never silently drop a row.
    known = [m.name for m in all_methods() if m.name in t.index]
    extra = [m for m in df["method"].drop_duplicates()
             if m in t.index and m not in known]
    t = t.loc[known + extra]
    t["mean"] = t.mean(axis=1, skipna=True)
    return t.round(3)


def rank_table(df, metrics=("trust", "sep2d", "score_read", "rash_read")):
    """Mean rank per method across datasets (1 = best).  Lower is better."""
    parts = []
    for m in metrics:
        r = df.pivot_table(index="method", columns="dataset", values=m)
        parts.append(r.rank(ascending=False, axis=0).mean(axis=1).rename(m))
    out = pd.concat(parts, axis=1)
    out["mean_rank"] = out.mean(axis=1)
    return out.sort_values("mean_rank").round(2)
