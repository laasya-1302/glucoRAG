import React from 'react';
import { AlertCircle, XCircle, RefreshCw } from 'lucide-react';

export default function ErrorBanner({ error, onRetry, onDismiss }) {
  if (!error) return null;

  return (
    <div className="error-banner" role="alert">
      <div className="error-main">
        <XCircle className="error-icon" size={20} />
        <div>
          <strong className="error-title">Inference Request Failed</strong>
          <p className="error-desc">{error.message || String(error)}</p>
        </div>
      </div>
      <div className="error-actions">
        {onRetry && (
          <button type="button" onClick={onRetry} className="btn-error-retry">
            <RefreshCw size={14} />
            <span>Retry</span>
          </button>
        )}
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="btn-error-dismiss" aria-label="Dismiss error">
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
