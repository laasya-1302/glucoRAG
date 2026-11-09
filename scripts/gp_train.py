"""Train GPFormer with its original MLDG meta-learning loop + HYPO/NORMAL/HYPER head. Resumable.

    python gp_train.py --selftest                                   # checks the real model + `higher`, times an iteration
    python gp_train.py --sources replacebg --run_dir runs/gp_A       # Experiment A: REPLACE-BG T1D only
    python gp_train.py --sources replacebg,shanghai_t2d --run_dir runs/gp_B    # Experiment B: + Shanghai T2D

Every epoch = iters_per_epoch iterations (500, as in the original run.sh). The full state is saved to Drive after
every epoch; after a disconnect run the SAME command again (same settings, including --epochs) and it continues.
Changing any setting starts a new run: use a new --run_dir. (The learning-rate schedule depends on --epochs.)
Zero-shot test sets (Shanghai T1D, Ohio) are never read here.
"""
import argparse
import json
import random
import time
from pathlib import Path

import higher
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from gp_data import CANON, DomainSampler, eval_windows, fit_scaler, load_domains
from gp_eval import val_mae
from gp_model import build_net, class_weights, detect_mark_dim, task_loss, to_tensors
from resume_utils import Checkpointer


def train_step(net, opt, sched, b, a, cls_w):
    """One MLDG iteration, as in the original main.py: support patients drive an inner SGD step, the outer
    loss = loss on support patients (original weights) + trade_off * loss on query patients (inner weights)."""
    n, P = a.n_support + a.n_query, a.per_domain
    sup = sorted(random.sample(range(n), a.n_support))
    qry = [i for i in range(n) if i not in set(sup)]
    ix = lambda L: torch.cat([torch.arange(i * P, (i + 1) * P) for i in L]).to(b["x"].device)
    S, Q = ix(sup), ix(qry)
    s = {k: v[S] for k, v in b.items()}
    q = {k: v[Q] for k, v in b.items()}
    opt.zero_grad()
    with higher.innerloop_ctx(net, opt, copy_initial_weights=False) as (inner, diffopt):
        for _ in range(a.inner_iters):
            loss_in, _, _ = task_loss(inner, s, cls_w, a.risk_lambda)
            diffopt.step(loss_in)
        loss_sup, _, _ = task_loss(net, s, cls_w, a.risk_lambda)
        loss_q, ql_q, ce_q = task_loss(inner, q, cls_w, a.risk_lambda)
        loss_outer = loss_sup + a.trade_off * loss_q
    loss_outer.backward()
    opt.step()
    sched.step()
    return loss_outer.item(), ql_q.item(), ce_q.item()


def selftest(a, device):
    print(f"device={device} | building the ORIGINAL GPFormer from {a.repo}")
    net = build_net(a.repo, vars(a), device=device)
    print("parameters:", sum(p.numel() for p in net.parameters()))
    d = detect_mark_dim(net, device)
    print("time-feature columns accepted by the model's embedding:", d)
    norm = {"mean": 145.0, "std": 55.0}
    n = a.n_support + a.n_query
    g = np.clip(150 + 60 * np.sin(np.linspace(0, 6, 32))[None] + 20 * np.random.randn(n * a.per_domain, 32), 40, 400)
    b = to_tensors(g, np.tile(np.linspace(0, 24, 32, endpoint=False), (len(g), 1)), norm, d, device)
    opt = torch.optim.SGD(net.parameters(), a.lr, momentum=a.momentum, weight_decay=a.wd, nesterov=True)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, 100)
    cw = torch.ones(3, device=device)
    net.train()
    times = []
    with torch.backends.cudnn.flags(enabled=False):
        for i in range(6):
            t = time.time()
            loss, ql, ce = train_step(net, opt, sched, b, a, cw)
            if device == "cuda":
                torch.cuda.synchronize()
            times.append(time.time() - t)
            print(f"  iteration {i + 1}: loss {loss:.4f} (quantile {ql:.4f}, risk CE {ce:.4f}) {times[-1]:.2f}s")
    s = float(np.median(times[1:]))
    print(f"\nSELFTEST OK. About {s:.2f} s per iteration -> {s * a.iters_per_epoch / 60:.1f} min per epoch of "
          f"{a.iters_per_epoch} iterations, {s * a.iters_per_epoch * 50 / 3600:.1f} h for the original 50 epochs.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run_dir", default="runs/gp_run")
    ap.add_argument("--sources", default="replacebg", help="replacebg  or  replacebg,shanghai_t2d")
    ap.add_argument("--shanghai_share", type=float, default=0.3, help="share of patients per batch from Shanghai T2D")
    ap.add_argument("--repo", default="gpformer", help="folder of the cloned GPFormer repo")
    ap.add_argument("--canon_dir", default=str(CANON))
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--iters_per_epoch", type=int, default=500)
    ap.add_argument("--n_support", type=int, default=16)
    ap.add_argument("--n_query", type=int, default=8)
    ap.add_argument("--per_domain", type=int, default=10, help="windows per patient in a batch (batch = 24 x this)")
    ap.add_argument("--inner_iters", type=int, default=1)
    ap.add_argument("--trade_off", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=0.001)
    ap.add_argument("--momentum", type=float, default=0.9)
    ap.add_argument("--wd", type=float, default=0.0005)
    ap.add_argument("--d_model", type=int, default=128)
    ap.add_argument("--n_heads", type=int, default=8)
    ap.add_argument("--e_layers", type=int, default=3)
    ap.add_argument("--d_ff", type=int, default=2048)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--embed", default="cycF")
    ap.add_argument("--freq", default="cyc")
    ap.add_argument("--risk_lambda", type=float, default=0.2, help="weight of the HYPO/NORMAL/HYPER loss")
    ap.add_argument("--val_windows", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stop_after_epoch", type=int, default=0, help=argparse.SUPPRESS)   # test helper
    a = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if a.selftest:
        return selftest(a, device)

    srcs = a.sources.split(",")
    assert srcs[0] == "replacebg" and set(srcs) <= {"replacebg", "shanghai_t2d"}, "sources: replacebg[,shanghai_t2d]"
    rb = load_domains(Path(a.canon_dir) / "replacebg.parquet")
    sh = load_domains(Path(a.canon_dir) / "shanghai.parquet")
    pools = {"replacebg": [d for d in rb if d.split == "train"]}
    shares = {"replacebg": 1.0}
    if "shanghai_t2d" in srcs:
        pools["shanghai_t2d"] = [d for d in sh if d.split == "train" and d.dtype == "T2D"]
        shares = {"replacebg": 1 - a.shanghai_share, "shanghai_t2d": a.shanghai_share}
    norm = fit_scaler([d for p in pools.values() for d in p])           # training patients only
    sampler = DomainSampler(pools, shares, a.n_support + a.n_query, a.per_domain)
    W_rb = eval_windows([d for d in rb if d.split == "val"], a.val_windows, seed=1)
    W_sh = eval_windows([d for d in sh if d.split == "val" and d.dtype == "T2D"], a.val_windows, seed=1)
    print(f"device={device} | sources={srcs} | patients per batch: {sampler.counts} | "
          f"normalization mean {norm['mean']:.1f} std {norm['std']:.1f}")
    print({k: f"{len(v)} patients, {sum(len(d.starts) for d in v)} windows" for k, v in pools.items()})
    print(f"validation: REPLACE-BG {len(W_rb['g'])} windows, Shanghai T2D {len(W_sh['g'])} windows")

    net = build_net(a.repo, vars(a), device=device)
    mark_dim = detect_mark_dim(net, device)
    cw_np, freqs = class_weights(pools, norm, a.per_domain)
    cls_w = torch.tensor(cw_np, device=device)
    print(f"time-feature columns: {mark_dim} | training class shares HYPO/NORMAL/HYPER: "
          f"{[round(f, 3) for f in freqs]} | class weights {np.round(cw_np, 2).tolist()}")

    run = Path(a.run_dir)
    run.mkdir(parents=True, exist_ok=True)
    (run / "run_info.json").write_text(json.dumps(
        {"arch": {k: getattr(a, k) for k in ("d_model", "n_heads", "e_layers", "d_ff", "dropout", "embed", "freq")},
         "norm": norm, "mark_dim": mark_dim, "repo": str(Path(a.repo).resolve()), "sources": srcs,
         "class_weights": cw_np.tolist()}, indent=2))

    opt = torch.optim.SGD(net.parameters(), a.lr, momentum=a.momentum, weight_decay=a.wd, nesterov=True)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs * a.iters_per_epoch)
    ck = Checkpointer(run, {k: v for k, v in vars(a).items() if k not in ("selftest", "stop_after_epoch")})
    st = ck.resume(net, opt, sched, device)
    best, hist = st["best_val"], st["history"]

    for epoch in range(st["start_epoch"], a.epochs):
        net.train()
        t0, tot, tq, tc = time.time(), 0.0, 0.0, 0.0
        with torch.backends.cudnn.flags(enabled=False):
            for it in range(a.iters_per_epoch):
                g, hr = sampler.next()
                b = to_tensors(g, hr, norm, mark_dim, device)
                l, ql, ce = train_step(net, opt, sched, b, a, cls_w)
                tot += l; tq += ql; tc += ce
        n = a.iters_per_epoch
        m_rb = val_mae(net, W_rb, norm, mark_dim, device)
        m_sh = val_mae(net, W_sh, norm, mark_dim, device) if len(W_sh["g"]) else np.full(4, np.nan)
        sel = float(m_rb.mean())                      # model selection: REPLACE-BG validation, same for A and B
        is_best = sel < best
        best = min(best, sel)
        hist.append({"epoch": epoch + 1, "loss": tot / n, "query_quantile_loss": tq / n, "query_risk_ce": tc / n,
                     **{f"val_rb_mae_{m}": v for m, v in zip((30, 60, 90, 120), m_rb)},
                     **{f"val_sh_t2d_mae_{m}": v for m, v in zip((30, 60, 90, 120), m_sh)},
                     "val_rb_mae_mean": sel, "lr": opt.param_groups[0]["lr"]})
        ck.save(net, opt, epoch, best, 0, hist, is_best, sched)
        print(f"epoch {epoch + 1:3d}/{a.epochs} | loss {tot / n:.4f} (risk CE {tc / n:.3f}) | "
              f"val MAE 30/60/90/120 min: REPLACE-BG {'/'.join(f'{v:.1f}' for v in m_rb)} "
              f"| Shanghai T2D {'/'.join(f'{v:.1f}' for v in m_sh)} | {time.time() - t0:.0f}s"
              f"{'  *best*' if is_best else ''}")
        if a.stop_after_epoch and epoch + 1 >= a.stop_after_epoch:
            return print("(stopping here on purpose, as a test of resuming)")

    pd.DataFrame(hist).to_csv(run / "history.csv", index=False)
    print("done. best model:", run / "best.pt")


if __name__ == "__main__":
    main()
