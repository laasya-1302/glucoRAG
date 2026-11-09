import React from 'react';
import { Table, ShieldAlert, CheckCircle, AlertTriangle } from 'lucide-react';

export default function ForecastTable({ forecast, units = "mg/dL" }) {
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
            <span>8-Step Quantile Forecast & Multi-Task Risk Distribution</span>
          </h2>
          <p className="card-description">
            Quantile forecasts and class probabilities output directly by the trained GPFormer architecture.
          </p>
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
              <th>10%–90% Interval</th>
              <th>Bandwidth</th>
              <th>Hypo Risk (&lt;70)</th>
              <th>Normal (70-180)</th>
              <th>Hyper Risk (&gt;180)</th>
              <th>Risk Status</th>
            </tr>
          </thead>
          <tbody>
            {forecast.map((row) => {
              const isHypo = row.predicted_risk_class === 'HYPO';
              const isHyper = row.predicted_risk_class === 'HYPER';
              const isNormal = row.predicted_risk_class === 'NORMAL';
              const hypoAlert = row.risk_probabilities.hypo >= 0.30;

              return (
                <tr key={row.step} className={hypoAlert ? 'row-alert' : ''}>
                  <td className="font-semibold text-center">#{row.step}</td>
                  <td>
                    <span className="horizon-badge">+{row.horizon_minutes} min</span>
                  </td>
                  <td className="text-muted">{formatTime(row.timestamp)}</td>
                  <td>
                    <strong className="glucose-val text-teal">
                      {row.glucose_median} <span className="unit-label">{units}</span>
                    </strong>
                  </td>
                  <td>
                    <span className="font-mono text-slate">
                      [{row.uncertainty_band.low_q10} – {row.uncertainty_band.high_q90}]
                    </span>
                  </td>
                  <td>
                    <span className="bandwidth-badge">
                      ±{(row.uncertainty_band.bandwidth / 2).toFixed(1)} {units}
                    </span>
                  </td>
                  <td>
                    <div className="prob-bar-container">
                      <div 
                        className="prob-fill hypo-fill" 
                        style={{ width: `${Math.min(row.risk_probabilities.hypo * 100, 100)}%` }}
                      ></div>
                      <span className={`prob-text ${hypoAlert ? 'text-danger font-bold' : ''}`}>
                        {(row.risk_probabilities.hypo * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="prob-bar-container">
                      <div 
                        className="prob-fill normal-fill" 
                        style={{ width: `${Math.min(row.risk_probabilities.normal * 100, 100)}%` }}
                      ></div>
                      <span className="prob-text">
                        {(row.risk_probabilities.normal * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="prob-bar-container">
                      <div 
                        className="prob-fill hyper-fill" 
                        style={{ width: `${Math.min(row.risk_probabilities.hyper * 100, 100)}%` }}
                      ></div>
                      <span className={`prob-text ${row.risk_probabilities.hyper >= 0.5 ? 'text-warning font-bold' : ''}`}>
                        {(row.risk_probabilities.hyper * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={`risk-status-pill ${row.predicted_risk_class.toLowerCase()}`}>
                      {isHypo && <ShieldAlert size={13} />}
                      {isNormal && <CheckCircle size={13} />}
                      {isHyper && <AlertTriangle size={13} />}
                      <span>{row.predicted_risk_class}</span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
