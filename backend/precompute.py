"""Precompute the fitted models and ECLIPSE lenses used in production."""
import os
import sys
import pickle
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine")
sys.path.insert(0, ENGINE)
import cf_core  # noqa: E402   

EPS = 0.03
OUT = os.path.join(ENGINE, "precomputed")
os.makedirs(OUT, exist_ok=True)


def main():
    import numpy, scipy, sklearn, contourpy
    print(f"env: numpy {numpy.__version__}  scipy {scipy.__version__}  "
          f"scikit-learn {sklearn.__version__}  contourpy {contourpy.__version__}")
    print("pin these versions in requirements.txt\n")
    for d in cf_core.DATASETS:
        key = d["key"]
        t0 = time.time()
        print(f"fitting {key} ...", flush=True)
        m = cf_core._models(key, EPS)
        lens = cf_core._lens(key, EPS)
        path = os.path.join(OUT, f"{key}_{round(float(EPS), 6)}.pkl")
        with open(path, "wb") as f:
            pickle.dump({"m": m, "lens": lens}, f, protocol=4)
        kb = os.path.getsize(path) // 1024
        print(f"  saved {os.path.relpath(path, HERE)}  ({kb} KB, {time.time() - t0:.1f}s)")
    print("\ndone. commit engine/precomputed/*.pkl and deploy.")


if __name__ == "__main__":
    main()
