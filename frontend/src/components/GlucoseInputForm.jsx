import React, { useState } from 'react';
import { Clock, RotateCcw, Play, Sparkles, AlertTriangle, CheckCircle2 } from 'lucide-react';

const SYNTHETIC_SAMPLE = [
  142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145,
  148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139
];

export default function GlucoseInputForm({
  readings,
  setReadings,
  latestTimestamp,
  setLatestTimestamp,
  onSubmit,
  isLoading,
  formError,
  setFormError
}) {
  const [selectedPreset, setSelectedPreset] = useState('normal');

  const handleReadingChange = (index, val) => {
    const updated = [...readings];
    updated[index] = val;
    setReadings(updated);
    if (formError) setFormError(null);
  };

  const handleFillSynthetic = (type = 'default') => {
    setSelectedPreset(type);
    let sample = [...SYNTHETIC_SAMPLE];
    if (type === 'hypo_trend') {
      // Downward trend toward hypoglycemia
      sample = [
        135, 130, 125, 122, 118, 115, 110, 105, 100, 96, 92, 88,
        85, 82, 80, 78, 76, 74, 72, 71, 70, 68, 67, 65
      ];
    } else if (type === 'hyper_trend') {
      // Upward trend toward hyperglycemia
      sample = [
        140, 145, 150, 156, 162, 168, 175, 180, 185, 192, 198, 205,
        210, 218, 224, 230, 235, 240, 242, 245, 248, 252, 255, 260
      ];
    }
    setReadings(sample.map(String));
    if (formError) setFormError(null);
  };

  const handleReset = () => {
    setReadings(Array(24).fill(''));
    if (formError) setFormError(null);
  };

  // Compute stats on valid numbers
  const validNumbers = readings
    .map(r => parseFloat(r))
    .filter(n => !isNaN(n) && isFinite(n));

  const countValid = validNumbers.length;
  const meanVal = countValid > 0 ? (validNumbers.reduce((a, b) => a + b, 0) / countValid).toFixed(1) : '--';
  const minVal = countValid > 0 ? Math.min(...validNumbers).toFixed(1) : '--';
  const maxVal = countValid > 0 ? Math.max(...validNumbers).toFixed(1) : '--';

  return (
    <div className="card input-card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Historical Continuous Glucose Input</h2>
          <p className="card-description">
            Provide exactly 24 chronological readings (6 hours at 15-minute intervals).
          </p>
        </div>
        <div className="synthetic-badge-container">
          <span className="badge-synthetic">
            <Sparkles size={13} />
            Synthetic Test Patterns
          </span>
          <button 
            type="button" 
            className={`btn-subtle ${selectedPreset === 'normal' ? 'active' : ''}`}
            onClick={() => handleFillSynthetic('default')}
            title="Load illustrative normal trend (24 readings)"
          >
            Sample A (Stable)
          </button>
          <button 
            type="button" 
            className={`btn-subtle ${selectedPreset === 'hypo_trend' ? 'active' : ''}`}
            onClick={() => handleFillSynthetic('hypo_trend')}
            title="Load illustrative downward trend (Hypo risk)"
          >
            Sample B (Low)
          </button>
          <button 
            type="button" 
            className={`btn-subtle ${selectedPreset === 'hyper_trend' ? 'active' : ''}`}
            onClick={() => handleFillSynthetic('hyper_trend')}
            title="Load illustrative upward trend (Hyper risk)"
          >
            Sample C (High)
          </button>
        </div>
      </div>

      {/* Timestamp configuration */}
      <div className="timestamp-bar">
        <div className="timestamp-field">
          <label htmlFor="latest-timestamp-input" className="field-label">
            <Clock size={16} className="text-teal" />
            <span>Latest Reading Timestamp (t = 0 min):</span>
          </label>
          <input 
            id="latest-timestamp-input"
            type="datetime-local" 
            value={latestTimestamp}
            onChange={(e) => setLatestTimestamp(e.target.value)}
            className="input-datetime"
            step="60"
          />
        </div>
        <div className="input-stats">
          <div className="stat-pill">
            <span className="stat-label">Valid Entries:</span>
            <strong className={`stat-num ${countValid === 24 ? 'text-emerald' : 'text-amber'}`}>
              {countValid} / 24
            </strong>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Mean:</span>
            <strong>{meanVal} mg/dL</strong>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Range:</span>
            <strong>{minVal} – {maxVal}</strong>
          </div>
        </div>
      </div>

      {/* 24 Input Grid */}
      <form onSubmit={onSubmit}>
        <div className="grid-24-container">
          {readings.map((val, idx) => {
            const minsAgo = (23 - idx) * 15;
            const isNow = idx === 23;
            const num = parseFloat(val);
            const isInvalid = val !== '' && (isNaN(num) || num < 20 || num > 600);
            const isHypo = !isInvalid && !isNaN(num) && num < 70;
            const isHyper = !isInvalid && !isNaN(num) && num > 180;

            let cellClass = "reading-cell";
            if (isNow) cellClass += " cell-now";
            if (isInvalid) cellClass += " cell-invalid";
            else if (isHypo) cellClass += " cell-hypo";
            else if (isHyper) cellClass += " cell-hyper";

            return (
              <div key={idx} className={cellClass}>
                <div className="cell-header">
                  <span className="cell-index">#{idx + 1}</span>
                  <span className="cell-time">{isNow ? 'Now' : `-${minsAgo}m`}</span>
                </div>
                <input
                  type="number"
                  step="0.1"
                  min="20"
                  max="600"
                  placeholder="mg/dL"
                  value={val}
                  onChange={(e) => handleReadingChange(idx, e.target.value)}
                  className="cell-input"
                  required
                  aria-label={`Glucose reading at ${isNow ? 'current time' : `-${minsAgo} minutes`}`}
                />
              </div>
            );
          })}
        </div>

        {formError && (
          <div className="form-error-banner" role="alert">
            <AlertTriangle size={18} />
            <span>{formError}</span>
          </div>
        )}

        <div className="form-actions">
          <button 
            type="button" 
            onClick={handleReset} 
            className="btn btn-secondary"
            disabled={isLoading}
          >
            <RotateCcw size={16} />
            <span>Clear Grid</span>
          </button>

          <button 
            type="submit" 
            className="btn btn-primary"
            disabled={isLoading || countValid !== 24}
          >
            {isLoading ? (
              <>
                <div className="spinner"></div>
                <span>Executing GPFormer Inference...</span>
              </>
            ) : (
              <>
                <Play size={16} fill="currentColor" />
                <span>Predict Glucose</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
