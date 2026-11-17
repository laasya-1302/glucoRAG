import sys, os
sys.path.insert(0, os.getcwd())
import json
from datetime import datetime, timedelta
from backend.app.services.e1_inference import e1_service

e1_service.warmup()
glucose = [110, 98, 99, 89, 96, 92, 87, 85, 84, 81, 82, 80, 75, 73, 74, 72, 70, 68, 67, 66, 64, 62, 65, 60]
latest_dt = datetime(2026, 11, 10, 12, 30, 0)
slot_dts = [latest_dt - timedelta(minutes=15 * (23 - i)) for i in range(24)]

presets = [
    ('A', 'Glucose only (CGM-only)', None, None, None, [59, 79, 97, 106]),
    ('B', 'Multimodal, no insulin, no carbs', [], 0.9, [], [61, 84, 102, 113]),
    ('C', 'Carbs 30 g, insulin data unavailable', None, None, [{'time': '2026-11-10T12:30:00', 'carbs': 30.0}], [67, 88, 103, 111]),
    ('D', 'Carbs 60 g, insulin data unavailable', None, None, [{'time': '2026-11-10T12:30:00', 'carbs': 60.0}], [82, 103, 111, 113]),
    ('E', 'Carbs 60 g, insulin available, none given', [], 0.9, [{'time': '2026-11-10T12:30:00', 'carbs': 60.0}], [83, 108, 114, 117]),
    ('F', 'Carbs 60 g + bolus 4 U', [{'time': '2026-11-10T12:30:00', 'units': 4.0}], 0.9, [{'time': '2026-11-10T12:30:00', 'carbs': 60.0}], [84, 109, 114, 117]),
    ('G', 'Bolus 4 U, no carbs', [{'time': '2026-11-10T12:30:00', 'units': 4.0}], 0.9, [], [64, 89, 107, 116])
]

print('| Preset | Description | Target (+30/+60/+90/+120) | Actual Median | P(hypo) @ +30/+60/+90/+120 | Status |')
print('|:---:|:---|:---:|:---:|:---:|:---:|')
for code, name, bolus, basal, carbs, target in presets:
    res = e1_service.predict(readings=glucose, latest_dt=latest_dt, slot_dts=slot_dts, bolus=bolus, basal=basal, carbs=carbs)
    f = res['forecast']
    actual = [int(round(f[1]['median'])), int(round(f[3]['median'])), int(round(f[5]['median'])), int(round(f[7]['median']))]
    p_hypo = [round(f[1]['p_hypo'], 3), round(f[3]['p_hypo'], 3), round(f[5]['p_hypo'], 3), round(f[7]['p_hypo'], 3)]
    match = all(abs(a - t) <= 3 for a, t in zip(actual, target))
    p_str = '/'.join(str(p) for p in p_hypo)
    act_str = '/'.join(str(a) for a in actual)
    tgt_str = '/'.join(str(t) for t in target)
    status_str = "EXACT MATCH" if actual == target else ("PASS (<=3 mg/dL)" if match else "FAIL")
    print(f'| **{code}** | {name} | {tgt_str} | **{act_str}** | {p_str} | {status_str} |')
