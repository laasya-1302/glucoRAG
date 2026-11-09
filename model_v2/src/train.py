
import argparse, json, sys, time, hashlib, os, pathlib
import numpy as np, pandas as pd, torch, torch.nn as nn, torch.nn.functional as F
sys.dont_write_bytecode = True
ROOT = pathlib.Path("/content/drive/MyDrive/gpformer_fresh"); sys.path.insert(0, str(ROOT))
from src.data.windows import Store, build_windows
from src.utils.seed import set_seed, make_rng
QS = (0.1, 0.25, 0.5, 0.75, 0.9); MED = 2
POS, MIN = [1, 3, 5, 7], [30, 60, 90, 120]
dev = "cuda" if torch.cuda.is_available() else "cpu"

class GRUNet(nn.Module):
    def __init__(self, nf=9, h=128):
        super().__init__(); self.rnn = nn.GRU(nf, h, 2, batch_first=True, dropout=0.1); self.out = nn.Linear(h, 8 * 5)
    def forward(self, x):
        o, _ = self.rnn(x); return self.out(o[:, -1]).view(-1, 8, 5)

class GPBackbone(nn.Module):
    def __init__(self, repo):
        super().__init__()
        from argparse import Namespace
        sys.path.insert(0, str(repo)); from models import GPFormer
        cfg = Namespace(pred_len=8, output_attention=False, enc_in=7, dec_in=7, c_out=5, d_model=128, n_heads=8,
                        e_layers=3, d_layers=1, d_ff=2048, dropout=0.05, factor=1, activation="gelu",
                        embed="cycF", freq="cyc")
        self.m = GPFormer.Model(cfg).float()
    def forward(self, x):
        xe = x[..., [0, 3, 4, 5, 6, 7, 8]]
        ang = torch.atan2(x[..., 1], x[..., 2])
        xm = torch.stack([torch.sin(ang), torch.cos(ang)], -1)
        off = torch.arange(-1, 9, device=x.device, dtype=x.dtype).view(1, -1) * (15.0 / 1440.0 * 2 * np.pi)
        a2 = ang[:, -1:] + off
        ym = torch.stack([torch.sin(a2), torch.cos(a2)], -1)
        dec = torch.cat([xe[:, -2:, :], torch.zeros(x.size(0), 8, 7, device=x.device, dtype=x.dtype)], 1)
        return self.m(xe, xm, dec, ym)

class Net(nn.Module):
    def __init__(self, bb, residual=True):
        super().__init__(); self.bb = bb; self.res = residual
        self.risk = nn.Sequential(nn.Linear(7, 32), nn.GELU(), nn.Linear(32, 3))
    def forward(self, x):
        q = self.bb(x); last = x[:, -1:, 0:1]
        if self.res: q = q + last
        q = torch.sort(q, -1).values
        pos = torch.linspace(1 / 8, 1, 8, device=x.device).view(1, -1, 1).expand(x.size(0), -1, -1)
        return q, self.risk(torch.cat([q, last.expand(-1, 8, -1), pos], -1))

def build(a):
    bb = GRUNet() if a.model == "gru" else GPBackbone(ROOT / "third_party/gpformer")
    return Net(bb, bool(a.residual)).to(dev)

def loss_fn(q, logits, y, lam, low_w, mu, sd):
    yn = ((y - mu) / sd).unsqueeze(-1)
    qs = torch.tensor(QS, device=q.device, dtype=q.dtype).view(1, 1, -1)
    e = yn - q; l = torch.maximum(qs * e, (qs - 1) * e)
    w = 1 + (low_w - 1) * (y < 70).float().unsqueeze(-1)
    pin = (l * w).mean()
    cls = torch.where(y < 70, 0, torch.where(y > 180, 2, 1))
    ce = F.cross_entropy(logits.reshape(-1, 3), cls.reshape(-1))
    return pin + lam * ce, pin, ce

def load_ctx():
    sc = json.load(open(ROOT / "manifests/scalers_v1.json"))
    idx = pd.read_parquet(ROOT / "cache/windows/window_index_v1.parquet"); idx["patient"] = idx.patient.astype(str)
    return sc, idx, Store(ROOT)

def assemble_eval(store, idx, sc, mode, per_pat=200, seed=42):
    rng = make_rng(seed); X, Y, L, P, D = [], [], [], [], []
    for (ds, p), g in idx[idx.split == "val"].groupby(["dataset", "patient"]):
        s = g.start.to_numpy(); s = rng.choice(s, min(per_pat, len(s)), replace=False)
        w = build_windows(store, p, s, sc, mode)
        X.append(w["x"]); Y.append(w["y"]); L.append(w["last"]); P += [p] * len(s); D += [ds] * len(s)
    return np.concatenate(X), np.concatenate(Y), np.concatenate(L), np.array(P), np.array(D)

def draw_train(store, info, by_pat, a, sc, epoch):
    rng = make_rng(a.seed * 100003 + epoch); n = a.steps * a.bs
    if a.sampling == "pooled": p = info.n.to_numpy(float)
    elif a.sampling == "patient": p = np.ones(len(info))
    else:
        h = (info.ds == "hupa").to_numpy(); p = np.where(h, a.hupa_share / h.sum(), (1 - a.hupa_share) / (~h).sum())
    cnt = rng.multinomial(n, p / p.sum()); X, Y = [], []
    for name, c in zip(info.index, cnt):
        if c == 0: continue
        s = by_pat[name][rng.integers(0, len(by_pat[name]), c)]
        w = build_windows(store, name, s, sc, a.mode); X.append(w["x"]); Y.append(w["y"])
    X, Y = np.concatenate(X), np.concatenate(Y); perm = rng.permutation(len(X))
    return X[perm], Y[perm]

@torch.no_grad()
def predict(net, X, mu, sd, bs=1024):
    net.eval(); Q, P = [], []
    for i in range(0, len(X), bs):
        q, lg = net(torch.from_numpy(X[i:i + bs]).to(dev)); Q.append(q.cpu().numpy()); P.append(torch.softmax(lg, -1).cpu().numpy())
    return np.concatenate(Q) * sd + mu, np.concatenate(P)

def metrics(Q, Pr, Y, L, Pid, D):
    out = {}; m = D == "replacebg"
    for pos, mn in zip(POS, MIN):
        d = pd.DataFrame({"p": Pid[m], "e": np.abs(Q[m, pos, MED] - Y[m, pos]), "ep": np.abs(L[m] - Y[m, pos])}).groupby("p").mean()
        out[f"mae{mn}"] = d.e.mean(); out[f"skill{mn}"] = 1 - d.e.mean() / d.ep.mean()
        hy = Y[m, pos] < 70; ph = Pr[m, pos, 0] >= 0.2
        out[f"hypoR{mn}"] = (hy & ph).sum() / max(hy.sum(), 1); out[f"hypoP{mn}"] = (hy & ph).sum() / max(ph.sum(), 1)
    return out

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()[:16]

def train(a):
    set_seed(a.seed); sc, idx, store = load_ctx(); mu, sd = sc["glucose"]["mean"], sc["glucose"]["std"]
    run = ROOT / "runs" / a.run; run.mkdir(parents=True, exist_ok=True)
    idx_tr = idx[idx.split == "train"]
    info = idx_tr.groupby("patient").agg(ds=("dataset", "first"), n=("start", "size"))
    by_pat = {p: g.start.to_numpy() for p, g in idx_tr.groupby("patient")}
    modes = ["cgm_only"] if a.mode == "cgm_only" else ["multimodal", "cgm_only"]
    V = {m: assemble_eval(store, idx, sc, m) for m in modes}
    net = build(a); opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs)
    start, best, bad, hist = 0, 1e9, 0, []
    if (run / "last.pt").exists():
        st = torch.load(run / "last.pt", map_location=dev, weights_only=False)
        net.load_state_dict(st["model"]); opt.load_state_dict(st["opt"]); sched.load_state_dict(st["sched"])
        start, best, bad, hist = st["epoch"], st["best"], st["bad"], st["hist"]; print("resumed at epoch", start)
    if not (run / "config.json").exists():
        json.dump({"args": vars(a), "scalers_sha": sha(ROOT / "manifests/scalers_v1.json"), "split_sha": sha(ROOT / "manifests/split_v1.json"),
                   "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                   "params": sum(p.numel() for p in net.parameters())}, open(run / "config.json", "w"), indent=1)
    print(f"run {a.run} | model {a.model} mode {a.mode} sampling {a.sampling} seed {a.seed} | params {sum(p.numel() for p in net.parameters())}")
    for ep in range(start, a.epochs):
        if bad >= a.patience: print("early stop"); break
        t0 = time.time(); X, Y = draw_train(store, info, by_pat, a, sc, ep); net.train(); tot = 0.0
        for i in range(a.steps):
            xb = torch.from_numpy(X[i * a.bs:(i + 1) * a.bs]).to(dev); yb = torch.from_numpy(Y[i * a.bs:(i + 1) * a.bs]).to(dev)
            if a.mode == "multimodal" and a.moddrop > 0:
                keep = (torch.rand(len(xb), device=dev) >= a.moddrop).float().view(-1, 1, 1)
                xb = torch.cat([xb[..., :3], xb[..., 3:] * keep], -1)
            q, lg = net(xb); loss, pin, ce = loss_fn(q, lg, yb, a.lam, a.low_w, mu, sd)
            assert torch.isfinite(loss), "non-finite loss"
            opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); tot += loss.item()
        sched.step(); row = {"epoch": ep + 1, "loss": tot / a.steps, "sec": time.time() - t0}; sel = []
        for m in modes:
            Xv, Yv, Lv, Pv, Dv = V[m]; Q, Pr = predict(net, Xv, mu, sd); mm = metrics(Q, Pr, Yv, Lv, Pv, Dv)
            row.update({f"{m}_{k}": v for k, v in mm.items()}); sel.append(np.mean([mm[f"mae{h}"] for h in MIN]))
        row["sel"] = float(np.mean(sel)); hist.append(row)
        if row["sel"] < best - 1e-4:
            best, bad = row["sel"], 0; torch.save({"model": net.state_dict()}, run / "best.pt")
        else: bad += 1
        torch.save({"model": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "epoch": ep + 1, "best": best, "bad": bad, "hist": hist}, run / "last.tmp")
        os.replace(run / "last.tmp", run / "last.pt"); pd.DataFrame(hist).to_csv(run / "history.csv", index=False)
        r = row; print(f"ep {ep + 1:2d} | loss {r['loss']:.3f} | {r['sec']:.0f}s | val MAE(mm) " +
                       "/".join(f"{r.get('multimodal_mae' + str(h), r.get('cgm_only_mae' + str(h))):.1f}" for h in MIN) +
                       f" | sel {r['sel']:.2f}{' *' if bad == 0 else ''}")
    net.load_state_dict(torch.load(run / "best.pt", map_location=dev, weights_only=False)["model"])
    for m in modes:
        Xv, Yv, Lv, Pv, Dv = V[m]; Q, Pr = predict(net, Xv, mu, sd)
        np.savez_compressed(run / f"val_preds_{m}.npz", q=Q, p=Pr, y=Yv, last=Lv, patient=Pv, dataset=Dv)
    json.dump({"best_sel_mae": best, "epochs_run": len(hist)}, open(run / "final.json", "w")); print("done; best sel MAE", round(best, 3))

def selftest(a):
    set_seed(0); sc, idx, store = load_ctx(); mu, sd = sc["glucose"]["mean"], sc["glucose"]["std"]
    net = build(a); X = torch.randn(4, 24, 9, device=dev); q, lg = net(X)
    assert q.shape == (4, 8, 5) and lg.shape == (4, 8, 3), (q.shape, lg.shape); print("shapes ok")
    assert (q[..., 1:] >= q[..., :-1]).all(); print("quantiles sorted ok")
    y = torch.rand(4, 8, device=dev) * 300 + 40; loss, _, _ = loss_fn(q, lg, y, 0.5, 2.0, mu, sd); loss.backward()
    assert torch.isfinite(loss) and all(torch.isfinite(p.grad).all() for p in net.parameters() if p.grad is not None); print("finite loss and gradients ok")
    tmp = ROOT / "runs/_selftest.pt"; torch.save(net.state_dict(), tmp); n2 = build(a); n2.load_state_dict(torch.load(tmp, map_location=dev)); net.eval(); n2.eval()
    assert torch.allclose(net(X)[0], n2(X)[0], atol=1e-6); os.remove(tmp); print("checkpoint round-trip ok")
    p0 = idx[(idx.split == "train") & (idx.dataset == "replacebg")].patient.iloc[0]
    s = idx[(idx.patient == p0)].start.to_numpy()[:64]; w = build_windows(store, p0, s, sc, "multimodal")
    xb, yb = torch.from_numpy(w["x"]).to(dev), torch.from_numpy(w["y"]).to(dev)
    net = build(a); opt = torch.optim.AdamW(net.parameters(), lr=1e-3); ls = []
    for i in range(200):
        net.train(); q, lg = net(xb); loss, _, _ = loss_fn(q, lg, yb, 0.5, 2.0, mu, sd); opt.zero_grad(); loss.backward(); opt.step(); ls.append(loss.item())
    print(f"tiny-batch overfit: loss {np.mean(ls[:5]):.3f} -> {np.mean(ls[-5:]):.3f}"); assert np.mean(ls[-5:]) < 0.6 * np.mean(ls[:5]), "did not overfit"
    print("ALL SELFTESTS PASSED")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="tmp"); ap.add_argument("--model", choices=["gru", "gpformer"], default="gru")
    ap.add_argument("--mode", choices=["multimodal", "cgm_only"], default="multimodal")
    ap.add_argument("--sampling", choices=["pooled", "patient", "dataset"], default="pooled"); ap.add_argument("--hupa_share", type=float, default=0.5)
    ap.add_argument("--moddrop", type=float, default=0.3); ap.add_argument("--low_w", type=float, default=2.0); ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--lr", type=float, default=5e-4); ap.add_argument("--epochs", type=int, default=20); ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--bs", type=int, default=128); ap.add_argument("--patience", type=int, default=5); ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--residual", type=int, default=1); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(); selftest(a) if a.selftest else train(a)
