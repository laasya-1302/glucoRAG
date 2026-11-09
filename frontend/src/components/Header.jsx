import React from 'react';
import { Activity, ShieldCheck, AlertCircle, RefreshCw, Cpu } from 'lucide-react';

export default function Header({ 
  selectedExp, 
  onSelectExp, 
  availableExps, 
  healthStatus, 
  onRefreshHealth 
}) {
  return (
    <header className="header-container">
      <div className="header-brand">
        <div className="logo-badge">
          <Activity className="icon-pulse" size={24} />
        </div>
        <div>
          <div className="brand-title">
            <span className="brand-accent">BIO</span>TECTIVE<span className="brand-tm">™</span>
            <span className="model-tag">GPFormer</span>
          </div>
          <p className="brand-subtitle">Clinical Multi-Horizon Blood Glucose Forecasting</p>
        </div>
      </div>

      <div className="header-actions">
        {/* Experiment Selector */}
        <div className="experiment-selector-card">
          <Cpu size={16} className="text-teal" />
          <span className="label-text">Model:</span>
          <select 
            value={selectedExp} 
            onChange={(e) => onSelectExp(e.target.value)}
            className="experiment-dropdown"
            aria-label="Select trained GPFormer experiment"
          >
            {availableExps && availableExps.length > 0 ? (
              availableExps.map((exp) => (
                <option key={exp.experiment_id} value={exp.experiment_id}>
                  {exp.name} ({exp.training_sources.join(', ')})
                </option>
              ))
            ) : (
              <>
                <option value="e1_gpformer">E1 Multimodal GPFormer (3-Seed Ensemble)</option>
                <option value="gp_A">Experiment A (REPLACE-BG T1D)</option>
                <option value="gp_B">Experiment B (REPLACE-BG + Shanghai T2D)</option>
              </>
            )}
          </select>
        </div>

        {/* Target Range Pill */}
        <div className="target-range-pill">
          <span className="range-dot"></span>
          <span className="range-label">Target:</span>
          <strong className="range-val">70 – 180 mg/dL</strong>
        </div>

        {/* Health status */}
        <div 
          className={`health-badge ${healthStatus?.online ? 'healthy' : 'degraded'}`}
          title={healthStatus?.online ? "API and Model Loaded" : "API Offline or Connecting..."}
          onClick={onRefreshHealth}
        >
          {healthStatus?.online ? (
            <>
              <ShieldCheck size={16} />
              <span>Model Ready</span>
            </>
          ) : (
            <>
              <AlertCircle size={16} />
              <span>Offline</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
