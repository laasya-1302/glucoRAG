import React from 'react';
import { ShieldCheck, ShieldAlert, AlertTriangle, AlertCircle } from 'lucide-react';

export default function ClinicalAlertCard({
  alert,
  experimentName,
  disclaimer,
  mode,
  _inputsUsed,
  compareWithCgmOnly = false,
  onToggleCompare = null,
  isComparing = false
}) {
  if (!alert) return null;

  const isHypo = alert.status === "HYPO_RISK";
  const isHyper = alert.status === "HYPER_RISK";

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

  // Determine mode label and styling ("glucose + insulin + carbs" or "glucose only")
  const isMultimodal = mode === 'E1';

  let modeLabel = null;
  let modeClass = 'mode-cgmonly';
  if (mode) {
    if (isMultimodal) {
      modeLabel = 'glucose + insulin + carbs';
      modeClass = 'mode-multimodal';
    } else {
      modeLabel = 'glucose only';
      modeClass = 'mode-cgmonly';
    }
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
            {modeLabel && (
              <span className={`mode-label ${modeClass}`}>
                {modeLabel}
              </span>
            )}
          </div>
          <p className="alert-message">{alert.message}</p>
          {isMultimodal && (
            <div className="multimodal-meta-row">
              <p className="multimodal-note">
                ⚠ Insulin and carbs usually change the forecast only slightly in testing.
              </p>
              {onToggleCompare && (
                <label className="compare-toggle-label">
                  <input
                    type="checkbox"
                    checked={compareWithCgmOnly}
                    onChange={(e) => onToggleCompare(e.target.checked)}
                    disabled={isComparing}
                  />
                  <span>Compare with glucose only</span>
                  {isComparing && <span className="comparing-spinner">…</span>}
                </label>
              )}
            </div>
          )}
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
