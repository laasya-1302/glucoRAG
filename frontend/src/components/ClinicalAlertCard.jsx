import React from 'react';
import { ShieldCheck, ShieldAlert, AlertTriangle, AlertCircle, Info } from 'lucide-react';

export default function ClinicalAlertCard({ alert, experimentName, disclaimer, mode }) {
  if (!alert) return null;

  const isHypo = alert.status === "HYPO_RISK";
  const isHyper = alert.status === "HYPER_RISK";
  const isNormal = alert.status === "NORMAL";

  let alertClass = "alert-normal";
  let IconComponent = ShieldCheck;
  let title = "Normal Glucose Trajectory";

  if (isHypo) {
    alertClass = "alert-hypo";
    IconComponent = ShieldAlert;
    title = "Hypoglycemia Risk Detected (< 70 mg/dL)";
  } else if (isHyper) {
    alertClass = "alert-hyper";
    IconComponent = AlertTriangle;
    title = "Hyperglycemia Risk Projected (> 180 mg/dL)";
  }

  return (
    <div className={`clinical-alert-box ${alertClass}`}>
      <div className="alert-content">
        <div className="alert-icon-wrapper">
          <IconComponent size={28} />
        </div>
        <div className="alert-text-body">
          <div className="alert-headline-row">
            <h3 className="alert-headline">{title}</h3>
            {alert.alert_horizon_minutes && (
              <span className="alert-time-pill">
                Earliest Horizon: +{alert.alert_horizon_minutes} min
              </span>
            )}
            <span className="model-source-pill">{experimentName}</span>
            {mode && (
              <span 
                className="mode-pill"
                style={{
                  background: mode === 'E1' ? '#ecfdf5' : '#f1f5f9',
                  color: mode === 'E1' ? '#047857' : '#475569',
                  border: `1px solid ${mode === 'E1' ? '#a7f3d0' : '#cbd5e1'}`,
                  borderRadius: '12px',
                  padding: '2px 8px',
                  fontSize: '0.75rem',
                  fontWeight: 600
                }}
              >
                {mode === 'E1' ? 'Multimodal (CGM + Events)' : 'CGM-Only Mode'}
              </span>
            )}
          </div>
          <p className="alert-message">{alert.message}</p>
        </div>
      </div>

      <div className="disclaimer-ribbon">
        <AlertCircle size={14} className="disclaimer-icon" />
        <span>
          <strong>Medical Notice:</strong> {disclaimer || "Forecasts are research model predictions and do not replace certified CGM or clinical advice."}
        </span>
      </div>
    </div>
  );
}
