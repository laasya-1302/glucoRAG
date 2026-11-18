import React from 'react';
import { Clock, Layers, HeartPulse, Smartphone, ArrowRight } from 'lucide-react';

export default function HeroSection({ onTryPrediction, onLearnMore }) {
  return (
    <section className="gp-hero-wrapper">
      {/* Top Announcement Ribbon */}
      <div className="gp-announcement-bar">
        <span>
          <strong>GPFormer</strong> &bull; AI-powered multi-horizon glucose forecasting for personalized diabetes care.
        </span>
      </div>

      <div className="gp-hero-card-container">
        {/* Main Hero Card */}
        <div className="gp-hero-card">
          <div className="gp-hero-content">
            <h1 className="gp-hero-title">
              Predict Your Glucose Ahead with GPFormer
            </h1>
            <p className="gp-hero-subtitle">
              Personalized &bull; Multi-Horizon &bull; Real-Time
            </p>

            <div className="gp-hero-buttons">
              <button
                type="button"
                className="gp-btn-outline"
                onClick={onLearnMore}
              >
                Learn More
              </button>
              <button
                type="button"
                className="gp-btn-orange"
                onClick={onTryPrediction}
              >
                Try Prediction <ArrowRight size={16} className="inline-arrow" />
              </button>
            </div>
          </div>

          <div className="gp-hero-graphic" aria-hidden="true">
            {/* High-fidelity Vector CGM Wearable Device & Glucose Wave */}
            <svg viewBox="0 0 340 240" fill="none" xmlns="http://www.w3.org/2000/svg" className="cgm-vector-illustration">
              <defs>
                <linearGradient id="waveGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#EA580C" />
                  <stop offset="50%" stopColor="#F97316" />
                  <stop offset="100%" stopColor="#EA580C" />
                </linearGradient>
                <linearGradient id="meterGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#FFFFFF" />
                  <stop offset="100%" stopColor="#F0FDF4" />
                </linearGradient>
                <filter id="softGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#0D766E" floodOpacity="0.12" />
                </filter>
              </defs>

              {/* Glucose Forecast Trajectory Waveform */}
              <path
                d="M 10 170 Q 75 120, 140 160 T 260 120 Q 300 130, 335 155"
                stroke="url(#waveGrad)"
                strokeWidth="3.5"
                strokeLinecap="round"
                fill="none"
              />

              {/* Sunbeam Spark Rays */}
              <line x1="248" y1="84" x2="252" y2="76" stroke="#F59E0B" strokeWidth="2.5" strokeLinecap="round" />
              <line x1="258" y1="92" x2="267" y2="88" stroke="#F59E0B" strokeWidth="2.5" strokeLinecap="round" />
              <line x1="262" y1="105" x2="271" y2="107" stroke="#F59E0B" strokeWidth="2.5" strokeLinecap="round" />

              {/* CGM Device Meter Body */}
              <g filter="url(#softGlow)">
                <rect
                  x="180"
                  y="92"
                  width="72"
                  height="94"
                  rx="18"
                  fill="url(#meterGrad)"
                  stroke="#0E5A52"
                  strokeWidth="3"
                />
                {/* Meter Screen */}
                <rect
                  x="191"
                  y="104"
                  width="50"
                  height="50"
                  rx="10"
                  fill="#FFFFFF"
                  stroke="#115E59"
                  strokeWidth="1.8"
                />
                {/* Droplet on Screen */}
                <path
                  d="M 216 116 C 216 116, 208 126, 208 132 C 208 136.5, 211.5 140, 216 140 C 220.5 140, 224 136.5, 224 132 C 224 126, 216 116, 216 116 Z"
                  stroke="#0E5A52"
                  strokeWidth="2"
                  fill="none"
                />
                {/* Sensor Notch / Port */}
                <path
                  d="M 210 186 L 210 175 Q 210 170, 216 170 Q 222 170, 222 175 L 222 186"
                  stroke="#0E5A52"
                  strokeWidth="2.5"
                  fill="none"
                  strokeLinecap="round"
                />
              </g>
            </svg>
          </div>
        </div>

        {/* 4 Feature Highlights Horizontal Bar */}
        <div className="gp-feature-bar">
          <div className="gp-feature-col">
            <div className="gp-feature-icon-circle">
              <Clock size={20} className="gp-icon-teal" />
            </div>
            <div className="gp-feature-text">
              <strong className="gp-feature-title">Multi-Horizon Forecast</strong>
              <span className="gp-feature-meta">(30–120 min)</span>
            </div>
          </div>

          <div className="gp-feature-col">
            <div className="gp-feature-icon-circle">
              <Layers size={20} className="gp-icon-teal" />
            </div>
            <div className="gp-feature-text">
              <strong className="gp-feature-title">Personalized Prediction</strong>
              <span className="gp-feature-meta">(T1D / T2D)</span>
            </div>
          </div>

          <div className="gp-feature-col">
            <div className="gp-feature-icon-circle">
              <HeartPulse size={20} className="gp-icon-teal" />
            </div>
            <div className="gp-feature-text">
              <strong className="gp-feature-title">Risk Alerts</strong>
              <span className="gp-feature-meta">(Hypo / Hyper)</span>
            </div>
          </div>

          <div className="gp-feature-col">
            <div className="gp-feature-icon-circle">
              <Smartphone size={20} className="gp-icon-teal" />
            </div>
            <div className="gp-feature-text">
              <strong className="gp-feature-title">Real-Time & Wearable Ready</strong>
              <span className="gp-feature-meta">BLE Continuous Sync</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
