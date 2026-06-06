"""Controller validation: baseline runs-model vs the blended (runs + team-strength
prior) model, across MULTIPLE seasons, with a blend-weight sweep.

The point is to pick a blend weight that helps ROBUSTLY across seasons (not one
overfit to a single year), and to confirm the improvement holds out of sample.

Run: PYTHONPATH=src python3 scripts/validate_improved.py
"""
from __future__ import annotations

from algoball.backtest import Prediction, build_components, _accuracy, _brier, _log_loss
from algoball.model.strength import blend

# (predict_season, feature_season, end_date)
SEASONS = [
    (2024, 2023, None),
    (2025, 2024, None),
    (2026, 2025, "2026-04-30"),
]
WEIGHTS = [0.0, 0.3, 0.4, 0.5, 0.6]


def evaluate(comps, w):
    preds = [Prediction(p_home=blend(c["p_runs"], c["p_prior"], w), home_won=c["home_won"]) for c in comps]
    return _accuracy(preds), _brier(preds), _log_loss(preds)


def main():
    all_comps = []
    print("=" * 78)
    print("BASELINE (w=0.0) vs BLENDED runs+team-strength prior — by season")
    print("=" * 78)
    for ps, fs, ed in SEASONS:
        comps = build_components(ps, fs, ed)
        all_comps.extend(comps)
        label = f"{ps}" + (f" thru {ed}" if ed else " full")
        print(f"\n{label}  (features {fs}, n={len(comps)})")
        print(f"  {'weight':>8}{'acc':>9}{'Brier':>10}{'logLoss':>10}")
        base_b = None
        for w in WEIGHTS:
            acc, br, ll = evaluate(comps, w)
            if w == 0.0:
                base_b = br
            tag = "  (baseline)" if w == 0.0 else (f"  dBrier {br - base_b:+.4f}" if base_b else "")
            print(f"  {w:>8.2f}{acc:>9.4f}{br:>10.5f}{ll:>10.5f}{tag}")

    print("\n" + "=" * 78)
    print(f"POOLED across all seasons (n={len(all_comps)})")
    print("=" * 78)
    print(f"  {'weight':>8}{'acc':>9}{'Brier':>10}{'logLoss':>10}")
    base_b = None
    best = None
    for w in WEIGHTS:
        acc, br, ll = evaluate(all_comps, w)
        if w == 0.0:
            base_b = br
        tag = "  (baseline)" if w == 0.0 else f"  dBrier {br - base_b:+.4f}"
        print(f"  {w:>8.2f}{acc:>9.4f}{br:>10.5f}{ll:>10.5f}{tag}")
        if best is None or ll < best[1]:
            best = (w, ll, br, acc)
    print(f"\nbest pooled log loss at weight {best[0]:.2f}: logLoss {best[1]:.5f}, Brier {best[2]:.5f}, acc {best[3]:.4f}")


if __name__ == "__main__":
    main()
