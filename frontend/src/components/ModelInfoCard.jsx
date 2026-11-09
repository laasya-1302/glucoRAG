import React from 'react';
import { Cpu, CheckCircle2, Shield, Layers, HelpCircle, AlertOctagon } from 'lucide-react';

export default function ModelInfoCard({ modelInfo, activeExperiment, onSelectExperiment }) {
  if (!modelInfo) return null;

  return (
    <div className="card model-info-card">
      <div className="card-header">
        <div>
          <h2 className="card-title flex-align">
            <Cpu size={18} className="text-teal" />
            <span>Trained GPFormer Checkpoint & Configuration</span>
          </h2>
          <p className="card-description">
            Architecture and normalization statistics loaded from your training runs.
          </p>
        </div>
      </div>

      <div className="experiments-grid">
        {modelInfo.available_experiments?.map((exp) => {
          const isSelected = exp.experiment_id === activeExperiment;

          return (
            <div 
              key={exp.experiment_id}
              className={`experiment-card ${isSelected ? 'selected' : ''}`}
              onClick={() => onSelectExperiment(exp.experiment_id)}
            >
              <div className="exp-card-header">
                <div className="flex-align gap-2">
                  <span className={`radio-dot ${isSelected ? 'checked' : ''}`}></span>
                  <h4 className="exp-name">{exp.name}</h4>
                </div>
                {exp.checkpoint_available && (
                  <span className="badge-available">
                    <CheckCircle2 size={12} />
                    <span>{exp.experiment_id === 'e1_gpformer' ? '3-seed ensemble ready' : 'best.pt ready'}</span>
                  </span>
                )}
              </div>

              <p className="exp-desc">{exp.description}</p>

              <div className="exp-meta-rows">
                <div className="meta-row">
                  <span>Training Cohorts:</span>
                  <strong>{exp.training_sources.join(', ') || 'N/A'}</strong>
                </div>
                <div className="meta-row">
                  <span>Training Norm Mean:</span>
                  <strong>{exp.normalization_mean} mg/dL</strong>
                </div>
                <div className="meta-row">
                  <span>Training Norm Std:</span>
                  <strong>{exp.normalization_std} mg/dL</strong>
                </div>
              </div>

              <div className="exp-select-action">
                <button 
                  type="button" 
                  className={`btn-select ${isSelected ? 'btn-select-active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectExperiment(exp.experiment_id);
                  }}
                >
                  {isSelected ? "Currently Active Model" : "Switch to this Model"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="model-specs-strip">
        <div className="spec-item">
          <span className="spec-label">History Window:</span>
          <strong>24 Steps (6 Hours)</strong>
        </div>
        <div className="spec-item">
          <span className="spec-label">Sampling Step:</span>
          <strong>15 Minutes</strong>
        </div>
        <div className="spec-item">
          <span className="spec-label">Forecast Horizon:</span>
          <strong>8 Steps (+15m to +120m)</strong>
        </div>
        <div className="spec-item">
          <span className="spec-label">Quantiles (5):</span>
          <strong>10%, 25%, 50%, 75%, 90%</strong>
        </div>
        <div className="spec-item">
          <span className="spec-label">Risk Classification:</span>
          <strong>HYPO (&lt;70) | NORMAL | HYPER (&gt;180)</strong>
        </div>
      </div>

      <div className="medical-disclaimer-box">
        <AlertOctagon size={18} className="text-danger flex-shrink-0" />
        <div className="disclaimer-text">
          <strong>Mandatory Medical Notice:</strong>
          <p>
            GPFormer glucose forecasts and risk predictions are experimental algorithmic outputs for research demonstration.
            They do not constitute medical diagnoses, treatment instructions, or continuous glucose monitor (CGM) replacements.
            Never adjust insulin dosages, medication, or medical treatment based on these projections without consulting a physician.
          </p>
        </div>
      </div>
    </div>
  );
}
