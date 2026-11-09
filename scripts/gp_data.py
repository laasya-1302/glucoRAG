"""Data side of the GPFormer experiments (everything on a 15-minute grid, glucose only).

    python gp_data.py prepare [--min_day N] [--seed 42]

Builds one common table per dataset from what you already have:
    cache/canonical/shanghai.parquet   from cache/shanghai_clean + shanghai_zeroshot_split.csv
    cache/canonical/replacebg.parquet  from cache/replacebg/replacebg_15min.parquet (patients split 80/10/10)
Columns: domain, dataset, diabetes_type, split, t_sec, hour, glucose, segment, at_floor, at_ceiling.
A "domain" is one patient. A window is WIN = 32 consecutive grid points (24 in, 8 out) inside one segment,
so no window ever crosses a gap, a recording boundary or a sensor change.

This file is numpy/pandas only. The model side is in gp_model.py.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEQ_LEN, LABEL_LEN, PRED_LEN = 24, 2, 8      # 6 h in, 30 min start token, 2 h out at 15-min steps
WIN = SEQ_LEN + PRED_LEN
HORIZON_POS = {30: 1, 60: 3, 90: 5, 120: 7}  # minutes -> output position
HYPO, HYPER = 70.0, 180.0
CLASSES = ("HYPO", "NORMAL", "HYPER")
CANON = Path("cache/canonical")


def risk_class(g):
    """mg/dL -> 0 HYPO (<70), 1 NORMAL, 2 HYPER (>180)."""
    g = np.asarray(g)
    return np.where(g < HYPO, 0, np.where(g > HYPER, 2, 1)).astype(np.int64)


def make_marks(hour, dim):
    """Time-of-day features, shape hour.shape + (dim,). Hour-of-day only: REPLACE-BG has no calendar dates."""
    hour = np.asarray(hour, np.float32)
    ang = hour / 24.0 * 2 * np.pi
    if dim == 1:
        return (hour / 24.0 - 0.5)[..., None].astype(np.float32)
    base = np.stack([np.sin(ang), np.cos(ang)], -1).astype(np.float32)
    if dim == 2:
        return base
    pad = np.zeros(hour.shape + (dim - 2,), np.float32)   # unused slots stay zero
    return np.concatenate([base, pad], -1)


# ---------------------------------------------------------------------------- prepare
def prepare(min_day=None, seed=42, clean_dir="cache/shanghai_clean", split_csv="shanghai_zeroshot_split.csv",
            rb_in="cache/replacebg/replacebg_15min.parquet", out_dir=CANON):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    split = pd.read_csv(split_csv, dtype=str)
    parts = []
    for r in split.itertuples():
        d = pd.read_parquet(Path(clean_dir) / f"{Path(r.path).stem}.parquet")
        ts = d["timestamp"]
        parts.append(pd.DataFrame({
            "domain": f"ShanghaiDM:{r.patient_id}", "dataset": "ShanghaiDM",
            "diabetes_type": "T1D" if r.cohort == "T1DM" else "T2D", "split": r.split,
            "t_sec": ((ts - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("int64"),
            "hour": (ts.dt.hour + ts.dt.minute / 60 + ts.dt.second / 3600).astype("float32"),
            "glucose": d["cgm"].astype("float32"),
            "segment": (int(r.recording) * 1000 + d["segment"]).astype("int32"),
            "at_floor": d["at_floor"].astype(bool), "at_ceiling": False}))
    sh = pd.concat(parts, ignore_index=True)
    for c in ("domain", "dataset", "diabetes_type", "split"):
        sh[c] = sh[c].astype("category")
    sh.to_parquet(out / "shanghai.parquet")

    rb = pd.read_parquet(rb_in)
    if min_day is not None:
        rb = rb[rb["t_sec"] >= min_day * 86400]
    pats = np.array(sorted(rb["patient_id"].astype(str).unique()))
    np.random.default_rng(seed).shuffle(pats)
    n_val = n_test = max(1, round(0.1 * len(pats)))
    split_of = {p: ("val" if i < n_val else "test" if i < n_val + n_test else "train") for i, p in enumerate(pats)}
    pid = rb["patient_id"].astype(str).astype("category")
    rb = rb.assign(domain=pid.map(lambda p: f"REPLACE-BG:{p}").astype("category"),
                   split=pid.map(split_of).astype("category"))
    rb["dataset"], rb["diabetes_type"] = "REPLACE-BG", "T1D"
    rb["dataset"] = rb["dataset"].astype("category")
    rb["diabetes_type"] = rb["diabetes_type"].astype("category")
    rb = rb[["domain", "dataset", "diabetes_type", "split", "t_sec", "hour", "glucose", "segment",
             "at_floor", "at_ceiling"]]
    rb.to_parquet(out / "replacebg.parquet")

    rows = []
    for name, df in (("ShanghaiDM", sh), ("REPLACE-BG", rb)):
        doms = build_domains(df)
        for d in doms:
            rows.append({"dataset": name, "domain": d.name, "type": d.dtype, "split": d.split,
                         "points": len(d.g), "windows": len(d.starts)})
    summary = pd.DataFrame(rows)
    summary.to_csv(out / "domains.csv", index=False)
    print("== patients / points / possible 24-in-8-out windows ==")
    print(summary.groupby(["dataset", "type", "split"]).agg(
        patients=("domain", "count"), points=("points", "sum"), windows=("windows", "sum")).to_string())
    print("\nsaved to", out)


# ---------------------------------------------------------------------------- domains
class Domain:
    __slots__ = ("name", "dataset", "dtype", "split", "g", "hour", "starts")

    def __init__(self, name, dataset, dtype, split, g, hour, starts):
        self.name, self.dataset, self.dtype, self.split = name, dataset, dtype, split
        self.g, self.hour, self.starts = g, hour, starts


def build_domains(df):
    """One Domain per patient. starts = indices where a full WIN-point window lies inside one segment."""
    out = []
    for name, d in df.groupby("domain", sort=False, observed=True):
        if len(d) == 0:
            continue
        d = d.sort_values("t_sec")
        g = d["glucose"].to_numpy(np.float32)
        hr = d["hour"].to_numpy(np.float32)
        seg = d["segment"].to_numpy()
        n = len(g)
        cut = np.flatnonzero(np.diff(seg) != 0) + 1
        s, e = np.concatenate([[0], cut]), np.concatenate([cut, [n]])
        starts = [np.arange(a, b - WIN + 1) for a, b in zip(s, e) if b - a >= WIN]
        starts = np.concatenate(starts).astype(np.int64) if starts else np.zeros(0, np.int64)
        out.append(Domain(str(name), str(d["dataset"].iloc[0]), str(d["diabetes_type"].iloc[0]),
                          str(d["split"].iloc[0]), g, hr, starts))
    return out


def load_domains(path):
    df = pd.read_parquet(path)
    return build_domains(df)


def fit_scaler(domains):
    """Mean and std of all training readings (training patients only)."""
    v = np.concatenate([d.g for d in domains]).astype(np.float64)
    return {"mean": float(v.mean()), "std": float(v.std())}


def eval_windows(domains, max_n=None, seed=0):
    """All windows of the given domains (optionally a fixed random subset of about max_n)."""
    rs = np.random.RandomState(seed)
    total = sum(len(d.starts) for d in domains)
    frac = 1.0 if (max_n is None or total <= max_n) else max_n / total
    G, H, ID = [], [], []
    for i, d in enumerate(domains):
        st = d.starts
        if frac < 1.0:
            st = st[rs.rand(len(st)) < frac]
        if len(st) == 0:
            continue
        rows = st[:, None] + np.arange(WIN)[None, :]
        G.append(d.g[rows]); H.append(d.hour[rows]); ID.append(np.full(len(st), i, np.int32))
    if not G:
        return {"g": np.zeros((0, WIN), np.float32), "hour": np.zeros((0, WIN), np.float32),
                "dom": np.zeros(0, np.int32), "names": [d.name for d in domains],
                "dtype": np.array([d.dtype for d in domains])}
    return {"g": np.concatenate(G), "hour": np.concatenate(H), "dom": np.concatenate(ID),
            "names": [d.name for d in domains], "dtype": np.array([d.dtype for d in domains])}


class DomainSampler:
    """Each batch = n_domains patients x per_domain windows, laid out patient after patient, so that
    batch.chunk(n_domains) gives one patient per chunk (what GPFormer's meta-learning loop expects).
    shares: fraction of the n_domains patients drawn from each source pool. Uses numpy's global RNG
    (so that resuming restores it)."""

    def __init__(self, pools, shares, n_domains=24, per_domain=10):
        self.pools = {k: [d for d in v if len(d.starts) > 0] for k, v in pools.items()}
        raw = {k: shares[k] * n_domains for k in self.pools}
        counts = {k: int(np.floor(v)) for k, v in raw.items()}
        for k in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True):
            if sum(counts.values()) < n_domains:
                counts[k] += 1
        self.counts, self.n_domains, self.per_domain = counts, n_domains, per_domain

    def next(self):
        G, H = [], []
        for src, c in self.counts.items():
            pool = self.pools[src]
            pick = np.random.choice(len(pool), size=c, replace=len(pool) < c)
            for i in pick:
                d = pool[i]
                st = d.starts[np.random.randint(0, len(d.starts), self.per_domain)]
                rows = st[:, None] + np.arange(WIN)[None, :]
                G.append(d.g[rows]); H.append(d.hour[rows])
        return np.concatenate(G), np.concatenate(H)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["prepare"])
    ap.add_argument("--min_day", type=int, default=None, help="drop REPLACE-BG data before this day from enrollment")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    prepare(a.min_day, a.seed)
