"""Figures for the projection comparison.

Palette: two categorical hues (#2563eb / #ea580c), validated colourblind-safe
(worst adjacent CVD dE 31.3, normal-vision dE 39.6, contrast >= 3:1).  Continuous
fields use a single-hue light-to-dark ramp built from those same two hues --
never a rainbow.
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from lab import disagreement

CLASS_COLORS = ("#2563eb", "#ea580c")
INK, MUTED, GRID = "#1f2328", "#6b7280", "#e5e7eb"


def seq_cmap(hex_color, name="seq"):
    """A one-hue sequential ramp: near-white to the full hue."""
    return LinearSegmentedColormap.from_list(name, ["#f2f4f8", hex_color])


SCORE_CMAP = seq_cmap(CLASS_COLORS[0], "score")
RASH_CMAP = seq_cmap(CLASS_COLORS[1], "rash")


def _clean(ax, title, sub=None):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.set_title(title, fontsize=10, color=INK, pad=3)
    if sub:
        ax.set_xlabel(sub, fontsize=7.5, color=MUTED, labelpad=2)


def _fit_all(methods, Xtr, ytr, ctx):
    """Fit each method, returning (method, error-or-None)."""
    import warnings
    out = []
    for m in methods:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m.fit(Xtr, ytr, ctx)
            out.append((m, None))
        except Exception as e:                       # noqa: BLE001
            out.append((m, f"{type(e).__name__}"))
    return out


def scatter_grid(fitted, X, y, model=None, ell=None, color_by="class",
                 class_names=("class 0", "class 1"), title="", ncols=5,
                 scores=None, out=None):
    """One panel per method, all showing the same people.

    color_by: 'class'  -- the two outcome groups
              'score'  -- the model's log-odds
              'rash'   -- how much equally-good models disagree
    """
    n = len(fitted)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(2.55 * ncols, 2.75 * nrows))
    axes = np.atleast_1d(axes).ravel()

    if color_by == "score":
        c, cmap, lab = model.logit(X), SCORE_CMAP, "model score (log-odds)"
    elif color_by == "rash":
        c, cmap, lab = disagreement(ell, X), RASH_CMAP, "disagreement between good models"
    else:
        c, cmap, lab = None, None, None

    # Clip the colour scale at the 2nd/98th percentile so a couple of extreme
    # people do not flatten the whole field to one pale tint.
    vlim = (float(np.percentile(c, 2)), float(np.percentile(c, 98))) if c is not None else (None, None)

    sc = None
    for ax, (m, err) in zip(axes, fitted):
        if err is not None:
            _clean(ax, m.name); ax.text(.5, .5, err, ha="center", va="center",
                                        color=MUTED, fontsize=8,
                                        transform=ax.transAxes)
            continue
        try:
            Z = m.embed(X)
        except NotImplementedError:
            _clean(ax, m.name)
            ax.text(.5, .5, "cannot place\nnew people", ha="center", va="center",
                    color=MUTED, fontsize=8, transform=ax.transAxes)
            continue
        if color_by == "class":
            for k in (0, 1):
                ax.scatter(Z[y == k, 0], Z[y == k, 1], s=9, lw=.4,
                           edgecolor="white", c=CLASS_COLORS[k], alpha=.85,
                           label=class_names[k])
        else:
            sc = ax.scatter(Z[:, 0], Z[:, 1], s=11, c=c, cmap=cmap, lw=.4,
                            edgecolor="white", alpha=.95,
                            vmin=vlim[0], vmax=vlim[1])
        sub = None
        if scores is not None and m.name in scores.index:
            r = scores.loc[m.name]
            sub = f"trust {r.trust:.2f} · score {r.score_read:.2f} · rash {r.rash_read:.2f}"
        _clean(ax, m.name, sub)
    for ax in axes[n:]:
        ax.axis("off")

    if color_by == "class":
        h = [plt.Line2D([], [], marker="o", ls="", color=CLASS_COLORS[k],
                        markersize=7, label=class_names[k]) for k in (0, 1)]
        fig.legend(handles=h, loc="lower center", ncol=2, frameon=False,
                   fontsize=9.5, bbox_to_anchor=(.5, -0.055))
    elif sc is not None:
        cax = fig.add_axes([0.25, -0.055, 0.5, 0.016])
        cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
        cb.set_label(lab, fontsize=9, color=MUTED)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=7.5, colors=MUTED, length=0)

    fig.suptitle(title, fontsize=12.5, fontweight="bold", color=INK, y=1.005)
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    return fig


def boundary_grid(fitted, X, y, model, class_names=("class 0", "class 1"),
                  title="", ncols=5, res=140, out=None):
    """What the classifier's decision boundary looks like THROUGH each lens.

    The same code runs for every method: grid the plane, send each grid point
    back to feature space with the lens's own inverse, ask the model.  Linear
    lenses return a straight line because they must; the others do not.
    """
    n = len(fitted)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(2.55 * ncols, 2.75 * nrows))
    axes = np.atleast_1d(axes).ravel()

    for ax, (m, err) in zip(axes, fitted):
        _clean(ax, m.name)
        if err is not None or not m.caps.invertible:
            try:
                Z = m.embed(X)
                for k in (0, 1):
                    ax.scatter(Z[y == k, 0], Z[y == k, 1], s=7, lw=.3,
                               edgecolor="white", c=CLASS_COLORS[k], alpha=.55)
            except Exception:                        # noqa: BLE001
                pass
            ax.text(.5, .04, "no inverse — no boundary can be drawn",
                    ha="center", fontsize=7.5, color=MUTED,
                    transform=ax.transAxes)
            continue

        Z = m.embed(X)
        pad = .08
        (x0, y0), (x1, y1) = Z.min(0), Z.max(0)
        dx, dy = (x1 - x0) * pad, (y1 - y0) * pad
        xs = np.linspace(x0 - dx, x1 + dx, res)
        ys = np.linspace(y0 - dy, y1 + dy, res)
        XX, YY = np.meshgrid(xs, ys)
        grid = np.column_stack([XX.ravel(), YY.ravel()])
        P = model.proba(m.invert(grid)).reshape(XX.shape)
        ax.contourf(XX, YY, P, levels=np.linspace(0, 1, 21), cmap=SCORE_CMAP,
                    alpha=.55)
        ax.contour(XX, YY, P, levels=[.5], colors=[INK], linewidths=1.6)
        for k in (0, 1):
            ax.scatter(Z[y == k, 0], Z[y == k, 1], s=7, lw=.3,
                       edgecolor="white", c=CLASS_COLORS[k], alpha=.75)
        ax.set_xlim(xs[0], xs[-1]); ax.set_ylim(ys[0], ys[-1])
        ax.set_xlabel("straight" if m.caps.linear else "curved",
                      fontsize=7.5, color=MUTED, labelpad=2)
    for ax in axes[n:]:
        ax.axis("off")

    h = [plt.Line2D([], [], marker="o", ls="", color=CLASS_COLORS[k],
                    markersize=7, label=class_names[k]) for k in (0, 1)]
    h.append(plt.Line2D([], [], color=INK, lw=1.6, label="decision boundary"))
    fig.legend(handles=h, loc="lower center", ncol=3, frameon=False,
               fontsize=9.5, bbox_to_anchor=(.5, -0.055))
    fig.suptitle(title, fontsize=12.5, fontweight="bold", color=INK, y=1.005)
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    return fig


def metric_bars(table, metric, help_text="", out=None, higher_better=True):
    """Per-method mean of one metric, sorted, with the mean labelled."""
    s = table["mean"].dropna().sort_values(ascending=not higher_better)
    fig, ax = plt.subplots(figsize=(7.2, .34 * len(s) + 1.1))
    colors = [CLASS_COLORS[0] if "ECLIPSE" not in i else CLASS_COLORS[1]
              for i in s.index]
    ax.barh(range(len(s)), s.values, color=colors, height=.62)
    ax.set_yticks(range(len(s)))
    ax.set_yticklabels(s.index, fontsize=9, color=INK)
    ax.invert_yaxis()
    for i, v in enumerate(s.values):
        ax.text(v, i, f" {v:.3f}", va="center", fontsize=8.5, color=MUTED)
    ax.set_xlabel(help_text or metric, fontsize=9, color=MUTED)
    ax.tick_params(axis="x", labelsize=8, colors=MUTED, length=0)
    ax.grid(axis="x", color=GRID, lw=.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_title(f"{metric} — mean across datasets", fontsize=11.5,
                 fontweight="bold", color=INK, loc="left")
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    return fig
