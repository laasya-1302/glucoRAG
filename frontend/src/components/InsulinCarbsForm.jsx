import React, { useCallback } from 'react';
import { Info } from 'lucide-react';
import {
  getLocalDateTimeString,
  validateBolus,
  validateBasal,
  validateCarb,
  findDuplicateMinuteIds
} from '../utils/multimodal';

/**
 * Generate a unique ID for events.
 */
function generateId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return String(Date.now()) + String(Math.random());
}

/**
 * Toggle switch sub-component.
 */
function ToggleSwitch({ id, checked, onChange, label }) {
  return (
    <div className="toggle-row">
      <label className="toggle-switch" aria-label={label}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-checked={checked}
        />
        <span className="toggle-track" />
      </label>
      <label htmlFor={id} className="toggle-label">{label}</label>
    </div>
  );
}

/**
 * InsulinCarbsForm component.
 *
 * Props:
 *   insulinEnabled, carbsEnabled: bool
 *   onInsulinToggle, onCarbsToggle: (bool) => void
 *   bolusEvents: [{id, time, units}]
 *   setBolusEvents: setter
 *   basalRate: {time, rate} | null
 *   setBasalRate: setter
 *   carbEvents: [{id, time, grams}]
 *   setCarbEvents: setter
 *   latestTimestamp: string (ISO local datetime)
 *   warnings: string[]
 */
export default function InsulinCarbsForm({
  insulinEnabled,
  carbsEnabled,
  onInsulinToggle,
  onCarbsToggle,
  bolusEvents,
  setBolusEvents,
  basalRate,
  setBasalRate,
  carbEvents,
  setCarbEvents,
  latestTimestamp,
  warnings = [],
}) {
  // --- Bolus helpers ---
  const addBolusEvent = useCallback(() => {
    setBolusEvents(prev => [
      ...prev,
      { id: generateId(), time: getLocalDateTimeString(), units: '' }
    ]);
  }, [setBolusEvents]);

  const updateBolusEvent = useCallback((id, field, value) => {
    setBolusEvents(prev =>
      prev.map(ev => ev.id === id ? { ...ev, [field]: value } : ev)
    );
  }, [setBolusEvents]);

  const removeBolusEvent = useCallback((id) => {
    setBolusEvents(prev => prev.filter(ev => ev.id !== id));
  }, [setBolusEvents]);

  // --- Basal helpers ---
  const handleBasalChange = useCallback((field, value) => {
    setBasalRate(prev => ({
      ...(prev || { time: getLocalDateTimeString(), rate: '' }),
      [field]: value
    }));
  }, [setBasalRate]);

  // --- Carb helpers ---
  const addCarbEvent = useCallback(() => {
    setCarbEvents(prev => [
      ...prev,
      { id: generateId(), time: getLocalDateTimeString(), grams: '' }
    ]);
  }, [setCarbEvents]);

  const updateCarbEvent = useCallback((id, field, value) => {
    setCarbEvents(prev =>
      prev.map(ev => ev.id === id ? { ...ev, [field]: value } : ev)
    );
  }, [setCarbEvents]);

  const removeCarbEvent = useCallback((id) => {
    setCarbEvents(prev => prev.filter(ev => ev.id !== id));
  }, [setCarbEvents]);

  // --- Duplicate detection ---
  const bolusDuplicates = findDuplicateMinuteIds(bolusEvents);
  const carbDuplicates = findDuplicateMinuteIds(carbEvents);

  // --- Basal validation ---
  const basalValidation = validateBasal(basalRate, latestTimestamp);

  // Initialize basal rate if it's null and insulin is toggled on
  const effectiveBasal = basalRate || { time: getLocalDateTimeString(), rate: '' };

  return (
    <div className="card insulin-carbs-card" role="region" aria-label="Insulin and Carbs Entry">
      {/* Card Header */}
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <h2 className="card-title">Insulin and Carbs</h2>
          <span
            title="Optionally enter insulin doses and carbohydrate intake to include in the forecast. This is experimental."
            aria-label="Info: Optionally enter insulin doses and carbohydrate intake"
            style={{ cursor: 'help', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center' }}
          >
            <Info size={15} />
          </span>
        </div>
        <p style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', marginTop: '0.2rem' }}>
          Optional: add recent insulin doses or meals to include in the multimodal forecast.
        </p>
      </div>

      {/* Global warnings passed from parent */}
      {warnings.length > 0 && (
        <div className="form-error-banner" role="alert">
          {warnings.map((w, i) => <div key={i}>{w}</div>)}
        </div>
      )}

      {/* ── Insulin Toggle ── */}
      <ToggleSwitch
        id="toggle-insulin"
        checked={insulinEnabled}
        onChange={onInsulinToggle}
        label="I'm entering insulin data"
      />

      {insulinEnabled && (
        <div className="insulin-section-block">
          {/* Bolus Events */}
          <p className="section-label">Bolus Doses</p>
          <div className="event-list" aria-label="Bolus events list">
            {bolusEvents.map((ev) => {
              const { error, warning } = validateBolus(ev, latestTimestamp);
              const isDuplicate = bolusDuplicates.has(ev.id);
              return (
                <div key={ev.id}>
                  <div className="event-row">
                    <input
                      type="datetime-local"
                      className="event-time-input"
                      value={ev.time}
                      max={latestTimestamp || undefined}
                      onChange={(e) => updateBolusEvent(ev.id, 'time', e.target.value)}
                      aria-label="Bolus event time"
                    />
                    <input
                      type="number"
                      className="event-num-input"
                      value={ev.units}
                      min={0}
                      max={40}
                      step={0.5}
                      placeholder="Units"
                      onChange={(e) => updateBolusEvent(ev.id, 'units', e.target.value)}
                      aria-label="Bolus units"
                    />
                    <span className="event-unit-label">U</span>
                    <button
                      type="button"
                      className="event-remove-btn"
                      onClick={() => removeBolusEvent(ev.id)}
                      aria-label="Remove bolus event"
                    >
                      Remove
                    </button>
                  </div>
                  {error && (
                    <div className="event-inline-error" role="alert">{error}</div>
                  )}
                  {!error && warning && (
                    <div className="event-inline-warn" role="status">{warning}</div>
                  )}
                  {!error && !warning && isDuplicate && (
                    <div className="event-inline-info">Duplicate minute – will be summed in model</div>
                  )}
                </div>
              );
            })}
          </div>
          <button
            type="button"
            className="btn-add-event"
            onClick={addBolusEvent}
            aria-label="Add bolus event"
          >
            + Add Bolus Event
          </button>

          {/* Basal Rate */}
          <p className="section-label" style={{ marginTop: '1rem' }}>Basal Rate (latest)</p>
          <div className="basal-row">
            <input
              type="datetime-local"
              className="event-time-input"
              value={effectiveBasal.time}
              max={latestTimestamp || undefined}
              onChange={(e) => handleBasalChange('time', e.target.value)}
              aria-label="Basal rate time"
            />
            <input
              type="number"
              className="event-num-input"
              value={effectiveBasal.rate}
              min={0}
              max={5}
              step={0.05}
              placeholder="Rate"
              onChange={(e) => handleBasalChange('rate', e.target.value)}
              aria-label="Basal rate value"
            />
            <span className="event-unit-label">U/h</span>
          </div>
          {basalValidation.error && (
            <div className="event-inline-error" role="alert">{basalValidation.error}</div>
          )}
        </div>
      )}

      {/* ── Carbs Toggle ── */}
      <ToggleSwitch
        id="toggle-carbs"
        checked={carbsEnabled}
        onChange={onCarbsToggle}
        label="I'm entering carb data"
      />

      {carbsEnabled && (
        <div className="insulin-section-block">
          <p className="section-label">Carbohydrate Events</p>
          <div className="event-list" aria-label="Carb events list">
            {carbEvents.map((ev) => {
              const { error, warning } = validateCarb(ev, latestTimestamp);
              const isDuplicate = carbDuplicates.has(ev.id);
              return (
                <div key={ev.id}>
                  <div className="event-row">
                    <input
                      type="datetime-local"
                      className="event-time-input"
                      value={ev.time}
                      max={latestTimestamp || undefined}
                      onChange={(e) => updateCarbEvent(ev.id, 'time', e.target.value)}
                      aria-label="Carb event time"
                    />
                    <input
                      type="number"
                      className="event-num-input"
                      value={ev.grams}
                      min={0}
                      max={370}
                      step={1}
                      placeholder="Grams"
                      onChange={(e) => updateCarbEvent(ev.id, 'grams', e.target.value)}
                      aria-label="Carb grams"
                    />
                    <span className="event-unit-label">g</span>
                    <button
                      type="button"
                      className="event-remove-btn"
                      onClick={() => removeCarbEvent(ev.id)}
                      aria-label="Remove carb event"
                    >
                      Remove
                    </button>
                  </div>
                  {error && (
                    <div className="event-inline-error" role="alert">{error}</div>
                  )}
                  {!error && warning && (
                    <div className="event-inline-warn" role="status">{warning}</div>
                  )}
                  {!error && !warning && isDuplicate && (
                    <div className="event-inline-info">Duplicate minute – will be summed in model</div>
                  )}
                </div>
              );
            })}
          </div>
          <button
            type="button"
            className="btn-add-event"
            onClick={addCarbEvent}
            aria-label="Add carb event"
          >
            + Add Carb Event
          </button>
        </div>
      )}

      {/* Warning: carbs without insulin */}
      {carbsEnabled && !insulinEnabled && (
        <div className="carbs-warning-box" role="alert">
          <span aria-hidden="true">⚠</span>
          <span>
            Carbs without insulin were rarely seen in training; accuracy is unverified.
          </span>
        </div>
      )}
    </div>
  );
}
