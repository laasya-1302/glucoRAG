import React, { useState, useEffect } from 'react';
import { 
  User, Calendar, Activity, ShieldCheck, AlertTriangle, ShieldAlert, 
  FileText, Download, Trash2, ArrowUpRight, RefreshCw, ChevronRight, CheckCircle2,
  Clock, HeartPulse, Sparkles, SlidersHorizontal
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { fetchPredictionHistory, clearPredictionHistory } from '../services/api';

export default function PatientHistoryView({ onOpenProfile, onLoadHistoricalRecord }) {
  const { user } = useAuth();
  const [history, setHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'details', 'values', 'reports'
  const [selectedRecord, setSelectedRecord] = useState(null);

  const loadHistory = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchPredictionHistory(100);
      setHistory(data.history || []);
      if (data.history && data.history.length > 0) {
        setSelectedRecord(data.history[0]);
      }
    } catch (err) {
      setError(err.message || "Failed to load patient history records.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const handleClearHistory = async () => {
    if (window.confirm("Are you sure you want to clear your stored forecast history? This cannot be undone.")) {
      try {
        await clearPredictionHistory();
        setHistory([]);
        setSelectedRecord(null);
      } catch (err) {
        alert("Failed to clear history: " + err.message);
      }
    }
  };

  const handlePrintReport = () => {
    window.print();
  };

  // Compute aggregate statistics from history
  const totalRecords = history.length;
  let allReadings = [];
  let hypoAlertCount = 0;
  let hyperAlertCount = 0;

  history.forEach(rec => {
    const readings = rec.inputs?.readings || [];
    readings.forEach(val => {
      const num = typeof val === 'object' && val !== null ? val.glucose : Number(val);
      if (!isNaN(num) && num > 0) allReadings.push(num);
    });
    const alertStatus = rec.results?.clinical_alert?.status || "";
    if (alertStatus === "HYPO_RISK") hypoAlertCount++;
    if (alertStatus === "HYPER_RISK") hyperAlertCount++;
  });

  const avgGlucose = allReadings.length > 0 
    ? (allReadings.reduce((a, b) => a + b, 0) / allReadings.length).toFixed(1)
    : "—";

  const inTargetCount = allReadings.filter(g => g >= 70 && g <= 180).length;
  const timeInRangePct = allReadings.length > 0 
    ? ((inTargetCount / allReadings.length) * 100).toFixed(0)
    : "—";

  return (
    <div className="patient-history-container">
      {/* View Header */}
      <div className="history-header-card">
        <div className="history-header-left">
          <div className="history-badge-icon">
            <User size={24} className="text-teal" />
          </div>
          <div>
            <h1 className="history-title">Patient Medical History &amp; Records</h1>
            <p className="history-subtitle">
              Comprehensive clinical profile, historical 24-point glucose trajectories, multimodal inputs, and predictive reports.
            </p>
          </div>
        </div>

        <div className="history-header-actions">
          <button 
            type="button" 
            className="btn-history-action btn-refresh" 
            onClick={loadHistory} 
            disabled={isLoading}
            title="Refresh history records"
          >
            <RefreshCw size={15} className={isLoading ? "animate-spin" : ""} />
            <span>Refresh</span>
          </button>

          <button 
            type="button" 
            className="btn-history-action btn-print" 
            onClick={handlePrintReport}
            title="Print or save PDF report"
          >
            <Download size={15} />
            <span>Export Report</span>
          </button>

          {history.length > 0 && (
            <button 
              type="button" 
              className="btn-history-action btn-danger-subtle" 
              onClick={handleClearHistory}
              title="Clear all history records"
            >
              <Trash2 size={15} />
              <span>Clear History</span>
            </button>
          )}
        </div>
      </div>

      {/* Sub-navigation Tabs */}
      <div className="history-tabs-bar">
        <button 
          className={`history-tab-btn ${activeTab === 'all' ? 'active' : ''}`}
          onClick={() => setActiveTab('all')}
        >
          Overview &amp; All Sections
        </button>
        <button 
          className={`history-tab-btn ${activeTab === 'details' ? 'active' : ''}`}
          onClick={() => setActiveTab('details')}
        >
          <User size={15} className="inline-icon" /> Patient Details
        </button>
        <button 
          className={`history-tab-btn ${activeTab === 'values' ? 'active' : ''}`}
          onClick={() => setActiveTab('values')}
        >
          <Activity size={15} className="inline-icon" /> Values &amp; Trajectories
        </button>
        <button 
          className={`history-tab-btn ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          <FileText size={15} className="inline-icon" /> Clinical Forecast Reports
        </button>
      </div>

      {/* Quick Summary Metrics Grid */}
      <div className="history-metrics-grid">
        <div className="metric-box">
          <div className="metric-top">
            <span className="metric-label">Total Predictions Logged</span>
            <Calendar size={18} className="metric-icon text-teal" />
          </div>
          <div className="metric-value">{totalRecords}</div>
          <span className="metric-sub">Chronological model runs</span>
        </div>

        <div className="metric-box">
          <div className="metric-top">
            <span className="metric-label">Historical Mean Glucose</span>
            <Activity size={18} className="metric-icon text-teal" />
          </div>
          <div className="metric-value">{avgGlucose} <span className="metric-unit">mg/dL</span></div>
          <span className="metric-sub">Across all recorded slots</span>
        </div>

        <div className="metric-box">
          <div className="metric-top">
            <span className="metric-label">Estimated Time-In-Range</span>
            <ShieldCheck size={18} className="metric-icon text-emerald" />
          </div>
          <div className="metric-value text-emerald">{timeInRangePct}{timeInRangePct !== "—" ? "%" : ""}</div>
          <span className="metric-sub">Target 70–180 mg/dL</span>
        </div>

        <div className="metric-box">
          <div className="metric-top">
            <span className="metric-label">Alert Flags (Hypo / Hyper)</span>
            <HeartPulse size={18} className="metric-icon text-amber" />
          </div>
          <div className="metric-value">
            <span className="text-danger">{hypoAlertCount}</span> / <span className="text-warning">{hyperAlertCount}</span>
          </div>
          <span className="metric-sub">Calibrated safety alerts triggered</span>
        </div>
      </div>

      {/* ---------------- 1. PATIENT DETAILS SECTION ---------------- */}
      {(activeTab === 'all' || activeTab === 'details') && (
        <div className="history-section-card">
          <div className="section-card-header">
            <div className="section-title-wrap">
              <User size={20} className="text-teal" />
              <h2>1. Patient Clinical Details</h2>
            </div>
            {onOpenProfile && (
              <button 
                type="button" 
                className="btn-edit-profile-action" 
                onClick={onOpenProfile}
              >
                Edit Clinical Profile
              </button>
            )}
          </div>

          <div className="patient-details-grid">
            <div className="detail-item">
              <span className="detail-label">Full Name</span>
              <strong className="detail-value">{user?.name || "Dr. Jane Research (Default Profile)"}</strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Email Account</span>
              <strong className="detail-value font-mono">{user?.email || "researcher@example.org"}</strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Age</span>
              <strong className="detail-value">{user?.age ? `${user.age} years` : "30 years"}</strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Biological Gender</span>
              <strong className="detail-value">{user?.gender || "Not specified"}</strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Clinical Target Range</span>
              <strong className="detail-value text-teal">70 – 180 mg/dL</strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Sampling Cadence</span>
              <strong className="detail-value">15 minutes (6h window = 24 points)</strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Pediatric / Minor Status</span>
              <strong className="detail-value">
                {user?.age && user.age < 18 ? (
                  <span className="badge-minor">Minor (Confirmed Consent)</span>
                ) : (
                  <span className="badge-adult">Adult Patient (18+)</span>
                )}
              </strong>
            </div>

            <div className="detail-item">
              <span className="detail-label">Account Security</span>
              <strong className="detail-value">OAuth 2.0 PKCE / Encrypted Session</strong>
            </div>
          </div>
        </div>
      )}

      {/* ---------------- 2. VALUES & TRAJECTORIES SECTION ---------------- */}
      {(activeTab === 'all' || activeTab === 'values') && (
        <div className="history-section-card">
          <div className="section-card-header">
            <div className="section-title-wrap">
              <Activity size={20} className="text-teal" />
              <h2>2. Historical Glucose Values &amp; Multimodal Inputs</h2>
            </div>
            <span className="badge-count">{history.length} records</span>
          </div>

          {isLoading ? (
            <div className="history-loading-box">
              <RefreshCw size={24} className="animate-spin text-teal" />
              <p>Loading historical values and prediction runs...</p>
            </div>
          ) : history.length === 0 ? (
            <div className="history-empty-box">
              <p>No forecast records found in database yet.</p>
              <span className="empty-hint">Run a prediction on the Home tab to log your first 24-point glucose record!</span>
            </div>
          ) : (
            <div className="history-table-responsive">
              <table className="history-data-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Model</th>
                    <th>Latest Glucose</th>
                    <th>Input Window (24 Pts)</th>
                    <th>Multimodal Events</th>
                    <th>Forecast +30m</th>
                    <th>Risk Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((rec) => {
                    const readings = rec.inputs?.readings || [];
                    const nums = readings.map(v => typeof v === 'object' && v !== null ? v.glucose : Number(v)).filter(n => !isNaN(n));
                    const latestG = nums.length > 0 ? nums[nums.length - 1] : "—";
                    const minG = nums.length > 0 ? Math.min(...nums) : "—";
                    const maxG = nums.length > 0 ? Math.max(...nums) : "—";
                    const bolusCount = Array.isArray(rec.inputs?.bolus) ? rec.inputs.bolus.length : (Array.isArray(rec.inputs?.bolus_events) ? rec.inputs.bolus_events.length : 0);
                    const carbsCount = Array.isArray(rec.inputs?.carbs) ? rec.inputs.carbs.length : (Array.isArray(rec.inputs?.carb_events) ? rec.inputs.carb_events.length : 0);
                    const alert = rec.results?.clinical_alert || {};
                    const isHypo = alert.status === "HYPO_RISK";
                    const isHyper = alert.status === "HYPER_RISK";

                    return (
                      <tr 
                        key={rec.id} 
                        className={`history-row ${selectedRecord?.id === rec.id ? 'row-selected' : ''}`}
                        onClick={() => setSelectedRecord(rec)}
                      >
                        <td className="font-mono text-xs">
                          {new Date(rec.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                        </td>
                        <td>
                          <span className="badge-model-tag">{rec.model_id}</span>
                        </td>
                        <td>
                          <strong className="text-teal font-semibold">{latestG} mg/dL</strong>
                        </td>
                        <td>
                          <div className="readings-spark-summary">
                            <span className="text-xs text-muted">Range: [{minG} – {maxG}]</span>
                            <div className="spark-bar">
                              {nums.slice(-8).map((val, idx) => (
                                <span 
                                  key={idx} 
                                  className={`spark-dot ${val < 70 ? 'dot-hypo' : val > 180 ? 'dot-hyper' : 'dot-normal'}`} 
                                  title={`Point ${idx + 1}: ${val} mg/dL`}
                                />
                              ))}
                            </div>
                          </div>
                        </td>
                        <td>
                          {bolusCount > 0 || carbsCount > 0 ? (
                            <span className="badge-multimodal-used">
                              {bolusCount > 0 ? `${bolusCount} bolus` : ''}
                              {bolusCount > 0 && carbsCount > 0 ? ' • ' : ''}
                              {carbsCount > 0 ? `${carbsCount} carbs` : ''}
                            </span>
                          ) : (
                            <span className="text-xs text-muted">CGM only</span>
                          )}
                        </td>
                        <td>
                          <strong>{rec.results?.forecast_30m ? `${rec.results.forecast_30m} mg/dL` : "—"}</strong>
                        </td>
                        <td>
                          <span className={`risk-mini-badge ${isHypo ? 'risk-hypo' : isHyper ? 'risk-hyper' : 'risk-normal'}`}>
                            {isHypo ? "HYPO RISK" : isHyper ? "HYPER RISK" : "NORMAL"}
                          </span>
                        </td>
                        <td>
                          {onLoadHistoricalRecord && (
                            <button
                              type="button"
                              className="btn-load-sequence"
                              onClick={(e) => {
                                e.stopPropagation();
                                onLoadHistoricalRecord(rec);
                              }}
                              title="Load this 24-point sequence back into the active Forecaster"
                            >
                              Load <ArrowUpRight size={13} />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ---------------- 3. CLINICAL FORECAST REPORTS SECTION ---------------- */}
      {(activeTab === 'all' || activeTab === 'reports') && (
        <div className="history-section-card">
          <div className="section-card-header">
            <div className="section-title-wrap">
              <FileText size={20} className="text-teal" />
              <h2>3. Clinical Forecast Reports &amp; Horizon Predictions</h2>
            </div>
            {selectedRecord && (
              <span className="text-xs text-muted">
                Showing details for run at {new Date(selectedRecord.timestamp).toLocaleTimeString()}
              </span>
            )}
          </div>

          {selectedRecord ? (
            <div className="report-detail-layout">
              {/* Selected Run Clinical Card */}
              <div className="report-hero-card">
                <div className="report-hero-top">
                  <div>
                    <span className="report-tag">CLINICAL PREDICTION REPORT</span>
                    <h3 className="report-hero-title">
                      Model: {selectedRecord.model_id} &bull; {new Date(selectedRecord.timestamp).toLocaleString()}
                    </h3>
                  </div>

                  <div className={`report-status-pill ${selectedRecord.results?.clinical_alert?.status === 'HYPO_RISK' ? 'status-hypo' : selectedRecord.results?.clinical_alert?.status === 'HYPER_RISK' ? 'status-hyper' : 'status-normal'}`}>
                    {selectedRecord.results?.clinical_alert?.status || "NORMAL"}
                  </div>
                </div>

                <p className="report-alert-message">
                  <strong>Clinical Flag:</strong> {selectedRecord.results?.clinical_alert?.message || "No immediate hypo/hyperglycemic risk flags triggered."}
                </p>

                {/* Horizon Prediction Summary Cards */}
                <div className="horizon-cards-row">
                  <div className="horizon-box">
                    <span className="horizon-label">+30 Minutes</span>
                    <div className="horizon-val">{selectedRecord.results?.forecast_30m || "—"} <span className="unit">mg/dL</span></div>
                    <span className="horizon-note">Earliest alert horizon</span>
                  </div>

                  <div className="horizon-box">
                    <span className="horizon-label">+60 Minutes</span>
                    <div className="horizon-val">{selectedRecord.results?.forecast_60m || "—"} <span className="unit">mg/dL</span></div>
                    <span className="horizon-note">1-hour postprandial</span>
                  </div>

                  <div className="horizon-box">
                    <span className="horizon-label">+90 Minutes</span>
                    <div className="horizon-val">{selectedRecord.results?.forecast_90m || "—"} <span className="unit">mg/dL</span></div>
                    <span className="horizon-note">Peak insulin action</span>
                  </div>

                  <div className="horizon-box">
                    <span className="horizon-label">+120 Minutes</span>
                    <div className="horizon-val">{selectedRecord.results?.forecast_120m || "—"} <span className="unit">mg/dL</span></div>
                    <span className="horizon-note">2-hour clinical horizon</span>
                  </div>
                </div>

                {/* Full 8-step breakdown table for the selected report */}
                {Array.isArray(selectedRecord.results?.forecast) && selectedRecord.results.forecast.length > 0 && (
                  <div className="report-steps-table-wrap">
                    <h4 className="report-table-heading">Multi-Horizon Quantile Trajectory &amp; Probabilities</h4>
                    <table className="report-steps-table">
                      <thead>
                        <tr>
                          <th>Horizon</th>
                          <th>Est. Time</th>
                          <th>Median Glucose</th>
                          <th>10%–90% Interval</th>
                          <th>Hypo Prob (&lt;70)</th>
                          <th>Normal Prob (70-180)</th>
                          <th>Hyper Prob (&gt;180)</th>
                          <th>Class</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedRecord.results.forecast.map((step) => {
                          const med = step.median ?? step.glucose_median;
                          const lo = step.lo ?? step.uncertainty_band?.low_q10;
                          const hi = step.hi ?? step.uncertainty_band?.high_q90;
                          const pHypo = (step.p_hypo ?? step.risk_probabilities?.hypo ?? 0) * 100;
                          const pNorm = (step.p_normal ?? step.risk_probabilities?.normal ?? 0) * 100;
                          const pHyper = (step.p_hyper ?? step.risk_probabilities?.hyper ?? 0) * 100;
                          const fClass = step.forecast_class || (med < 70 ? 'low' : med <= 180 ? 'normal' : 'high');

                          return (
                            <tr key={step.step || step.horizon_minutes}>
                              <td className="font-semibold">+{step.horizon_minutes} min</td>
                              <td className="text-muted text-xs">
                                {step.timestamp ? new Date(step.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "—"}
                              </td>
                              <td><strong className="text-teal">{med} mg/dL</strong></td>
                              <td className="font-mono text-xs">[{lo} – {hi}]</td>
                              <td className={pHypo >= 30 ? "text-danger font-bold" : ""}>{pHypo.toFixed(1)}%</td>
                              <td>{pNorm.toFixed(1)}%</td>
                              <td className={pHyper >= 40 ? "text-warning font-bold" : ""}>{pHyper.toFixed(1)}%</td>
                              <td>
                                <span className={`risk-mini-badge class-${fClass}`}>
                                  {fClass.toUpperCase()}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="report-disclaimer-box">
                  <strong>Medical Notice:</strong> Predictions are generated by the calibrated GPFormer research model and do not replace certified CGM measurements or physician guidance.
                </div>
              </div>
            </div>
          ) : (
            <div className="history-empty-box">
              <p>Select a historical prediction run above to inspect its multi-horizon report.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
