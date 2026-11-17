import React, { useState } from 'react';
import { Terminal, ChevronDown, ChevronRight, Layers, AlertCircle, CheckCircle2, Shield } from 'lucide-react';

export default function RequestInspector({ requestPayload, predictionResult, isDev, onToggleDev }) {
  const [isOpen, setIsOpen] = useState(true);
  const [activeTab, setActiveTab] = useState('summary'); // 'summary' | 'payload' | 'mapping' | 'channels'

  if (!isDev) {
    return (
      <div className="dev-toggle-container" style={{ margin: '12px 0', textAlign: 'right' }}>
        <button
          type="button"
          className="btn-sm btn-subtle text-xs"
          onClick={onToggleDev}
          title="Enable Developer Request Inspector"
          style={{ fontSize: '0.75rem', opacity: 0.7 }}
        >
          <Terminal size={12} style={{ marginRight: 4 }} />
          Enable Dev Inspector
        </button>
      </div>
    );
  }

  const inspector = predictionResult?.inspector || {};
  const channelSums = inspector.channel_sums || {};
  const slotMapping = inspector.event_to_slot_mapping || [];
  const rejectedEvents = inspector.rejected_events || [];

  return (
    <div className="card request-inspector-card" style={{ marginTop: '1.5rem', border: '1px solid #0284c7', background: '#0f172a', color: '#f8fafc' }}>
      <div 
        className="card-header" 
        style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #1e293b' }}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Terminal size={18} color="#38bdf8" />
          <strong style={{ fontSize: '0.95rem', color: '#e2e8f0' }}>Developer Request Inspector</strong>
          <span style={{ fontSize: '0.75rem', background: '#0369a1', color: '#e0f2fe', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
            DEV MODE
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            type="button"
            className="btn-xs btn-subtle text-muted"
            onClick={(e) => { e.stopPropagation(); onToggleDev(); }}
            style={{ fontSize: '0.75rem', color: '#94a3b8' }}
          >
            Hide Inspector
          </button>
          {isOpen ? <ChevronDown size={18} color="#94a3b8" /> : <ChevronRight size={18} color="#94a3b8" />}
        </div>
      </div>

      {isOpen && (
        <div className="card-body" style={{ padding: '16px' }}>
          {/* Sub-nav tabs */}
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #334155', paddingBottom: '10px', marginBottom: '14px' }}>
            <button
              type="button"
              className={`btn-tab ${activeTab === 'summary' ? 'active' : ''}`}
              onClick={() => setActiveTab('summary')}
              style={{
                background: activeTab === 'summary' ? '#1e293b' : 'transparent',
                color: activeTab === 'summary' ? '#38bdf8' : '#94a3b8',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                fontWeight: activeTab === 'summary' ? 600 : 400
              }}
            >
              Summary & Mode
            </button>
            <button
              type="button"
              className={`btn-tab ${activeTab === 'channels' ? 'active' : ''}`}
              onClick={() => setActiveTab('channels')}
              style={{
                background: activeTab === 'channels' ? '#1e293b' : 'transparent',
                color: activeTab === 'channels' ? '#38bdf8' : '#94a3b8',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                fontWeight: activeTab === 'channels' ? 600 : 400
              }}
            >
              Channels 3–8 Sums
            </button>
            <button
              type="button"
              className={`btn-tab ${activeTab === 'mapping' ? 'active' : ''}`}
              onClick={() => setActiveTab('mapping')}
              style={{
                background: activeTab === 'mapping' ? '#1e293b' : 'transparent',
                color: activeTab === 'mapping' ? '#38bdf8' : '#94a3b8',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                fontWeight: activeTab === 'mapping' ? 600 : 400
              }}
            >
              Event Mapping ({slotMapping.length})
            </button>
            <button
              type="button"
              className={`btn-tab ${activeTab === 'payload' ? 'active' : ''}`}
              onClick={() => setActiveTab('payload')}
              style={{
                background: activeTab === 'payload' ? '#1e293b' : 'transparent',
                color: activeTab === 'payload' ? '#38bdf8' : '#94a3b8',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                fontWeight: activeTab === 'payload' ? 600 : 400
              }}
            >
              Exact Sent JSON
            </button>
          </div>

          {/* Tab 1: Summary & Mode */}
          {activeTab === 'summary' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
              <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block' }}>Backend Response Mode</span>
                <strong style={{ fontSize: '1rem', color: predictionResult?.mode === 'multimodal' ? '#34d399' : '#38bdf8' }}>
                  {predictionResult?.mode || 'No run yet'}
                </strong>
              </div>
              <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block' }}>Inputs Used</span>
                <strong style={{ fontSize: '1rem', color: '#f1f5f9' }}>
                  {predictionResult?.inputs_used?.join(', ') || 'none'}
                </strong>
              </div>
              <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block' }}>Rejected Events</span>
                <strong style={{ fontSize: '1rem', color: rejectedEvents.length > 0 ? '#f87171' : '#34d399' }}>
                  {rejectedEvents.length}
                </strong>
              </div>
              <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block' }}>Model ID</span>
                <strong style={{ fontSize: '0.9rem', color: '#cbd5e1' }}>
                  {predictionResult?.model_id || requestPayload?.modelId || 'e1_gpformer'}
                </strong>
              </div>
            </div>
          )}

          {/* Tab 2: Channels 3-8 Sums */}
          {activeTab === 'channels' && (
            <div>
              <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '10px' }}>
                Sum of normalized feature values and availability masks across all 24 slots (shape 1, 24, 9):
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Ch 3: Bolus (scaled sum)</div>
                  <strong style={{ fontSize: '1.1rem', color: '#38bdf8', fontFamily: 'monospace' }}>
                    {channelSums.channel_3_bolus_scaled_sum ?? 0}
                  </strong>
                </div>
                <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Ch 4: Basal (scaled sum)</div>
                  <strong style={{ fontSize: '1.1rem', color: '#38bdf8', fontFamily: 'monospace' }}>
                    {channelSums.channel_4_basal_scaled_sum ?? 0}
                  </strong>
                </div>
                <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Ch 5: Carbs (scaled sum)</div>
                  <strong style={{ fontSize: '1.1rem', color: '#38bdf8', fontFamily: 'monospace' }}>
                    {channelSums.channel_5_carbs_scaled_sum ?? 0}
                  </strong>
                </div>
                <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Ch 6: Mask Bolus sum</div>
                  <strong style={{ fontSize: '1.1rem', color: '#a78bfa', fontFamily: 'monospace' }}>
                    {channelSums.channel_6_mask_bolus_sum ?? 0}
                  </strong>
                </div>
                <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Ch 7: Mask Basal sum</div>
                  <strong style={{ fontSize: '1.1rem', color: '#a78bfa', fontFamily: 'monospace' }}>
                    {channelSums.channel_7_mask_basal_sum ?? 0}
                  </strong>
                </div>
                <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Ch 8: Mask Carbs sum</div>
                  <strong style={{ fontSize: '1.1rem', color: '#a78bfa', fontFamily: 'monospace' }}>
                    {channelSums.channel_8_mask_carbs_sum ?? 0}
                  </strong>
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Event Mapping */}
          {activeTab === 'mapping' && (
            <div>
              {slotMapping.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: '#94a3b8', fontStyle: 'italic' }}>
                  No discrete events entered in this forecast run.
                </p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#1e293b', textAlign: 'left', color: '#cbd5e1' }}>
                        <th style={{ padding: '8px' }}>Type</th>
                        <th style={{ padding: '8px' }}>Event Time</th>
                        <th style={{ padding: '8px' }}>Assigned Slot</th>
                        <th style={{ padding: '8px' }}>Slot Time</th>
                        <th style={{ padding: '8px' }}>Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {slotMapping.map((item, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #334155' }}>
                          <td style={{ padding: '8px', textTransform: 'capitalize', color: item.type === 'bolus' ? '#38bdf8' : '#fbbf24' }}>
                            {item.type}
                          </td>
                          <td style={{ padding: '8px', fontFamily: 'monospace' }}>{item.event_time}</td>
                          <td style={{ padding: '8px', fontWeight: 600 }}>Slot #{item.slot_index + 1}</td>
                          <td style={{ padding: '8px', fontFamily: 'monospace' }}>{item.slot_time}</td>
                          <td style={{ padding: '8px', fontWeight: 600 }}>{item.amount} {item.unit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Tab 4: Exact Sent JSON */}
          {activeTab === 'payload' && (
            <div style={{ position: 'relative' }}>
              <pre
                style={{
                  background: '#090d16',
                  padding: '12px',
                  borderRadius: '6px',
                  fontSize: '0.78rem',
                  overflowX: 'auto',
                  maxHeight: '260px',
                  color: '#7dd3fc',
                  fontFamily: 'Consolas, monospace'
                }}
              >
                {requestPayload ? JSON.stringify(requestPayload, null, 2) : '// No request sent yet'}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
