# testing/

Research on GLIMPSE that is not part of the app: whether ECLIPSE is the right
projection, attempts to beat it, the distance–confidence tradeoff, and the write-ups.

Everything here runs on **the app's own engine** (`../backend/engine/`), so the research and
the tool can never drift apart. `lab.py` is the only bridge: it re-exports the app's
maths and adds the few things the app itself does not need — fixed-weight ECLIPSE
fits, the κ₂ ceiling, the four extra datasets, and `fit_glimpse(key)`.

```
testing/
├── lab.py                 bridge to ../backend/engine (replaces the old glimpse_min/)
├── alternative_projection_testing.ipynb   the 13-method study (executed)
├── projections.py         13 competing methods behind one interface
├── metrics.py             readout metrics (all methods) + inverse metrics (decoders only)
├── benchmark.py           the train/test sweep and the summary tables
├── variants.py            three candidate improvements to ECLIPSE + term ablations
├── gaussian.py            the "p(y|x) comes from a Gaussian" tools
├── tradeoff.py            the distance–confidence tradeoff (frontier + λ sweep)
├── tradeoff_minimal.py    the same tradeoff in ~40 readable lines, one dataset
├── viz.py                 figures (validated colourblind-safe palette)
├── datasets/              german, heart, spambase, taiwan (pima/heloc come from the app)
├── figures/  results/     generated
└── *.tex                  plain-language write-ups
```

## Run it

```bash
cd improving_glimpse/testing

# smoke test: GLIMPSE on all 7 datasets
../../.venv/bin/python lab.py

# the tradeoff on one dataset
../../.venv/bin/python tradeoff_minimal.py

# the full notebook
../../.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
    alternative_projection_testing.ipynb
```

Uses the repo-root `.venv` (latest libraries). The app itself uses the pinned
`improving_glimpse/.venv`; research code never loads the app's precomputed pickles,
so the version difference does not matter here.

Requires numpy, scipy, scikit-learn, pandas, matplotlib, torch, umap-learn, pacmap —
all already in the repo-root `.venv`.

## What the notebook found

Thirteen methods (PCA, Random, LDA, PLS, NCA, KernelPCA, Isomap, t-SNE, UMAP, PaCMAP,
Autoencoder, SAE, ECLIPSE) on seven datasets, fitted on train and scored on held-out test.

- **ECLIPSE has the best mean rank overall (5.02 of 13)** and the best `score_read`
  (0.982) and `sep2d` (0.847).
- vs PCA: `score_read` **+0.133**, `sep2d` +0.034, `rash_read` +0.018, `trust` −0.024
  — inside the `TAU = 0.05` budget the auto rule is allowed to spend.
- **Capability disqualifies more methods than quality does.** t-SNE has the best
  neighbourhood scores in the table and cannot place a new person. Isomap and PaCMAP
  cannot run backwards. Only 10 of 13 are usable by GLIMPSE at all; only 6 are linear.
- **`ECLIPSE-ceil`** (use `kappa_2` instead of the validation sweep) matches the auto
  rule to within noise at **0.002 s vs 0.344 s — ~170× faster**. Best practical win,
  especially for serverless cold starts.
- **`ECLIPSE-suff`** (pin axis 1 to `w`) gives `score_inv` = **1.000 on all seven
  datasets** vs 0.997, confirming the Gaussian sufficiency argument exactly.
- **`ECLIPSE-gen`** (generalised eigenproblem `Mv = λΣv`) is a clear **negative
  result**: `score_read` collapses to 0.547. Recorded so it is not retried.
- Honest caveat: on `rash_read` KernelPCA leads (0.708 vs ECLIPSE's 0.539) — but its
  `rash_inv` is 0.169, the worst in the table, so its decoder is unfaithful and it
  could not drive the counterfactual panel.

## The "p(y|x) comes from a Gaussian" question

Section 6 of the notebook. Short version: if the two outcome groups are Gaussian with a
**shared** covariance, the quadratic terms cancel in Bayes' rule and the log-odds is
*exactly* linear, `w = Σ⁻¹(μ₁ − μ₀)`. So logistic regression is not an approximation —
it is the truth under that model. Two consequences that matter:

1. It **licenses the straight boundary** GLIMPSE draws.
2. `w'x` is a **sufficient statistic** — all outcome information is on one axis — so a
   second outcome axis is provably empty. That is the design argument for ECLIPSE's
   "axis 1 = score, axis 2 = something else", and for why LDA giving only one
   discriminant direction is correct rather than limiting.

Break the shared covariance and the log-odds becomes quadratic; the notebook simulates
this and shows `cost_of_linear` jumping from −0.02 to +0.10. A separate Gaussian — the
Laplace approximation over *parameters* — is what makes the Rashomon set an ellipsoid.
The two are distinguished explicitly in §6.4.

## Still open

No user study. `rash_read` is a k-NN readout and rewards smooth spatial structure. The
autoencoders got one fixed architecture and no tuning. `ECLIPSE-suff` and `ECLIPSE-ceil`
both deserve paired multi-seed CV before either replaces the shipped rule.
