import React from 'react';
import { Table, ShieldAlert, CheckCircle, AlertTriangle, ShieldCheck, Database, Hash } from 'lucide-react';

export default function ForecastTable({ 
  forecast, 
  units = "mg/dL",
  mode = "cgm_only",
  inputsUsed = ["cgm"],
  modelName = "E1 Multimodal GPFormer",
  checkpointHashes = null,
  compareWithCgmOnly = false,
  horizonDiffs = []
}) {
  if (!forecast || forecast.length === 0) return null;

  const formatTime = (isoString) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="card table-card">
      <div className="card-header">
        <div>
          <h2 className="card-title flex-align">
            <Table size={18} className="text-teal" />
            <span>Multi-Horizon Forecast &amp; Calibrated Risk Distribution</span>
          </h2>
          <p className="card-description">
            Quantile forecasts, calibrated uncertainty bounds, median-derived forecast class, and frozen threshold alerts.
          </p>
        </div>

        {/* Model & Input Features Metadata */}
        <div className="model-meta-badges">
          <span className="badge-meta">
            <strong>Mode:</strong> {mode === 'multimodal' || mode === 'E1' ? 'Multimodal (E1)' : 'CGM-only'}
          </span>
          <span className="badge-meta">
            <strong>Inputs:</strong> {Array.isArray(inputsUsed) ? inputsUsed.join(', ') : 'cgm'}
          </span>
          <span className="badge-meta">
            <strong>Model:</strong> {modelName}
          </span>
        </div>
      </div>

      <div className="table-responsive">
        <table className="forecast-table">
          <thead>
            <tr>
              <th>Step</th>
              <th>Horizon</th>
              <th>Est. Time</th>
              <th>Median (q50)</th>
              {compareWithCgmOnly && <th>Diff vs Glucose Only</th>}
              <th>10%–90% Band</th>
              <th>Bandwidth</th>
              <th>P(low) &lt;70</th>
              <th>P(normal) 70–180</th>
              <th>P(high) &gt;180</th>
              <th>Forecast Class (Median)</th>
              <th>Threshold Alert</th>
            </tr>
          </thead>
          <tbody>
            {forecast.map((row) => {
              const med = row.median ?? row.glucose_median;
              // Forecast class derived STRICTLY from MEDIAN (<70 low, 70-180 normal, >180 high)
              const fClass = row.forecast_class || (med < 70 ? 'low' : med <= 180 ? 'normal' : 'high');
              const alertMsg = row.alert;

              const isHypoAlert = alertMsg === "Possible low glucose";
              const isHyperAlert = alertMsg === "Possible high glucose";
              const diffItem = horizonDiffs?.find(d => d.step === row.step);

              const lo = row.lo ?? row.uncertainty_band?.low_q10;
              const hi = row.hi ?? row.uncertainty_band?.high_q90;
              const bandwidth = (lo != null && hi != null) ? (hi - lo).toFixed(1) : '—';

              return (
                <tr key={row.step} className={isHypoAlert ? 'row-alert-hypo' : ''}>
                  <td className="font-semibold text-center">#{row.step}</td>
                  <td>
                    <span className="horizon-badge">+{row.horizon_minutes} min</span>
                  </td>
                  <td className="text-muted">{formatTime(row.timestamp)}</td>
                  <td>
                    <strong className="glucose-val text-teal">
                      {med} <span className="unit-label">{units}</span>
                    </strong>
                  </td>
                  {compareWithCgmOnly && (
                    <td>
                      <span className={`diff-pill ${diffItem && diffItem.diff_mg_dl > 0 ? 'diff-pos' : (diffItem && diffItem.diff_mg_dl < 0 ? 'diff-neg' : 'diff-neutral')}`}>
                        {diffItem ? `${diffItem.diff_mg_dl > 0 ? '+' : ''}${diffItem.diff_mg_dl.toFixed(1)} ${units}` : '—'}
                      </span>
                    </td>
                  )}
                  <td>
                    <span className="font-mono text-slate">
                      [{lo} – {hi}]
                    </span>
                  </td>
                  <td>
                    <span className="font-mono text-slate">{bandwidth} {units}</span>
                  </td>
                  <td>
                    <div className="prob-bar-container">
                      <div 
                        className="prob-fill hypo-fill" 
                        style={{ width: `${Math.min((row.p_hypo ?? row.risk_probabilities?.hypo ?? 0) * 100, 100)}%` }}
                      ></div>
                      <span className={`prob-text ${isHypoAlert ? 'text-danger font-bold' : ''}`}>
                        {(((row.p_hypo ?? row.risk_probabilities?.hypo ?? 0) * 100)).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="prob-bar-container">
                      <div 
                        className="prob-fill normal-fill" 
                        style={{ width: `${Math.min((row.p_normal ?? row.risk_probabilities?.normal ?? 0) * 100, 100)}%` }}
                      ></div>
                      <span className="prob-text">
                        {(((row.p_normal ?? row.risk_probabilities?.normal ?? 0) * 100)).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="prob-bar-container">
                      <div 
                        className="prob-fill hyper-fill" 
                        style={{ width: `${Math.min((row.p_hyper ?? row.risk_probabilities?.hyper ?? 0) * 100, 100)}%` }}
                      ></div>
                      <span className={`prob-text ${isHyperAlert ? 'text-warning font-bold' : ''}`}>
                        {(((row.p_hyper ?? row.risk_probabilities?.hyper ?? 0) * 100)).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    {/* Forecast class derived strictly from MEDIAN */}
                    <span className={`risk-status-pill class-${fClass.toLowerCase()}`}>
                      {fClass === 'low' && <ShieldAlert size={13} />}
                      {fClass === 'normal' && <CheckCircle size={13} />}
                      {fClass === 'high' && <AlertTriangle size={13} />}
                      <span>{fClass.toUpperCase()}</span>
                    </span>
                  </td>
                  <td>
                    {/* Separate alert from frozen thresholds */}
                    {alertMsg ? (
                      <span className={`alert-badge ${isHypoAlert ? 'badge-alert-hypo' : 'badge-alert-hyper'}`}>
                        <AlertTriangle size={12} />
                        <span>{alertMsg}</span>
                      </span>
                    ) : (
                      <span className="text-muted text-xs">
                        {[30, 60, 90, 120].includes(row.horizon_minutes) ? 'None' : (
                          <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>Not validated</span>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Checkpoint Hashes & Mandatory Clinical Disclaimer */}
      <div className="table-footer-meta">
        {checkpointHashes && typeof checkpointHashes === 'object' && Object.keys(checkpointHashes).length > 0 && (
          <div className="checkpoint-hashes-row">
            <span className="hash-title">
              <Hash size={13} className="text-teal" />
              <span>Checkpoint SHA-256 Hashes:</span>
            </span>
            <div className="hashes-list">
              {Object.entries(checkpointHashes).map(([seed, h]) => (
                <span key={seed} className="hash-item font-mono" title={`${seed}: ${h}`}>
                  <strong>{seed}:</strong> {h.slice(0, 12)}...
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mandatory-clinical-disclaimer">
          <strong>Mandatory Notice:</strong> Research prototype. Not a medical device. Do not use for insulin dosing,
          treatment decisions or as a safety alert. A forecast of recovery must never delay treating or rechecking a low.
        </div>
      </div>
    </div>
  );
}
