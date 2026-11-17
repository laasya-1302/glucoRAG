import React, { useState } from 'react';
import { Activity, ShieldCheck, AlertTriangle, ArrowRight, Lock, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { loginWithGoogle, loginWithMock, authError } = useAuth();
  const [isMockLoading, setIsMockLoading] = useState(false);
  const [mockEmail, setMockEmail] = useState('researcher@example.org');
  const [mockName, setMockName] = useState('Dr. Jane Research');
  const [showMockOptions, setShowMockOptions] = useState(false);
  const [localError, setLocalError] = useState(null);

  // Check URL query parameters for OAuth error
  const urlParams = new URLSearchParams(window.location.search);
  const oauthError = urlParams.get('error');

  const handleMockSubmit = async (e) => {
    e.preventDefault();
    setLocalError(null);
    setIsMockLoading(true);
    try {
      await loginWithMock({ email: mockEmail, name: mockName });
    } catch (err) {
      setLocalError(err.message || 'Mock sign-in failed');
    } finally {
      setIsMockLoading(false);
    }
  };

  return (
    <div className="login-page-container">
      <div className="login-card">
        {/* Brand Header */}
        <div className="login-header">
          <div className="login-logo-badge">
            <Activity className="icon-pulse" size={32} />
          </div>
          <h1 className="login-title">
            <span className="brand-accent">BIO</span>TECTIVE<span className="brand-tm">™</span>
          </h1>
          <p className="login-subtitle">GPFormer Clinical Glucose Forecasting Research Prototype</p>
        </div>

        {/* Error Banners */}
        {(oauthError || authError || localError) && (
          <div className="login-error-banner" role="alert">
            <AlertTriangle size={18} />
            <div>
              <strong>Sign-in Error: </strong>
              <span>
                {oauthError === 'access_denied'
                  ? 'Access was cancelled or denied by provider.'
                  : localError || authError || oauthError || 'Authentication could not be completed.'}
              </span>
            </div>
          </div>
        )}

        {/* Primary OAuth Action */}
        <div className="login-actions">
          <button
            type="button"
            className="btn-google-login"
            onClick={loginWithGoogle}
            id="google-signin-btn"
          >
            <svg className="google-icon" viewBox="0 0 24 24" width="20" height="20">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            <span>Continue with Google</span>
          </button>
        </div>

        {/* Feature Highlights */}
        <div className="login-features">
          <div className="feature-item">
            <ShieldCheck size={16} className="text-teal" />
            <span>OAuth 2.0 / OIDC PKCE Security with httpOnly Session</span>
          </div>
          <div className="feature-item">
            <Lock size={16} className="text-emerald" />
            <span>Zero Persistent Storage of Health Data (Readings, Insulin, Carbs)</span>
          </div>
        </div>

        {/* Development / Test Mock Login Accordion */}
        <div className="mock-login-section">
          <button
            type="button"
            className="btn-mock-toggle"
            onClick={() => setShowMockOptions(!showMockOptions)}
          >
            {showMockOptions ? 'Hide Test / Local Sign-in' : 'Developer / Local Test Sign-in ▼'}
          </button>

          {showMockOptions && (
            <form onSubmit={handleMockSubmit} className="mock-login-form">
              <div className="form-group-sm">
                <label>Email Address</label>
                <input
                  type="email"
                  value={mockEmail}
                  onChange={(e) => setMockEmail(e.target.value)}
                  className="input-sm"
                  required
                />
              </div>
              <div className="form-group-sm">
                <label>Full Name</label>
                <input
                  type="text"
                  value={mockName}
                  onChange={(e) => setMockName(e.target.value)}
                  className="input-sm"
                  required
                />
              </div>
              <button
                type="submit"
                className="btn-sm btn-secondary"
                disabled={isMockLoading}
              >
                {isMockLoading ? 'Signing in...' : 'Sign In as Test User'}
              </button>
            </form>
          )}
        </div>

        {/* Research Disclaimer */}
        <div className="login-disclaimer">
          <strong>Research Prototype Notice:</strong>
          <p>
            Not a medical device. Do not use for insulin dosing, treatment decisions or as a safety
            alert. A forecast of recovery must never delay treating or rechecking a low glucose reading.
          </p>
        </div>
      </div>
    </div>
  );
}
