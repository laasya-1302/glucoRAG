"""Evaluate a trained GPFormer run, and show forecast cards (future glucose + HYPO/NORMAL/HYPER risk).

    python gp_eval.py --run_dir runs/gp_B --eval_set shanghai_t1d            # zero-shot test, Shanghai T1D
    python gp_eval.py --run_dir runs/gp_B --eval_set shanghai_t1d --demo 5   # also print 5 forecast cards
    python gp_eval.py --run_dir runs/gp_B --canonical cache/canonical/ohio.parquet --split zeroshot_test --name ohio

eval sets: shanghai_t1d (zero-shot), shanghai_t2d_val, replacebg_val, replacebg_test.
Prints and saves to run_dir/eval_<name>/: overall.csv, by_range.csv, risk.csv, coverage.csv, per_patient.csv.
Never touches a test set unless you ask for it by name.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from gp_data import (CANON, CLASSES, HORIZON_POS, HYPER, HYPO, PRED_LEN, SEQ_LEN, eval_windows, load_domains,
                     risk_class)
from gp_model import MEDIAN, QUANTILES, build_net, predict

EVAL_SETS = {"shanghai_t1d": ("shanghai.parquet", "zeroshot_test"), "shanghai_t2d_val": ("shanghai.parquet", "val"),
             "replacebg_val": ("replacebg.parquet", "val"), "replacebg_test": ("replacebg.parquet", "test")}


def r2(y, p):
    ss = ((y - y.mean()) ** 2).sum()
    return 1 - ((y - p) ** 2).sum() / ss if ss > 0 else float("nan")


def val_mae(net, W, norm, mark_dim, device):
    """Quick MAE (mg/dL) of the median forecast at 30/60/90/120 min."""
    q, _ = predict(net, W, norm, mark_dim, device)
    y = W["g"][:, SEQ_LEN:]
    return np.array([np.abs(q[:, p, MEDIAN] - y[:, p]).mean() for p in HORIZON_POS.values()])


def evaluate(net, W, norm, mark_dim, device, out_dir=None):
    q, probs = predict(net, W, norm, mark_dim, device)
    y, last = W["g"][:, SEQ_LEN:], W["g"][:, SEQ_LEN - 1]
    med, lo, hi = q[..., MEDIAN], np.minimum(q[..., 0], q[..., -1]), np.maximum(q[..., 0], q[..., -1])
    tr = risk_class(y)
    tables = {}

    rows = []
    for mins, p in HORIZON_POS.items():
        e, ep = med[:, p] - y[:, p], last - y[:, p]
        rows.append({"horizon": mins, "n": len(y), "MAE": np.abs(e).mean(), "RMSE": np.sqrt((e ** 2).mean()),
                     "R2": r2(y[:, p], med[:, p]), "persist_MAE": np.abs(ep).mean(),
                     "persist_RMSE": np.sqrt((ep ** 2).mean()), "persist_R2": r2(y[:, p], last),
                     "skill_MAE": 1 - np.abs(e).mean() / np.abs(ep).mean()})
    tables["overall"] = pd.DataFrame(rows)

    rows = []
    for label, a, b in (("<70", -np.inf, HYPO), ("70-180", HYPO, HYPER + 1e-9), (">180", HYPER + 1e-9, np.inf)):
        for mins, p in HORIZON_POS.items():
            m = (y[:, p] >= a) & (y[:, p] < b)
            if m.sum():
                rows.append({"true_range": label, "horizon": mins, "n": int(m.sum()),
                             "MAE": np.abs(med[m, p] - y[m, p]).mean(), "persist_MAE": np.abs(last[m] - y[m, p]).mean()})
    tables["by_range"] = pd.DataFrame(rows)

    rows = []
    for mins, p in HORIZON_POS.items():
        for who, pred in (("risk head", probs[:, p].argmax(-1)), ("median rule", risk_class(med[:, p])),
                          ("persistence rule", risk_class(last))):
            r = {"horizon": mins, "method": who, "accuracy": (pred == tr[:, p]).mean(),
                 "true_hypo": int((tr[:, p] == 0).sum()), "true_hyper": int((tr[:, p] == 2).sum())}
            for c, nm in ((0, "hypo"), (2, "hyper")):
                tp = int(((pred == c) & (tr[:, p] == c)).sum())
                r[f"{nm}_recall"] = tp / max((tr[:, p] == c).sum(), 1)
                r[f"{nm}_precision"] = tp / max((pred == c).sum(), 1)
                r[f"{nm}_false_alarms"] = int(((pred == c) & (tr[:, p] != c)).sum())
            rows.append(r)
    tables["risk"] = pd.DataFrame(rows)

    tables["coverage"] = pd.DataFrame([{"horizon": m, "coverage_10_90": ((y[:, p] >= lo[:, p]) & (y[:, p] <= hi[:, p])).mean(),
                                        "below_q10": (y[:, p] < lo[:, p]).mean(), "above_q90": (y[:, p] > hi[:, p]).mean(),
                                        "mean_band_width": (hi[:, p] - lo[:, p]).mean()}
                                       for m, p in HORIZON_POS.items()])

    rows = []
    for i, name in enumerate(W["names"]):
        m = W["dom"] == i
        if not m.any():
            continue
        r = {"patient": name, "n": int(m.sum())}
        for mins, p in HORIZON_POS.items():
            r[f"MAE_{mins}"] = np.abs(med[m, p] - y[m, p]).mean()
            r[f"persist_MAE_{mins}"] = np.abs(last[m] - y[m, p]).mean()
        r["skill_60"] = 1 - r["MAE_60"] / r["persist_MAE_60"]
        rows.append(r)
    tables["per_patient"] = pd.DataFrame(rows)

    if out_dir is not None:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        for k, t in tables.items():
            t.to_csv(Path(out_dir) / f"{k}.csv", index=False)
    return tables, (q, probs)


def print_tables(tables):
    pd.set_option("display.width", 200)
    print("== forecast error (mg/dL), median forecast vs persistence ==")
    print(tables["overall"].round(3).to_string(index=False))
    print("\n== error by true glucose range ==")
    print(tables["by_range"].round(2).to_string(index=False))
    print("\n== HYPO / HYPER detection (HYPO < 70, HYPER > 180) ==")
    print(tables["risk"].round(3).to_string(index=False))
    print("\n== 10%-90% forecast band (ideal coverage 0.80) ==")
    print(tables["coverage"].round(3).to_string(index=False))
    pp = tables["per_patient"]
    print(f"\n== per patient: {len(pp)} patients; model beats persistence at +60 min for "
          f"{int((pp.skill_60 > 0).sum())} of {len(pp)} ==")
    print(pp.round(2).to_string(index=False))


def forecast_cards(W, q, probs, n, seed=0, hypo_alert=0.3):
    """Print the output format: future glucose at 30/60/90/120 min + HYPO/NORMAL/HYPER risk."""
    rs = np.random.RandomState(seed)
    for i in rs.choice(len(W["g"]), size=min(n, len(W["g"])), replace=False):
        now = W["g"][i, SEQ_LEN - 1]
        hr = W["hour"][i, SEQ_LEN - 1]
        print("-" * 78)
        print(f"{W['names'][W['dom'][i]]}   time of day {int(hr):02d}:{int(round((hr % 1) * 60)) % 60:02d}   "
              f"glucose now: {now:.0f} mg/dL  ({CLASSES[int(risk_class(now))]})")
        print("   future glucose [10%-90% range]        risk (probabilities)                    actual")
        worst = ("NORMAL", None)
        for mins, p in HORIZON_POS.items():
            lo, md, hi = q[i, p, 0], q[i, p, MEDIAN], q[i, p, -1]
            pr = probs[i, p]
            label = CLASSES[int(pr.argmax())]
            print(f"   +{mins:3d} min  {md:5.0f} [{min(lo, hi):4.0f}-{max(lo, hi):4.0f}]      "
                  f"{label:7s} (hypo {pr[0]:4.0%} | normal {pr[1]:4.0%} | hyper {pr[2]:4.0%})   "
                  f"{W['g'][i, SEQ_LEN + p]:5.0f}")
            if pr[0] >= hypo_alert and worst[0] != "HYPO":
                worst = ("HYPO", mins)
            elif pr[2] >= 0.5 and worst[0] == "NORMAL":
                worst = ("HYPER", mins)
        msg = {"NORMAL": "NORMAL: no low or high glucose expected in the next 2 hours",
               "HYPO": f"HYPO RISK: low glucose possible by about +{worst[1]} min (alert level {hypo_alert:.0%})",
               "HYPER": f"HYPER RISK: high glucose likely by about +{worst[1]} min"}[worst[0]]
        print(f"   overall: {msg}")
    print("-" * 78)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run_dir", required=True)
    ap.add_argument("--eval_set", choices=list(EVAL_SETS), default=None)
    ap.add_argument("--canonical", default=None, help="custom canonical parquet (e.g. Ohio)")
    ap.add_argument("--split", default=None, help="split name inside the custom parquet")
    ap.add_argument("--name", default=None)
    ap.add_argument("--canon_dir", default=str(CANON))
    ap.add_argument("--max_windows", type=int, default=None)
    ap.add_argument("--demo", type=int, default=0, help="print this many forecast cards")
    ap.add_argument("--hypo_alert", type=float, default=0.3, help="probability at which a HYPO warning is raised")
    ap.add_argument("--repo", default=None)
    a = ap.parse_args()

    run = Path(a.run_dir)
    info = json.loads((run / "run_info.json").read_text())
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = build_net(a.repo or info["repo"], info["arch"], device=device)
    net.load_state_dict(torch.load(run / "best.pt", map_location=device, weights_only=False)["model"])
    net.eval()

    if a.canonical:
        path, split, name = a.canonical, a.split, a.name or Path(a.canonical).stem
    else:
        fname, split = EVAL_SETS[a.eval_set]
        path, name = Path(a.canon_dir) / fname, a.eval_set
    doms = [d for d in load_domains(path) if d.split == split]
    W = eval_windows(doms, a.max_windows, seed=0)
    print(f"{name}: {len(doms)} patients, {len(W['g'])} windows | model: {run} | normalization from training only "
          f"(mean {info['norm']['mean']:.1f}, std {info['norm']['std']:.1f})\n")

    tables, (q, probs) = evaluate(net, W, info["norm"], info["mark_dim"], device, run / f"eval_{name}")
    print_tables(tables)
    if a.demo:
        print("\n== forecast cards (illustrative windows from this set) ==")
        forecast_cards(W, q, probs, a.demo, hypo_alert=a.hypo_alert)


if __name__ == "__main__":
    main()
