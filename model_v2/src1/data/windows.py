
"""Window loader. Inputs are the 24 steps up to and including the forecast origin; targets are the next 8 steps."""
import numpy as np, pandas as pd, pathlib
IN_LEN, OUT_LEN, N_FEAT = 24, 8, 9
FEATURES = ["glucose", "sin_tod", "cos_tod", "bolus", "basal", "carb", "m_bolus", "m_basal", "m_carb"]
EVENT_CLIP = 3.0     # event values are x / (99.9th pct of training); clipped at 3x that scale

class Store:
    def __init__(self, root):
        root = pathlib.Path(root)
        self.g, self.tod, self.ev, self.dataset, tmin = {}, {}, {}, {}, {}
        for name in ("hupa", "replacebg", "d1namo"):
            cols = ["patient", "glucose", "tod_min"] + (["t_min"] if name != "hupa" else [])
            df = pd.read_parquet(root / f"cache/canonical/{name}_glucose_15min.parquet", columns=cols)
            for pid, d in df.groupby("patient", sort=False):
                self.g[pid] = d.glucose.to_numpy(np.float32)
                self.tod[pid] = d.tod_min.to_numpy(np.float32)
                self.dataset[pid] = name
                if name == "replacebg":
                    tmin[pid] = d.t_min.to_numpy()
        ev = pd.read_parquet(root / "cache/canonical/replacebg_events_15min.parquet")
        for pid, d in ev.groupby("patient", sort=False):
            assert len(d) == len(self.g[pid]) and np.array_equal(d.t_min.to_numpy(), tmin[pid]), \
                f"event rows do not line up with glucose rows for {pid}"
            self.ev[pid] = d[["bolus_u", "basal_uh", "carb_g", "m_bolus", "m_basal", "m_carb"]].to_numpy(np.float32)

def build_windows(store, pid, starts, sc, mode="multimodal"):
    if mode not in ("multimodal", "cgm_only"):
        raise ValueError(mode)
    starts = np.asarray(starts, np.int64)
    rows = starts[:, None] + np.arange(IN_LEN + OUT_LEN)[None, :]
    g = store.g[pid][rows]
    ri = rows[:, :IN_LEN]                                  # inputs use ONLY these positions
    x = np.zeros((len(starts), IN_LEN, N_FEAT), np.float32)
    x[..., 0] = (g[:, :IN_LEN] - sc["glucose"]["mean"]) / sc["glucose"]["std"]
    ang = store.tod[pid][ri] / 1440.0 * 2 * np.pi
    x[..., 1], x[..., 2] = np.sin(ang), np.cos(ang)
    if mode == "multimodal" and pid in store.ev:
        e, caps = store.ev[pid][ri], sc["event_caps"]
        x[..., 3] = np.clip(e[..., 0] / caps["bolus_u"], 0, EVENT_CLIP)
        x[..., 4] = np.clip(e[..., 1] / caps["basal_uh"], 0, EVENT_CLIP)
        x[..., 5] = np.clip(e[..., 2] / caps["carb_g"], 0, EVENT_CLIP)
        x[..., 6:9] = e[..., 3:6]
    return {"x": x, "y": g[:, IN_LEN:].astype(np.float32), "last": g[:, IN_LEN - 1]}
