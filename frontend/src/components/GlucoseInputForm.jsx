import React, { useState, useRef } from 'react';
import {
  Clock, RotateCcw, Play, Sparkles, AlertTriangle,
  PlusCircle, Syringe, Utensils, Info, X, CheckCircle, ArrowRight, ArrowLeft
} from 'lucide-react';

const DEMO_GLUCOSE = [
  110, 98, 99, 89, 96, 92, 87, 85, 84, 81, 82, 80,
  75, 73, 74, 72, 70, 68, 67, 66, 64, 62, 65, 60
];

export default function GlucoseInputForm({
  readings,
  setReadings,
  latestTimestamp,
  setLatestTimestamp,
  onSubmit,
  isLoading,
  formError,
  setFormError,
  // Lifting state up / exporting for App.jsx payload construction
  isInsulinOn,
  setIsInsulinOn,
  isCarbsOn,
  setIsCarbsOn,
  bolusSlots,
  setBolusSlots,
  carbSlots,
  setCarbSlots,
  basalRate,
  setBasalRate,
  basalStartTime,
  setBasalStartTime,
  isDemoActive,
  setIsDemoActive
}) {
  const [selectedPreset, setSelectedPreset] = useState('');
  const [showAddEventModal, setShowAddEventModal] = useState(false);
  const [modalError, setModalError] = useState(null);
  const [lastAssignedNotice, setLastAssignedNotice] = useState(null);
  const [newEvent, setNewEvent] = useState({ type: 'bolus', time: '', bolus: '', carbs: '', amount: '' });
  const [highlightedSlot, setHighlightedSlot] = useState(null);
  const gridContainerRef = useRef(null);

  const scrollToSlot = (slotIndex) => {
    if (gridContainerRef.current) {
      const slotWidth = 75; // Approx slot column width
      gridContainerRef.current.scrollTo({
        left: Math.max(0, slotIndex * slotWidth - 120),
        behavior: 'smooth'
      });
      setHighlightedSlot(slotIndex);
      setTimeout(() => setHighlightedSlot(null), 4000);
    }
  };

  // Calculate slot timestamps based on latestTimestamp
  const getSlotTimestamps = () => {
    const baseDate = latestTimestamp ? new Date(latestTimestamp) : new Date();
    const times = [];
    for (let i = 0; i < 24; i++) {
      const d = new Date(baseDate.getTime() - (23 - i) * 15 * 60000);
      times.push(d);
    }
    return times;
  };

  const slotTimes = getSlotTimestamps();

  // Helper to format ISO datetime for local input
  const formatLocalDt = (d) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  // Turn on insulin toggle prefill
  const handleToggleInsulin = (checked) => {
    setIsInsulinOn(checked);
    if (checked && (!basalRate || basalRate === '')) {
      setBasalRate('0.9');
      const sixHoursAgo = new Date(new Date(latestTimestamp || Date.now()).getTime() - 6 * 3600000);
      setBasalStartTime(formatLocalDt(sixHoursAgo));
    }
  };

  // Turn on carbs toggle
  const handleToggleCarbs = (checked) => {
    setIsCarbsOn(checked);
  };

  const handleReadingChange = (index, val) => {
    const updated = [...readings];
    updated[index] = val;
    setReadings(updated);
    if (formError) setFormError(null);
  };

  const handleBolusChange = (index, val) => {
    const updated = [...bolusSlots];
    updated[index] = val;
    setBolusSlots(updated);
    if (formError) setFormError(null);
  };

  const handleCarbChange = (index, val) => {
    const updated = [...carbSlots];
    updated[index] = val;
    setCarbSlots(updated);
    if (formError) setFormError(null);
  };

  // Live slot preview helper
  const getSlotPreview = (timeStr) => {
    if (!timeStr) return null;
    const evTime = new Date(timeStr);
    if (isNaN(evTime.getTime())) return null;
    for (let i = 0; i < 24; i++) {
      if (slotTimes[i] >= evTime) {
        const mins = -(23 - i) * 15;
        const label = mins === 0 ? "Now (0m)" : `${mins}m`;
        const timeFormatted = slotTimes[i].toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return { slotIndex: i, slotNumber: i + 1, label, timeFormatted };
      }
    }
    return { slotIndex: 23, slotNumber: 24, label: "Now (0m)", timeFormatted: slotTimes[23].toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
  };

  // Add arbitrary time event and map to first slot with t_slot >= t_event
  const handleAddArbitraryEvent = (e) => {
    e.preventDefault();
    setModalError(null);
    if (!newEvent.time) {
      setModalError("Please enter an event timestamp.");
      return;
    }

    const bolusVal = newEvent.bolus !== '' && !isNaN(parseFloat(newEvent.bolus)) 
      ? parseFloat(newEvent.bolus) 
      : (newEvent.type === 'bolus' && newEvent.amount !== '' && !isNaN(parseFloat(newEvent.amount)) ? parseFloat(newEvent.amount) : null);
    
    const carbsVal = newEvent.carbs !== '' && !isNaN(parseFloat(newEvent.carbs)) 
      ? parseFloat(newEvent.carbs) 
      : (newEvent.type === 'carbs' && newEvent.amount !== '' && !isNaN(parseFloat(newEvent.amount)) ? parseFloat(newEvent.amount) : null);

    if (bolusVal === null && carbsVal === null) {
      setModalError("Please enter an amount for Bolus (Units) or Carbs (Grams).");
      return;
    }

    const eventTime = new Date(newEvent.time);
    const latestTime = new Date(latestTimestamp);
    const earliestTime = new Date(slotTimes[0].getTime() - 15 * 60000);

    if (eventTime > latestTime) {
      setModalError("Event time cannot be after the latest reading timestamp.");
      return;
    }
    if (eventTime < earliestTime) {
      setModalError("Event time cannot be earlier than the 6-hour input window boundary.");
      return;
    }

    if (bolusVal !== null) {
      if (isNaN(bolusVal) || bolusVal < 0) {
        setModalError("Please enter a non-negative bolus amount.");
        return;
      }
      if (bolusVal > 40) {
        setModalError("Bolus amount cannot exceed 40 U.");
        return;
      }
    }

    if (carbsVal !== null) {
      if (isNaN(carbsVal) || carbsVal < 0) {
        setModalError("Please enter a non-negative carbohydrate amount.");
        return;
      }
      if (carbsVal > 370) {
        setModalError("Carbohydrate amount cannot exceed 370 g.");
        return;
      }
    }

    // Find first slot where slot_time >= event_time (e.g. 07:30 -> 07:39 / Slot #12)
    let targetSlot = 23;
    for (let i = 0; i < 24; i++) {
      if (slotTimes[i] >= eventTime) {
        targetSlot = i;
        break;
      }
    }

    if (bolusVal !== null) {
      const current = parseFloat(bolusSlots[targetSlot]) || 0;
      const total = current + bolusVal;
      handleBolusChange(targetSlot, total.toFixed(1));
    }
    if (carbsVal !== null) {
      const current = parseFloat(carbSlots[targetSlot]) || 0;
      const total = current + carbsVal;
      handleCarbChange(targetSlot, total.toFixed(0));
    }

    const assignedTimeStr = slotTimes[targetSlot].toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setLastAssignedNotice(`Successfully assigned to Slot #${targetSlot + 1} (${assignedTimeStr})!`);
    scrollToSlot(targetSlot);
    setTimeout(() => setLastAssignedNotice(null), 8000);

    setShowAddEventModal(false);
    setNewEvent({ type: 'bolus', time: '', bolus: '', carbs: '', amount: '' });
    setModalError(null);
  };

  // Load standard Demo Scenarios A - G
  const handleLoadDemoScenario = (scenarioKey) => {
    setSelectedPreset(scenarioKey);
    setIsDemoActive(true);

    // Set latest timestamp to 12:30 today
    const now = new Date();
    const demoLatest = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 30, 0);
    const demoLatestStr = formatLocalDt(demoLatest);
    setLatestTimestamp(demoLatestStr);

    // Fill standard 24 demo glucose readings
    setReadings(DEMO_GLUCOSE.map(String));

    // Reset slot arrays
    const newBolus = Array(24).fill('');
    const newCarbs = Array(24).fill('');

    const sixHoursAgoStr = formatLocalDt(new Date(demoLatest.getTime() - 6 * 3600000));

    switch (scenarioKey) {
      case 'A': // Glucose only (CGM-only)
        setIsInsulinOn(false);
        setIsCarbsOn(false);
        setBasalRate('');
        setBasalStartTime('');
        break;

      case 'B': // Multimodal, no insulin, no carbs
        setIsInsulinOn(true);
        setIsCarbsOn(true);
        setBasalRate('0.9');
        setBasalStartTime(sixHoursAgoStr);
        break;

      case 'C': // Carbs 30 g, insulin unavailable
        setIsInsulinOn(false);
        setIsCarbsOn(true);
        newCarbs[23] = '30';
        setBasalRate('');
        break;

      case 'D': // Carbs 60 g, insulin unavailable
        setIsInsulinOn(false);
        setIsCarbsOn(true);
        newCarbs[23] = '60';
        setBasalRate('');
        break;

      case 'E': // Carbs 60 g, insulin available none given
        setIsInsulinOn(true);
        setIsCarbsOn(true);
        setBasalRate('0.9');
        setBasalStartTime(sixHoursAgoStr);
        newCarbs[23] = '60';
        break;

      case 'F': // Carbs 60 g + bolus 4 U
        setIsInsulinOn(true);
        setIsCarbsOn(true);
        setBasalRate('0.9');
        setBasalStartTime(sixHoursAgoStr);
        newBolus[23] = '4.0';
        newCarbs[23] = '60';
        break;

      case 'G': // Bolus 4 U, no carbs
        setIsInsulinOn(true);
        setIsCarbsOn(true);
        setBasalRate('0.9');
        setBasalStartTime(sixHoursAgoStr);
        newBolus[23] = '4.0';
        break;

      default:
        break;
    }

    setBolusSlots(newBolus);
    setCarbSlots(newCarbs);
    if (formError) setFormError(null);
  };

  const handleReset = () => {
    setReadings(Array(24).fill(''));
    setBolusSlots(Array(24).fill(''));
    setCarbSlots(Array(24).fill(''));
    setBasalRate('');
    setBasalStartTime('');
    setIsInsulinOn(false);
    setIsCarbsOn(false);
    setIsDemoActive(false);
    setSelectedPreset('');
    if (formError) setFormError(null);
  };

  // Summary statistics
  const validNumbers = readings
    .map(r => parseFloat(r))
    .filter(n => !isNaN(n) && isFinite(n));
  const countValid = validNumbers.length;
  const meanVal = countValid > 0 ? (validNumbers.reduce((a, b) => a + b, 0) / countValid).toFixed(1) : '--';
  const minVal = countValid > 0 ? Math.min(...validNumbers).toFixed(1) : '--';
  const maxVal = countValid > 0 ? Math.max(...validNumbers).toFixed(1) : '--';

  // Warnings checks
  const hasCarbsWithoutInsulin = isCarbsOn && !isInsulinOn && carbSlots.some(c => parseFloat(c) > 0);
  const highBolusWarning = bolusSlots.some(b => parseFloat(b) > 17);
  const highCarbWarning = carbSlots.some(c => parseFloat(c) > 120);

  return (
    <div className="card input-card">
      {/* Prominent Demo Data Banner */}
      {isDemoActive && (
        <div className="demo-data-banner" role="status">
          <div className="demo-banner-content">
            <span className="demo-tag">DEMO DATA</span>
            <strong>DEMO DATA - not a real person</strong>
            <span className="demo-hint">Editing fields keeps this banner until "Clear Grid". Click Predict to test.</span>
          </div>
          <button type="button" className="btn-sm btn-subtle text-amber" onClick={handleReset}>
            Clear
          </button>
        </div>
      )}

      <div className="card-header">
        <div>
          <h2 className="card-title">Continuous Glucose & Multimodal Event Input</h2>
          <p className="card-description">
            Provide 24 chronological glucose readings with aligned insulin and carbohydrate rows.
          </p>
        </div>

        {/* Demo Scenarios Selector */}
        <div className="demo-scenario-controls">
          <div className="demo-selector-group">
            <label htmlFor="demo-scenario-select" className="demo-label">
              <Sparkles size={14} className="text-amber" />
              <span>Load demo scenario:</span>
            </label>
            <select
              id="demo-scenario-select"
              value={selectedPreset}
              onChange={(e) => handleLoadDemoScenario(e.target.value)}
              className="demo-dropdown"
              aria-label="Load demo scenario"
            >
              <option value="">Select acceptance preset...</option>
              <option value="A">A: Glucose only (CGM-only)</option>
              <option value="B">B: Multimodal, no insulin, no carbs</option>
              <option value="C">C: Carbs 30 g, insulin unavailable</option>
              <option value="D">D: Carbs 60 g, insulin unavailable</option>
              <option value="E">E: Carbs 60 g, insulin available none</option>
              <option value="F">F: Carbs 60 g + bolus 4 U</option>
              <option value="G">G: Bolus 4 U, no carbs</option>
            </select>
          </div>
          <p className="demo-disclaimer-note">
            Demo scenarios are for testing the app. They are not advice, and the model's response to insulin and carbs is not clinically validated.
          </p>
        </div>
      </div>

      {/* Multimodal Input Toggles */}
      <div className="multimodal-toggles-bar">
        <label className="toggle-chip">
          <input
            type="checkbox"
            checked={isInsulinOn}
            onChange={(e) => handleToggleInsulin(e.target.checked)}
          />
          <Syringe size={15} className="text-teal" />
          <span>I'm entering insulin data</span>
        </label>

        <label className="toggle-chip">
          <input
            type="checkbox"
            checked={isCarbsOn}
            onChange={(e) => handleToggleCarbs(e.target.checked)}
          />
          <Utensils size={15} className="text-emerald" />
          <span>I'm entering carb data</span>
        </label>

        <div className="event-action-buttons">
          {isInsulinOn && (
            <button
              type="button"
              className="btn-sm btn-subtle"
              onClick={() => {
                setNewEvent({ type: 'bolus', time: latestTimestamp || '', bolus: '', carbs: '', amount: '' });
                setModalError(null);
                setShowAddEventModal(true);
              }}
            >
              <PlusCircle size={14} />
              <span>+ Add Bolus Event</span>
            </button>
          )}

          {isCarbsOn && (
            <button
              type="button"
              className="btn-sm btn-subtle"
              onClick={() => {
                setNewEvent({ type: 'carbs', time: latestTimestamp || '', bolus: '', carbs: '', amount: '' });
                setModalError(null);
                setShowAddEventModal(true);
              }}
            >
              <PlusCircle size={14} />
              <span>+ Add Carb Event</span>
            </button>
          )}
        </div>
      </div>

      {/* Basal Rate Entry (Active when insulin toggle is ON) */}
      {isInsulinOn && (
        <div className="basal-entry-card">
          <div className="basal-row">
            <div className="basal-field">
              <label>Basal Rate (U/h):</label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="5"
                value={basalRate}
                onChange={(e) => setBasalRate(e.target.value)}
                className="input-sm"
                placeholder="0.9"
              />
              <span className="unit-tag">U/h</span>
            </div>

            <div className="basal-field">
              <label>Started at:</label>
              <input
                type="datetime-local"
                value={basalStartTime}
                onChange={(e) => setBasalStartTime(e.target.value)}
                className="input-sm input-datetime-sm"
              />
            </div>
            <span className="basal-helper-text">
              Typical default (0.9 U/h, started 6h ago) – replace with your pump's rate.
            </span>
          </div>

          <p className="clinical-model-note">
            <Info size={14} className="text-teal" />
            <span>In testing, insulin has little effect on the forecast.</span>
          </p>
        </div>
      )}

      {/* Contextual Warnings */}
      {hasCarbsWithoutInsulin && (
        <div className="alert-banner-warning">
          <AlertTriangle size={15} />
          <span>Carbs without insulin data were rarely seen in training; accuracy is unverified.</span>
        </div>
      )}
      {highBolusWarning && (
        <div className="alert-banner-warning">
          <AlertTriangle size={15} />
          <span>Notice: Bolus dose exceeds 17 U. Ensure dose is entered correctly (max limit: 40 U).</span>
        </div>
      )}
      {highCarbWarning && (
        <div className="alert-banner-warning">
          <AlertTriangle size={15} />
          <span>Notice: Carbohydrate entry exceeds 120 g. Ensure entry is accurate (max limit: 370 g).</span>
        </div>
      )}

      {/* Timestamp and Stats Bar */}
      <div className="timestamp-bar">
        <div className="timestamp-field">
          <label htmlFor="latest-timestamp-input" className="field-label">
            <Clock size={16} className="text-teal" />
            <span>Latest Reading Timestamp (t = 0 min):</span>
          </label>
          <input
            id="latest-timestamp-input"
            type="datetime-local"
            value={latestTimestamp}
            onChange={(e) => setLatestTimestamp(e.target.value)}
            className="input-datetime"
            step="60"
          />
        </div>
        <div className="input-stats">
          <div className="stat-pill">
            <span className="stat-label">Valid Entries:</span>
            <strong className={`stat-num ${countValid === 24 ? 'text-emerald' : 'text-amber'}`}>
              {countValid} / 24
            </strong>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Mean:</span>
            <strong>{meanVal} mg/dL</strong>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Range:</span>
            <strong>{minVal} – {maxVal}</strong>
          </div>
        </div>
      </div>

      {lastAssignedNotice && (
        <div className="alert-banner-warning" style={{ background: '#ecfdf5', borderColor: '#a7f3d0', color: '#047857', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle size={16} />
          <span><strong>Success:</strong> {lastAssignedNotice} Scrolled grid to slot.</span>
        </div>
      )}

      {/* Active Entered Bolus & Carb Events summary */}
      {(() => {
        const events = [];
        for (let i = 0; i < 24; i++) {
          const hasB = isInsulinOn && bolusSlots[i] && !isNaN(parseFloat(bolusSlots[i])) && parseFloat(bolusSlots[i]) > 0;
          const hasC = isCarbsOn && carbSlots[i] && !isNaN(parseFloat(carbSlots[i])) && parseFloat(carbSlots[i]) > 0;
          if (hasB || hasC) {
            events.push({
              slotIndex: i,
              slotNumber: i + 1,
              time: slotTimes[i].toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              label: i === 23 ? 'Now' : `-${(23 - i) * 15}m`,
              bolus: hasB ? `${bolusSlots[i]} U` : null,
              carbs: hasC ? `${carbSlots[i]}g` : null,
            });
          }
        }
        if (events.length === 0) return null;
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', padding: '10px 14px', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '8px', marginBottom: '12px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#166534' }}>
              📌 Assigned Events ({events.length}):
            </span>
            {events.map((ev) => (
              <button
                key={ev.slotIndex}
                type="button"
                onClick={() => scrollToSlot(ev.slotIndex)}
                style={{
                  background: '#ffffff',
                  border: '1px solid #10b981',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '0.8rem',
                  color: '#047857',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                }}
                title="Click to jump and view this slot in the 24-grid"
              >
                <strong>Slot #{ev.slotNumber}</strong> ({ev.time}): {ev.bolus ? `💉 ${ev.bolus}` : ''} {ev.carbs ? `🍞 ${ev.carbs}` : ''}
                <ArrowRight size={13} />
              </button>
            ))}
          </div>
        );
      })()}

      {/* Grid Quick Navigation Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', fontSize: '0.8rem', color: '#64748b' }}>
        <span>Showing 24 time slots (15-min intervals). Use buttons or scrollbar to see all slots:</span>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            type="button"
            onClick={() => scrollToSlot(0)}
            className="btn-sm btn-subtle"
            style={{ padding: '2px 8px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
          >
            <ArrowLeft size={12} />
            <span>Oldest (Slot #1)</span>
          </button>
          <button
            type="button"
            onClick={() => scrollToSlot(23)}
            className="btn-sm btn-subtle"
            style={{ padding: '2px 8px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
          >
            <span>Latest Now (Slot #24)</span>
            <ArrowRight size={12} />
          </button>
        </div>
      </div>

      {/* 24 Aligned Slots Table (Glucose, Bolus, Carbs) */}
      <form onSubmit={onSubmit}>
        <div className="grid-aligned-table-container" ref={gridContainerRef}>
          <div className="grid-aligned-row glucose-row">
            <div className="row-header-label">
              <strong>Glucose</strong>
              <span className="text-muted text-xs">mg/dL</span>
            </div>
            <div className="slots-24-track">
              {readings.map((val, idx) => {
                const minsAgo = (23 - idx) * 15;
                const isNow = idx === 23;
                const num = parseFloat(val);
                const isInvalid = val !== '' && (isNaN(num) || num < 20 || num > 600);
                const isHypo = !isInvalid && !isNaN(num) && num < 70;
                const isHyper = !isInvalid && !isNaN(num) && num > 180;

                let cellClass = "reading-cell";
                if (isNow) cellClass += " cell-now";
                if (isInvalid) cellClass += " cell-invalid";
                else if (isHypo) cellClass += " cell-hypo";
                else if (isHyper) cellClass += " cell-hyper";

                return (
                  <div key={idx} className={cellClass}>
                    <div className="cell-header">
                      <span className="cell-index">#{idx + 1}</span>
                      <span className="cell-time">{isNow ? 'Now' : `-${minsAgo}m`}</span>
                    </div>
                    <input
                      type="number"
                      step="0.1"
                      min="20"
                      max="600"
                      placeholder="mg/dL"
                      value={val}
                      onChange={(e) => handleReadingChange(idx, e.target.value)}
                      className="cell-input"
                      required
                      aria-label={`Glucose reading at ${isNow ? 'current time' : `-${minsAgo} minutes`}`}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Bolus Row (Active when insulin toggle is ON) */}
          {isInsulinOn && (
            <div className="grid-aligned-row bolus-row">
              <div className="row-header-label">
                <strong>Bolus</strong>
                <span className="text-muted text-xs">Units</span>
              </div>
              <div className="slots-24-track">
                {bolusSlots.map((val, idx) => {
                  const num = parseFloat(val);
                  const isWarn = num > 17 && num <= 40;
                  const isErr = num < 0 || num > 40;
                  const isHighlighted = highlightedSlot === idx;
                  return (
                    <div
                      key={idx}
                      className={`reading-cell event-cell ${isErr ? 'cell-invalid' : ''} ${isWarn ? 'cell-warn' : ''}`}
                      style={isHighlighted ? { outline: '3px solid #00BFA5', boxShadow: '0 0 12px rgba(0,191,165,0.6)', borderRadius: '6px' } : undefined}
                    >
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="40"
                        placeholder="--"
                        value={val}
                        onChange={(e) => handleBolusChange(idx, e.target.value)}
                        className="cell-input cell-event-input"
                        aria-label={`Bolus in slot #${idx + 1}`}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Carbs Row (Active when carbs toggle is ON) */}
          {isCarbsOn && (
            <div className="grid-aligned-row carb-row">
              <div className="row-header-label">
                <strong>Carbs</strong>
                <span className="text-muted text-xs">grams</span>
              </div>
              <div className="slots-24-track">
                {carbSlots.map((val, idx) => {
                  const num = parseFloat(val);
                  const isWarn = num > 120 && num <= 370;
                  const isErr = num < 0 || num > 370;
                  const isHighlighted = highlightedSlot === idx;
                  return (
                    <div
                      key={idx}
                      className={`reading-cell event-cell ${isErr ? 'cell-invalid' : ''} ${isWarn ? 'cell-warn' : ''}`}
                      style={isHighlighted ? { outline: '3px solid #00BFA5', boxShadow: '0 0 12px rgba(0,191,165,0.6)', borderRadius: '6px' } : undefined}
                    >
                      <input
                        type="number"
                        step="1"
                        min="0"
                        max="370"
                        placeholder="--"
                        value={val}
                        onChange={(e) => handleCarbChange(idx, e.target.value)}
                        className="cell-input cell-event-input"
                        aria-label={`Carbs in slot #${idx + 1}`}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {formError && (
          <div className="form-error-banner" role="alert">
            <AlertTriangle size={18} />
            <span>{formError}</span>
          </div>
        )}

        <div className="form-actions">
          <button
            type="button"
            onClick={handleReset}
            className="btn btn-secondary"
            disabled={isLoading}
          >
            <RotateCcw size={16} />
            <span>Clear Grid</span>
          </button>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading || countValid !== 24}
          >
            {isLoading ? (
              <>
                <div className="spinner"></div>
                <span>Executing GPFormer Inference...</span>
              </>
            ) : (
              <>
                <Play size={16} fill="currentColor" />
                <span>Predict Glucose</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Arbitrary Time Event Modal */}
      {showAddEventModal && (
        <div className="modal-overlay">
          <div className="modal-card modal-card-sm">
            <div className="modal-header">
              <h3>
                {newEvent.type === 'bolus' && !isCarbsOn ? 'Add Bolus Event' : (newEvent.type === 'carbs' && !isInsulinOn ? 'Add Carb Event' : 'Add Insulin / Meal Event')}
              </h3>
              <button type="button" className="btn-close" onClick={() => setShowAddEventModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleAddArbitraryEvent} className="modal-form">
              {modalError && (
                <div className="alert-banner-warning" style={{ background: '#fef2f2', borderColor: '#fecaca', color: '#b91c1c', marginBottom: '12px' }}>
                  <AlertTriangle size={15} />
                  <span>{modalError}</span>
                </div>
              )}
              <div className="form-group">
                <label>Event Timestamp (Date & Time):</label>
                <input
                  type="datetime-local"
                  value={newEvent.time}
                  onChange={(e) => {
                    setNewEvent({ ...newEvent, time: e.target.value });
                    setModalError(null);
                  }}
                  className="input-text"
                  required
                />
                {(() => {
                  const p = getSlotPreview(newEvent.time);
                  return p ? (
                    <div style={{ background: '#ecfdf5', border: '1px solid #a7f3d0', padding: '6px 10px', borderRadius: '6px', fontSize: '0.8rem', color: '#047857', marginTop: '6px' }}>
                      Maps to <strong>Slot #{p.slotNumber}</strong> ({p.timeFormatted}, {p.label})
                    </div>
                  ) : null;
                })()}
              </div>

              {isInsulinOn && (
                <div className="form-group">
                  <label>Bolus Dose (Units, 0–40):</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="40"
                    value={newEvent.bolus}
                    onChange={(e) => {
                      setNewEvent({ ...newEvent, bolus: e.target.value });
                      setModalError(null);
                    }}
                    className="input-text"
                    placeholder="e.g. 4.0"
                    autoFocus={newEvent.type === 'bolus'}
                  />
                </div>
              )}

              {isCarbsOn && (
                <div className="form-group">
                  <label>Carbohydrates (Grams, 0–370):</label>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    max="370"
                    value={newEvent.carbs}
                    onChange={(e) => {
                      setNewEvent({ ...newEvent, carbs: e.target.value });
                      setModalError(null);
                    }}
                    className="input-text"
                    placeholder="e.g. 60"
                    autoFocus={newEvent.type === 'carbs'}
                  />
                </div>
              )}

              <p className="text-muted text-xs">
                The event will automatically be mapped to the first 15-min slot at or after the event time.
              </p>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddEventModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Assign to Slot
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
