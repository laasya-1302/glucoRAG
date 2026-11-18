import React from 'react';
import { Activity, ShieldCheck, AlertCircle, Cpu, User, LogOut, Trash2, Edit3, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function Header({ 
  currentView = 'home',
  onChangeView,
  selectedExp, 
  onSelectExp, 
  availableExps, 
  healthStatus, 
  onRefreshHealth,
  onOpenProfile,
  onTryPrediction
}) {
  const { user, logout, deleteAccount } = useAuth();

  const handleDelete = async () => {
    if (window.confirm("Are you sure you want to permanently delete your account and profile data? This cannot be undone.")) {
      await deleteAccount();
    }
  };

  return (
    <header className="gp-main-header">
      {/* Brand & Logo */}
      <div className="gp-brand-container" onClick={() => onChangeView && onChangeView('home')} style={{ cursor: 'pointer' }}>
        <div className="gp-logo-badge">
          {/* Teardrop droplet icon matching screenshot */}
          <svg viewBox="0 0 24 24" fill="none" className="gp-droplet-icon" stroke="#0D766E" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
          </svg>
        </div>
        <div className="gp-brand-text">
          <div className="gp-brand-title">
            GPFormer<span className="gp-brand-tm">™</span>
          </div>
          <span className="gp-brand-sub">Glucose Forecasting</span>
        </div>
      </div>

      {/* Nav Links: strictly Home and Patient History */}
      <nav className="gp-nav-links" aria-label="Main Navigation">
        <button
          type="button"
          className={`gp-nav-link ${currentView === 'home' ? 'active' : ''}`}
          onClick={() => onChangeView && onChangeView('home')}
        >
          Home
        </button>
        <button
          type="button"
          className={`gp-nav-link ${currentView === 'history' ? 'active' : ''}`}
          onClick={() => onChangeView && onChangeView('history')}
        >
          Patient History
        </button>
      </nav>

      {/* Header Controls & Profile Actions */}
      <div className="gp-header-actions">
        {/* Model Selector */}
        <div className="gp-model-selector-pill">
          <Cpu size={14} className="text-teal" />
          <select 
            value={selectedExp} 
            onChange={(e) => onSelectExp(e.target.value)}
            className="gp-header-select"
            aria-label="Select trained GPFormer experiment"
          >
            {availableExps && availableExps.length > 0 ? (
              availableExps.map((exp) => (
                <option key={exp.experiment_id} value={exp.experiment_id}>
                  {exp.name}
                </option>
              ))
            ) : (
              <>
                <option value="e1_gpformer">E1 Multimodal (3-Seed Ensemble)</option>
                <option value="gp_A">Experiment A (REPLACE-BG T1D)</option>
                <option value="gp_B">Experiment B (REPLACE-BG + Shanghai T2D)</option>
              </>
            )}
          </select>
        </div>

        {/* Target Range Pill */}
        <div className="gp-target-pill">
          <span className="gp-target-dot"></span>
          <span className="gp-target-text">70–180 mg/dL</span>
        </div>

        {/* Health status badge */}
        <div 
          className={`gp-health-pill ${healthStatus?.online ? 'healthy' : 'degraded'}`}
          title={healthStatus?.online ? "API and Model Loaded" : "API Offline or Connecting..."}
          onClick={onRefreshHealth}
        >
          {healthStatus?.online ? (
            <>
              <ShieldCheck size={14} />
              <span>Model Ready</span>
            </>
          ) : (
            <>
              <AlertCircle size={14} />
              <span>Offline</span>
            </>
          )}
        </div>

        {/* Orange "Try Prediction" CTA Button from screenshot */}
        <button
          type="button"
          className="gp-btn-cta-orange"
          onClick={() => {
            if (onChangeView) onChangeView('home');
            if (onTryPrediction) onTryPrediction();
          }}
        >
          Try Prediction
        </button>

        {/* User Profile Pill & Actions */}
        {user && (
          <div className="gp-user-profile-menu">
            <div className="gp-user-info" title={`Signed in as ${user.email}`}>
              <User size={14} className="text-teal" />
              <span className="gp-user-name">{user.name?.split(' ')[0] || user.name}</span>
            </div>

            <button
              type="button"
              className="btn-icon-subtle"
              onClick={onOpenProfile}
              title="Edit Profile"
              aria-label="Edit Profile"
            >
              <Edit3 size={14} />
            </button>

            <button
              type="button"
              className="btn-icon-subtle text-amber"
              onClick={handleDelete}
              title="Delete My Account and Data"
              aria-label="Delete Account"
            >
              <Trash2 size={14} />
            </button>

            <button
              type="button"
              className="btn-icon-subtle text-muted"
              onClick={logout}
              title="Logout"
              aria-label="Logout"
            >
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
