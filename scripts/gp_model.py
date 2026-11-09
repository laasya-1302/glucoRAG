"""Model side of the GPFormer experiments.

GlucoseNet = the ORIGINAL GPFormer (models/GPFormer.py from the repo you cloned, unchanged) + a small risk head.
  forecast : 5 quantiles (10/25/50/75/90 %) of glucose for the next 8 steps (15 min each); 30/60/90/120 min are
             steps 2, 4, 6, 8
  risk     : HYPO / NORMAL / HYPER probabilities for each of those steps, from a small MLP that reads the
             quantile forecast, the last observed glucose and the step number. It is trained jointly with
             the forecast (multi-task), so the classification gradient also shapes the forecast.
"""
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from gp_data import LABEL_LEN, PRED_LEN, SEQ_LEN, make_marks, risk_class

QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)
MEDIAN = QUANTILES.index(0.5)


def load_gpformer_class(repo):
    repo = str(Path(repo).resolve())
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from models import GPFormer          # the repo's own package
    return GPFormer.Model


def make_configs(arch):
    """Settings from the repo's scripts/run.sh and the defaults in args_generator.py."""
    return Namespace(pred_len=PRED_LEN, output_attention=False, enc_in=1, dec_in=1, c_out=len(QUANTILES),
                     d_model=arch["d_model"], n_heads=arch["n_heads"], e_layers=arch["e_layers"], d_layers=1,
                     d_ff=arch["d_ff"], dropout=arch["dropout"], factor=1, activation="gelu",
                     embed=arch["embed"], freq=arch["freq"])


class GlucoseNet(nn.Module):
    def __init__(self, gp_model, hidden=32):
        super().__init__()
        self.gp = gp_model
        self.risk = nn.Sequential(nn.Linear(len(QUANTILES) + 2, hidden), nn.GELU(), nn.Linear(hidden, 3))

    def forward(self, x, xm, ym):
        B = x.size(0)
        # decoder input = the last LABEL_LEN known values (start token) + zeros for the steps to predict
        dec_inp = torch.cat([x[:, -LABEL_LEN:, :], torch.zeros(B, PRED_LEN, 1, device=x.device, dtype=x.dtype)], 1)
        q = self.gp(x, xm, dec_inp, ym)                                   # (B, PRED_LEN, 5)
        last = x[:, -1:, :].expand(-1, PRED_LEN, -1)
        pos = torch.linspace(1.0 / PRED_LEN, 1.0, PRED_LEN, device=x.device).view(1, -1, 1).expand(B, -1, -1)
        logits = self.risk(torch.cat([q, last, pos], -1))                 # (B, PRED_LEN, 3)
        return q, logits


def build_net(repo, arch, mark_dim=None, device="cpu"):
    gp = load_gpformer_class(repo)(make_configs(arch)).float()
    net = GlucoseNet(gp).to(device)
    return net


def detect_mark_dim(net, device, max_dim=12):
    """The original embedding decides how many time-feature columns it accepts. Try 1..max_dim on a dummy pass."""
    net.eval()
    errors = []
    x = torch.zeros(2, SEQ_LEN, 1, device=device)
    for d in range(1, max_dim + 1):
        try:
            with torch.no_grad():
                net(x, torch.zeros(2, SEQ_LEN, d, device=device),
                    torch.zeros(2, LABEL_LEN + PRED_LEN, d, device=device))
            return d
        except Exception as e:                                           # shape mismatch for the wrong d
            errors.append(f"{d}: {type(e).__name__}: {str(e)[:90]}")
    raise RuntimeError("Could not find a time-feature size the model accepts. Paste layers/Embed.py and "
                       "utils/timefeatures.py so the marks can be matched.\n" + "\n".join(errors[-3:]))


def pinball(q_pred, y):
    """Quantile (pinball) loss, mean over batch, steps and quantiles. q_pred (B,P,5), y (B,P,1)."""
    qs = torch.tensor(QUANTILES, device=q_pred.device, dtype=q_pred.dtype).view(1, 1, -1)
    e = y - q_pred
    return torch.maximum(qs * e, (qs - 1) * e).mean()


def to_tensors(g, hour, norm, mark_dim, device):
    g = np.asarray(g, np.float32)
    gs = (g - norm["mean"]) / norm["std"]
    marks = make_marks(hour, mark_dim)
    t = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(device)
    return {"x": t(gs[:, :SEQ_LEN, None]), "y": t(gs[:, SEQ_LEN - LABEL_LEN:, None]),
            "xm": t(marks[:, :SEQ_LEN]), "ym": t(marks[:, SEQ_LEN - LABEL_LEN:]),
            "risk": t(risk_class(g[:, SEQ_LEN:]))}


def task_loss(model, part, cls_w, lam):
    """pinball + lam * class-weighted cross-entropy; both are plain means over elements, so the loss of a
    concatenation of equal-sized patient chunks equals the average of the per-patient losses."""
    q, logits = model(part["x"], part["xm"], part["ym"])
    ql = pinball(q, part["y"][:, LABEL_LEN:, :])
    ce = F.cross_entropy(logits.reshape(-1, 3), part["risk"].reshape(-1), weight=cls_w, reduction="none").mean()
    return ql + lam * ce, ql, ce


@torch.no_grad()
def predict(net, W, norm, mark_dim, device, bs=2048):
    """Returns quantiles in mg/dL (N,8,5) and class probabilities (N,8,3)."""
    net.eval()
    Q, P = [], []
    for i in range(0, len(W["g"]), bs):
        b = to_tensors(W["g"][i:i + bs], W["hour"][i:i + bs], norm, mark_dim, device)
        q, logits = net(b["x"], b["xm"], b["ym"])
        Q.append((q * norm["std"] + norm["mean"]).cpu().numpy())
        P.append(torch.softmax(logits, -1).cpu().numpy())
    if not Q:
        return np.zeros((0, PRED_LEN, len(QUANTILES)), np.float32), np.zeros((0, PRED_LEN, 3), np.float32)
    return np.concatenate(Q), np.concatenate(P)


def class_weights(pools, norm, per_domain=10, n_batches=60, power=0.5):
    """Weights ~ (1/frequency)^power from the training pools (HYPO is rare). Leaves the global RNG untouched."""
    from gp_data import DomainSampler
    state = np.random.get_state()
    np.random.seed(123)
    sampler = DomainSampler(pools, {k: 1.0 / len(pools) for k in pools}, 24, per_domain)
    labels = np.concatenate([risk_class(sampler.next()[0][:, SEQ_LEN:]).ravel() for _ in range(n_batches)])
    np.random.set_state(state)
    freq = np.bincount(labels, minlength=3).astype(np.float64) + 1.0
    w = (1.0 / freq) ** power
    return (w / w.mean()).astype(np.float32), (freq / freq.sum()).tolist()
