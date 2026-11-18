import React, { useState, useRef, useEffect } from 'react';
import { sendChatMessage } from '../services/api';
import './Chatbot.css';

const QUICK_SUGGESTIONS = [
  { icon: '🚨', label: 'Blood sugar below 70 mg/dL', text: 'My blood glucose is below 70 mg/dL. What should I do right now?' },
  { icon: '🍽️', label: 'Low GI meal ideas', text: 'What are healthy, low glycemic index meal ideas for dinner?' },
  { icon: '🏃', label: 'Exercise & blood sugar', text: 'How does exercise affect glucose levels and how should I prepare?' },
  { icon: '🍞', label: 'Carb counting tips', text: 'Can you give me practical tips for estimating carbs in a mixed meal?' },
  { icon: '📈', label: 'Explain my CGM trend', text: 'Can you explain what my current glucose reading and forecast trend mean for my daily routine?' }
];

export default function Chatbot({ latestReading = null, predictionResult = null }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: "Hello! I'm **GlucoGuide**, your AI diabetes decision-support educator powered by Gemini.\n\nI can help answer questions about nutrition, carbohydrate estimation, managing glucose fluctuations, and understanding CGM trends.\n\n*Note: I provide educational guidance, not formal medical prescriptions. In emergencies, follow the Rule of 15 and consult your healthcare provider.*",
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      inputRef.current?.focus();
    }
  }, [isOpen, messages]);

  // Build telemetry context from live UI state
  const buildGlucoseContext = () => {
    const context = {};
    if (latestReading != null) {
      const val = parseFloat(latestReading);
      if (!isNaN(val)) context.current_glucose = val;
    }
    if (predictionResult) {
      if (predictionResult.clinical_alert?.trend) {
        context.trend = predictionResult.clinical_alert.trend;
      }
      if (predictionResult.clinical_alert?.status) {
        context.risk_class = predictionResult.clinical_alert.status;
      }
      // Look for 30m horizon forecast
      const f30 = predictionResult.forecast?.find(f => f.horizon_minutes === 30);
      if (f30) {
        context.predicted_30m = f30.glucose_median ?? f30.median;
        if (f30.risk_probabilities) {
          context.hypo_probability = f30.risk_probabilities.hypo;
          context.hyper_probability = f30.risk_probabilities.hyper;
        }
      }
    }
    return Object.keys(context).length > 0 ? context : null;
  };

  const handleSend = async (textToSend = null) => {
    const text = (textToSend || inputValue).trim();
    if (!text || isLoading) return;

    setError(null);
    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    if (!textToSend) setInputValue('');
    setIsLoading(true);

    try {
      const historyPayload = messages
        .filter(m => m.id !== 'welcome')
        .map(m => ({ role: m.role, content: m.content }));

      const glucoseContext = buildGlucoseContext();

      const response = await sendChatMessage({
        message: text,
        history: historyPayload,
        glucoseContext
      });

      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.reply,
        model: response.model,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      setError(err.message || 'Failed to get response from GlucoGuide AI.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const currentCtx = buildGlucoseContext();

  return (
    <div className="glucoguide-container">
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          className="glucoguide-launcher"
          onClick={() => setIsOpen(true)}
          aria-label="Open GlucoGuide AI Chatbot"
        >
          <span className="glucoguide-launcher-icon">💬</span>
          <span className="glucoguide-launcher-label">Ask GlucoGuide</span>
          {currentCtx?.current_glucose && (
            <span className="glucoguide-launcher-badge">
              {currentCtx.current_glucose} mg/dL
            </span>
          )}
        </button>
      )}

      {/* Floating Chat Window */}
      {isOpen && (
        <div className="glucoguide-window" role="dialog" aria-labelledby="chatbot-title">
          {/* Header */}
          <div className="glucoguide-header">
            <div className="glucoguide-header-info">
              <div className="glucoguide-avatar">🤖</div>
              <div>
                <h3 id="chatbot-title" className="glucoguide-title">GlucoGuide AI</h3>
                <span className="glucoguide-subtitle">
                  <span className="online-indicator"></span> Gemini Patient Decision Support
                </span>
              </div>
            </div>
            <div className="glucoguide-header-actions">
              <button
                className="glucoguide-icon-btn"
                onClick={() => setIsOpen(false)}
                title="Minimize chat"
                aria-label="Minimize chat"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Telemetry Status Strip */}
          {currentCtx && (
            <div className="glucoguide-telemetry-bar">
              <span className="telemetry-badge">
                📊 CGM: <strong>{currentCtx.current_glucose ?? '--'} mg/dL</strong>
              </span>
              {currentCtx.predicted_30m && (
                <span className="telemetry-badge">
                  🔮 +30m: <strong>{Math.round(currentCtx.predicted_30m)} mg/dL</strong>
                </span>
              )}
              {currentCtx.trend && (
                <span className="telemetry-badge">
                  📈 {currentCtx.trend}
                </span>
              )}
            </div>
          )}

          {/* Quick Suggestions Chips */}
          <div className="glucoguide-suggestions-strip">
            {QUICK_SUGGESTIONS.map((sug, idx) => (
              <button
                key={idx}
                className="glucoguide-chip"
                onClick={() => handleSend(sug.text)}
                disabled={isLoading}
              >
                <span>{sug.icon}</span> {sug.label}
              </button>
            ))}
          </div>

          {/* Message List */}
          <div className="glucoguide-messages">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`glucoguide-message ${msg.role === 'user' ? 'message-user' : 'message-assistant'}`}
              >
                <div className="message-bubble">
                  <div className="message-text" style={{ whiteSpace: 'pre-wrap' }}>
                    {msg.content}
                  </div>
                  <div className="message-meta">
                    <span className="message-time">{msg.timestamp}</span>
                    {msg.model && <span className="message-model">{msg.model}</span>}
                  </div>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="glucoguide-message message-assistant">
                <div className="message-bubble loading-bubble">
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                  <span style={{ marginLeft: '8px', fontSize: '11px', color: '#94a3b8' }}>
                    Consulting GlucoGuide...
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div className="glucoguide-error-banner">
                ⚠️ {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="glucoguide-input-area">
            <textarea
              ref={inputRef}
              className="glucoguide-input"
              placeholder="Ask about diet, low glucose, trends, carbs..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={isLoading}
            />
            <button
              className="glucoguide-send-btn"
              onClick={() => handleSend()}
              disabled={isLoading || !inputValue.trim()}
              aria-label="Send message"
            >
              ➤
            </button>
          </div>

          {/* Medical Disclaimer */}
          <div className="glucoguide-disclaimer">
            Decision support only. Not medical advice. In emergencies, call your doctor or 911.
          </div>
        </div>
      )}
    </div>
  );
}
