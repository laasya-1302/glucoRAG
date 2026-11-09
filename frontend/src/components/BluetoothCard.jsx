import React from 'react';
import { 
  Bluetooth, 
  BluetoothConnected, 
  BluetoothOff, 
  RefreshCw, 
  Radio, 
  Trash2, 
  Activity, 
  Clock, 
  Smartphone,
  CheckCircle,
  AlertCircle
} from 'lucide-react';

export default function BluetoothCard({
  bleStatus,
  onConnect,
  onDisconnect,
  onRequestHistory,
  onClearHistory,
  latestReading,
  receivedCount,
  transferProgress,
  isConnecting
}) {
  const isConnected = bleStatus.state === 'connected';

  return (
    <div className="card ble-card">
      <div className="card-header">
        <div className="ble-header-left">
          <div className={`ble-status-icon-box ${isConnected ? 'connected' : isConnecting ? 'connecting' : 'disconnected'}`}>
            {isConnected ? (
              <BluetoothConnected size={22} className="text-ble-active" />
            ) : isConnecting ? (
              <RefreshCw size={22} className="spin text-ble-connecting" />
            ) : (
              <Bluetooth size={22} className="text-ble-idle" />
            )}
          </div>
          <div>
            <div className="ble-title-row">
              <h2 className="card-title">Bluetooth Glucose Receiver (BLE)</h2>
              <span className={`status-pill ${isConnected ? 'pill-connected' : 'pill-disconnected'}`}>
                {isConnected ? 'Connected' : isConnecting ? 'Connecting...' : 'Disconnected'}
              </span>
            </div>
            <p className="card-description">
              Direct connection from Android Phone (GATT Server) to React Dashboard via Web Bluetooth API.
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="ble-actions">
          {!isConnected ? (
            <button
              type="button"
              className="btn btn-primary btn-ble"
              onClick={onConnect}
              disabled={isConnecting}
            >
              <Bluetooth size={16} />
              <span>{isConnecting ? 'Searching...' : 'Connect Bluetooth Device'}</span>
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-secondary btn-ble"
                onClick={onRequestHistory}
                title="Request all 24 initial readings from phone"
              >
                <Radio size={16} />
                <span>Request Initial History</span>
              </button>
              <button
                type="button"
                className="btn btn-outline btn-ble text-danger"
                onClick={onDisconnect}
              >
                <BluetoothOff size={16} />
                <span>Disconnect</span>
              </button>
            </>
          )}

          <button
            type="button"
            className="btn btn-subtle btn-ble"
            onClick={onClearHistory}
            title="Clear all received readings"
          >
            <Trash2 size={15} />
            <span>Clear Received</span>
          </button>
        </div>
      </div>

      {/* Connection / Device / Protocol Information */}
      <div className="ble-details-grid">
        <div className="ble-detail-box">
          <span className="detail-label">Connected Device</span>
          <div className="detail-value-row">
            <Smartphone size={16} className="text-muted" />
            <span className="detail-value">{bleStatus.deviceName || (isConnected ? 'GlucoseTransmitter' : 'None')}</span>
          </div>
        </div>

        <div className="ble-detail-box">
          <span className="detail-label">Latest BLE Reading</span>
          <div className="detail-value-row">
            <Activity size={16} className="text-teal" />
            <span className="detail-value highlight-value">
              {latestReading ? `${latestReading.glucose} ${latestReading.unit || 'mg/dL'}` : '--'}
            </span>
            {latestReading && (
              <span className={`badge-source ${latestReading.source === 'manual' ? 'source-manual' : 'source-sim'}`}>
                {latestReading.source}
              </span>
            )}
          </div>
        </div>

        <div className="ble-detail-box">
          <span className="detail-label">Readings Streamed</span>
          <div className="detail-value-row">
            <CheckCircle size={16} className="text-success" />
            <span className="detail-value">{receivedCount} {receivedCount === 24 ? '(Full 24-Window)' : ''}</span>
          </div>
        </div>

        <div className="ble-detail-box">
          <span className="detail-label">Last Transmission Time</span>
          <div className="detail-value-row">
            <Clock size={16} className="text-muted" />
            <span className="detail-value text-small">
              {latestReading?.timestamp ? new Date(latestReading.timestamp).toLocaleTimeString() : '--'}
            </span>
          </div>
        </div>
      </div>

      {/* Transfer Progress Bar if history is transferring */}
      {transferProgress && (
        <div className="ble-progress-banner">
          <div className="progress-info-row">
            <span>Synchronizing initial 24-point history: {transferProgress.received} / {transferProgress.total} packets</span>
            <span>{Math.round((transferProgress.received / transferProgress.total) * 100)}%</span>
          </div>
          <div className="progress-track">
            <div 
              className="progress-fill" 
              style={{ width: `${(transferProgress.received / transferProgress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Error / Warning Notice */}
      {bleStatus.error && (
        <div className="ble-error-banner">
          <AlertCircle size={16} />
          <span>{bleStatus.error}</span>
        </div>
      )}
    </div>
  );
}
