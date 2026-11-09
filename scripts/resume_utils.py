"""Resume helpers for Colab (plain PyTorch).

1. process_all(): run a preprocessing function once per file and skip files already done.
2. Checkpointer: save the full training state every epoch and resume exactly where it stopped.

Everything is written to a folder on Google Drive, so it survives a runtime disconnect.
Run `python resume_utils.py` to execute a self-test that proves resuming gives the same result
as an uninterrupted run.
"""
import hashlib
import json
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch


# ---------------------------------------------------------------- preprocessing cache
def process_all(items, out_dir, fn, suffix=".parquet"):
    """items: list of (name, input) pairs. fn(input) -> DataFrame.
    Writes out_dir/<name>.parquet. Existing outputs are skipped, so a rerun continues where it stopped."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    for name, item in items:
        out = out_dir / f"{name}{suffix}"
        if out.exists():
            skipped += 1
            continue
        df = fn(item)
        tmp = out.with_suffix(out.suffix + ".tmp")
        df.to_parquet(tmp)
        os.replace(tmp, out)  # never leaves a half-written file if the runtime dies
        done += 1
        if done % 10 == 0:
            print(f"  processed {done} new files ({skipped} already done)")
    print(f"preprocessing finished: {done} new, {skipped} skipped (already cached)")


# ---------------------------------------------------------------- training checkpoints
def config_hash(cfg: dict) -> str:
    return hashlib.md5(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _atomic_save(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(obj, tmp)
    os.replace(tmp, path)


class Checkpointer:
    """last.pt = full state after every epoch (for resuming). best.pt = best validation model (for use)."""

    def __init__(self, run_dir, cfg: dict):
        self.dir = Path(run_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hash = config_hash(cfg)
        (self.dir / "config.json").write_text(json.dumps(cfg, indent=2, default=str))

    def save(self, model, optimizer, epoch, best_val, bad_epochs, history, is_best, scheduler=None):
        cuda_rng = [t.cpu() for t in torch.cuda.get_rng_state_all()] if torch.cuda.is_available() else None
        _atomic_save({
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict() if scheduler else None,
            "epoch": epoch, "best_val": best_val, "bad_epochs": bad_epochs, "history": history,
            "config_hash": self.hash,
            "rng": {"python": random.getstate(), "numpy": np.random.get_state(),
                    "torch": torch.get_rng_state(), "cuda": cuda_rng},
        }, self.dir / "last.pt")
        if is_best:
            _atomic_save({"model": model.state_dict(), "epoch": epoch, "val": best_val,
                          "config_hash": self.hash}, self.dir / "best.pt")

    def resume(self, model, optimizer, scheduler=None, device="cpu"):
        """Returns a dict with start_epoch, best_val, bad_epochs, history (fresh values if no checkpoint)."""
        p = self.dir / "last.pt"
        fresh = {"start_epoch": 0, "best_val": float("inf"), "bad_epochs": 0, "history": []}
        if not p.exists():
            print("No checkpoint found: starting from epoch 0")
            return fresh
        s = torch.load(p, map_location=device, weights_only=False)  # our own file, so this is safe
        if s["config_hash"] != self.hash:
            raise RuntimeError("The settings changed since this checkpoint was saved. "
                               "Use a new run folder, or delete last.pt to start over.")
        model.load_state_dict(s["model"])
        optimizer.load_state_dict(s["optimizer"])
        if scheduler is not None and s["scheduler"] is not None:
            scheduler.load_state_dict(s["scheduler"])
        random.setstate(s["rng"]["python"])
        np.random.set_state(s["rng"]["numpy"])
        torch.set_rng_state(s["rng"]["torch"].cpu())
        if s["rng"]["cuda"] is not None and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(s["rng"]["cuda"])
        print(f"Resuming: {s['epoch'] + 1} epochs already done, continuing with epoch {s['epoch'] + 2} "
              f"(best val so far {s['best_val']:.4f})")
        return {"start_epoch": s["epoch"] + 1, "best_val": s["best_val"],
                "bad_epochs": s["bad_epochs"], "history": s["history"]}


# ---------------------------------------------------------------- self-test
def _run(run_dir, epochs, stop_after=None, seed=0):
    cfg = {"lr": 0.05, "epochs": epochs, "seed": seed}
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    g = torch.Generator().manual_seed(123)
    X = torch.randn(256, 8, generator=g)
    y = X @ torch.arange(1.0, 9.0) + 0.1 * torch.randn(256, generator=g)
    model = torch.nn.Linear(8, 1)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["lr"])
    ck = Checkpointer(run_dir, cfg)
    st = ck.resume(model, opt)
    best, bad, hist = st["best_val"], st["bad_epochs"], st["history"]
    for epoch in range(st["start_epoch"], epochs):
        perm = torch.randperm(len(X))  # uses the torch RNG, which is restored on resume
        for i in range(0, len(X), 32):
            idx = perm[i:i + 32]
            loss = torch.nn.functional.mse_loss(model(X[idx]).squeeze(1), y[idx])
            opt.zero_grad(); loss.backward(); opt.step()
        val = loss.item()
        hist.append(val)
        is_best = val < best
        best, bad = (val, 0) if is_best else (best, bad + 1)
        ck.save(model, opt, epoch, best, bad, hist, is_best)
        if stop_after is not None and epoch + 1 == stop_after:
            print(f"-- simulated disconnect after epoch {epoch + 1} --")
            return None
    return torch.cat([p.detach().flatten() for p in model.parameters()])


if __name__ == "__main__":
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    full = _run(tmp / "full", epochs=6)
    _run(tmp / "resumed", epochs=6, stop_after=3)   # disconnect after 3 epochs
    resumed = _run(tmp / "resumed", epochs=6)       # rerun: continues at epoch 4
    print("identical final weights:", torch.allclose(full, resumed))
    shutil.rmtree(tmp)
