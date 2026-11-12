import React, { useState, useEffect, useRef, useCallback } from 'react';
import Header from './components/Header';
import BluetoothCard from './components/BluetoothCard';
import GlucoseInputForm from './components/GlucoseInputForm';
import InsulinCarbsForm from './components/InsulinCarbsForm';
import ForecastChart from './components/ForecastChart';
import ForecastTable from './components/ForecastTable';
import ClinicalAlertCard from './components/ClinicalAlertCard';
import ModelInfoCard from './components/ModelInfoCard';
import ErrorBanner from './components/ErrorBanner';
import { fetchHealth, fetchModelInfo, predictGlucose } from './services/api';
import { bleClient } from './services/ble';
import { buildEventPayloads, computeHorizonDifferences } from './utils/multimodal';

const DEFAULT_READINGS = [
  "142", "138", "135", "132", "129", "127", "125", "128", "131", "134", "139", "145",
  "148", "151", "147", "143", "140", "136", "133", "130", "128", "131", "135", "139"
];

function getLocalDateTimeString() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

export default function App() {
  const [readings, setReadings] = useState(DEFAULT_READINGS);
  const [latestTimestamp, setLatestTimestamp] = useState(getLocalDateTimeString());
  const [selectedExperiment, setSelectedExperiment] = useState("gp_A");

  // API State
  const [health, setHealth] = useState({ online: false });
  const [modelInfo, setModelInfo] = useState(null);
  const [predictionResult, setPredictionResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [formError, setFormError] = useState(null);

  // Bluetooth (BLE) State
  const [bleStatus, setBleStatus] = useState({ state: 'disconnected', deviceName: null, error: null });
  const [isConnecting, setIsConnecting] = useState(false);
  const [latestBleReading, setLatestBleReading] = useState(null);
  const [bleHistoryCount, setBleHistoryCount] = useState(0);
  const [transferProgress, setTransferProgress] = useState(null);

  // Insulin & Carbs State
  const [insulinEnabled, setInsulinEnabled] = useState(false);
  const [carbsEnabled, setCarbsEnabled] = useState(false);
  const [bolusEvents, setBolusEvents] = useState([]); // [{id, time, units}]
  const [basalRate, setBasalRate] = useState(null);   // {time, rate} | null
  const [carbEvents, setCarbEvents] = useState([]);   // [{id, time, grams}]

  // Comparison with CGM-only State
  const [compareWithCgmOnly, setCompareWithCgmOnly] = useState(false);
  const [cgmOnlyForecast, setCgmOnlyForecast] = useState(null);
  const [isComparing, setIsComparing] = useState(false);

  // Track sequence numbers to prevent duplicate processing
  const processedSequencesRef = useRef(new Set());
  const readingsRef = useRef(readings);
  readingsRef.current = readings;

  const selectedExperimentRef = useRef(selectedExperiment);
  selectedExperimentRef.current = selectedExperiment;

  // Initial diagnostics load
  useEffect(() => {
    checkHealthAndModel();
  }, []);

  // Load insulin/carbs state from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem('glucorag_insulin_carbs');
      if (saved) {
        const d = JSON.parse(saved);
        if (d.insulinEnabled !== undefined) setInsulinEnabled(d.insulinEnabled);
        if (d.carbsEnabled !== undefined) setCarbsEnabled(d.carbsEnabled);
        if (d.bolusEvents) setBolusEvents(d.bolusEvents);
        if (d.basalRate !== undefined) setBasalRate(d.basalRate);
        if (d.carbEvents) setCarbEvents(d.carbEvents);
      }
    } catch {
      // Ignore parse errors
    }
  }, []);

  // Persist insulin/carbs state to localStorage whenever they change
  useEffect(() => {
    try {
      localStorage.setItem('glucorag_insulin_carbs', JSON.stringify({
        insulinEnabled, carbsEnabled, bolusEvents, basalRate, carbEvents
      }));
    } catch {
      // Ignore storage errors
    }
  }, [insulinEnabled, carbsEnabled, bolusEvents, basalRate, carbEvents]);

  const checkHealthAndModel = async () => {
    try {
      const h = await fetchHealth();
      setHealth({ online: h.api_online && h.model_loaded });
    } catch {
      setHealth({ online: false });
    }

    try {
      const info = await fetchModelInfo();
      setModelInfo(info);
    } catch {
      // Ignored
    }
  };

  /**
   * Helper to build bolus/basal/carb payloads for the API using multimodal utils.
   * Pass forceNull=true (BLE live mode) to send null for all three-state fields.
   */
  const buildCurrentPayloads = useCallback((forceNull = false) => {
    return buildEventPayloads({
      insulinEnabled,
      carbsEnabled,
      bolusEvents,
      basalRate,
      carbEvents,
      latestTimestamp,
      forceNull
    });
  }, [insulinEnabled, carbsEnabled, bolusEvents, basalRate, carbEvents, latestTimestamp]);

  /**
   * Helper to trigger GPFormer model inference whenever 24 valid readings are present.
   * options: { bolusEvents, basalEvents, carbEvents } — pass null values for BLE live mode
   */
  const runPrediction = useCallback(async (currentReadings, timestamp, experiment, options = {}) => {
    const valid = currentReadings.map(r => parseFloat(r)).filter(n => !isNaN(n) && n >= 20 && n <= 600);
    if (valid.length !== 24) return;

    setIsLoading(true);
    setApiError(null);
    setCgmOnlyForecast(null); // Reset comparison cache on new run
    try {
      const response = await predictGlucose(currentReadings, timestamp, experiment, options);
      setPredictionResult(response);
      setHealth({ online: true });
    } catch (err) {
      setApiError(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Configures BLE callbacks and handles connection lifecycle.
   */
  useEffect(() => {
    // 1. Connection status change listener
    bleClient.onStatusChange = (status) => {
      setBleStatus(status);
      if (status.state === 'connected') {
        setIsConnecting(false);
      } else if (status.state === 'disconnected') {
        setIsConnecting(false);
        setTransferProgress(null);
      }
    };

    // 2. Incoming single live reading listener (manual or simulated)
    bleClient.onReading = (readingMsg) => {
      if (!readingMsg || readingMsg.glucose == null) return;

      // Duplicate check using sequence number
      if (readingMsg.sequence != null) {
        if (processedSequencesRef.current.has(readingMsg.sequence)) {
          return;
        }
        processedSequencesRef.current.add(readingMsg.sequence);
      }

      setLatestBleReading(readingMsg);

      // Slide the 24-window: remove oldest (index 0), append new value at end (index 23)
      setReadings((prev) => {
        const nextList = [...prev.slice(1), String(readingMsg.glucose)];
        return nextList;
      });

      setBleHistoryCount(prev => prev + 1);

      // Update timestamp if valid
      if (readingMsg.timestamp) {
        try {
          const parsed = new Date(readingMsg.timestamp);
          if (!isNaN(parsed.getTime())) {
            parsed.setMinutes(parsed.getMinutes() - parsed.getTimezoneOffset());
            const localFormatted = parsed.toISOString().slice(0, 16);
            setLatestTimestamp(localFormatted);
          }
        } catch {
          // Keep current timestamp
        }
      }

      // Re-run GPFormer inference automatically on live streaming reading
      // BLE live readings use CGM-only mode (null for all event payloads)
      const updatedWindow = [...readingsRef.current.slice(1), String(readingMsg.glucose)];
      runPrediction(updatedWindow, readingMsg.timestamp, selectedExperimentRef.current, {
        bolusEvents: null,
        basalEvents: null,
        carbEvents: null,
      });
    };

    // 3. Initial 24-reading transfer progress listener
    bleClient.onHistoryProgress = (progress) => {
      setTransferProgress(progress);
      if (progress.latestReading) {
        setLatestBleReading(progress.latestReading);
      }
    };

    // 4. Initial 24-reading transfer completion listener
    bleClient.onHistoryComplete = ({ readings: transferredReadings, count }) => {
      setTransferProgress(null);
      if (!transferredReadings || transferredReadings.length === 0) return;

      // Sort chronologically by sequence or timestamp
      const sorted = [...transferredReadings].sort((a, b) => {
        if (a.sequence != null && b.sequence != null) {
          return a.sequence - b.sequence;
        }
        return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      });

      // Populate input grid with exactly 24 readings
      const stringified = sorted.map(r => String(r.glucose));
      setReadings(stringified);
      setBleHistoryCount(count);

      // Set latest reading from the 24th point
      const lastPoint = sorted[sorted.length - 1];
      if (lastPoint) {
        setLatestBleReading(lastPoint);
        if (lastPoint.timestamp) {
          try {
            const dt = new Date(lastPoint.timestamp);
            if (!isNaN(dt.getTime())) {
              dt.setMinutes(dt.getMinutes() - dt.getTimezoneOffset());
              setLatestTimestamp(dt.toISOString().slice(0, 16));
            }
          } catch {}
        }
      }

      // Mark all transferred sequences as processed
      sorted.forEach(r => {
        if (r.sequence != null) processedSequencesRef.current.add(r.sequence);
      });

      // Trigger GPFormer prediction immediately with the fresh 24-reading history
      // BLE history transfers use CGM-only mode (null for all event payloads)
      if (stringified.length === 24) {
        runPrediction(stringified, lastPoint?.timestamp, selectedExperimentRef.current, {
          bolusEvents: null,
          basalEvents: null,
          carbEvents: null,
        });
      }
    };

    return () => {
      // Cleanup event listeners
      bleClient.onStatusChange = null;
      bleClient.onReading = null;
      bleClient.onHistoryProgress = null;
      bleClient.onHistoryComplete = null;
    };
  }, [runPrediction]);

  // Connect BLE Device
  const handleConnectBle = async () => {
    setIsConnecting(true);
    setBleStatus(prev => ({ ...prev, error: null }));
    try {
      await bleClient.connect();
    } catch (err) {
      setIsConnecting(false);
    }
  };

  // Disconnect BLE
  const handleDisconnectBle = () => {
    bleClient.disconnect();
  };

  // Request 24 History Readings from Android phone
  const handleRequestHistory = async () => {
    try {
      await bleClient.requestHistory();
    } catch (err) {
      setBleStatus(prev => ({ ...prev, error: err.message }));
    }
  };

  // Clear received history
  const handleClearBleHistory = () => {
    processedSequencesRef.current.clear();
    setLatestBleReading(null);
    setBleHistoryCount(0);
    setTransferProgress(null);
    setReadings(Array(24).fill(''));
  };

  const handlePredict = async (e) => {
    if (e) e.preventDefault();
    setFormError(null);
    setApiError(null);

    // Validate 24 readings
    if (readings.length !== 24) {
      setFormError(`Exactly 24 readings required. Current count: ${readings.length}`);
      return;
    }

    for (let i = 0; i < 24; i++) {
      const r = readings[i];
      if (r === '' || r === null || r === undefined) {
        setFormError(`Reading #${i + 1} is empty. Exactly 24 continuous readings are required.`);
        return;
      }
      const num = parseFloat(r);
      if (isNaN(num)) {
        setFormError(`Reading #${i + 1} ('${r}') is not a valid number.`);
        return;
      }
      if (num < 20 || num > 600) {
        setFormError(`Reading #${i + 1} (${num} mg/dL) is outside acceptable physiological range [20, 600] mg/dL.`);
        return;
      }
    }

    // Build event payloads from current insulin/carbs state
    const eventPayloads = buildCurrentPayloads(false);
    await runPrediction(readings, latestTimestamp, selectedExperiment, eventPayloads);
  };

  const handleToggleCompare = async (checked) => {
    setCompareWithCgmOnly(checked);
    if (checked && !cgmOnlyForecast && predictionResult) {
      setIsComparing(true);
      try {
        const cgmOnlyRes = await predictGlucose(readings, latestTimestamp, selectedExperiment, {
          bolusEvents: null,
          basalEvents: null,
          carbEvents: null,
        });
        setCgmOnlyForecast(cgmOnlyRes.forecast);
      } catch (err) {
        console.warn("Failed to fetch glucose-only forecast comparison", err);
      } finally {
        setIsComparing(false);
      }
    }
  };

  const horizonDiffs = (predictionResult?.mode === 'E1' && cgmOnlyForecast)
    ? computeHorizonDifferences(predictionResult.forecast, cgmOnlyForecast)
    : [];

  return (
    <div className="app-layout">
      <Header
        selectedExp={selectedExperiment}
        onSelectExp={(exp) => setSelectedExperiment(exp)}
        availableExps={modelInfo?.available_experiments}
        healthStatus={health}
        onRefreshHealth={checkHealthAndModel}
      />

      <main className="main-content">
        {apiError && (
          <ErrorBanner
            error={apiError}
            onRetry={handlePredict}
            onDismiss={() => setApiError(null)}
          />
        )}

        {/* Bluetooth (BLE) Integration Card */}
        <BluetoothCard
          bleStatus={bleStatus}
          onConnect={handleConnectBle}
          onDisconnect={handleDisconnectBle}
          onRequestHistory={handleRequestHistory}
          onClearHistory={handleClearBleHistory}
          latestReading={latestBleReading}
          receivedCount={bleHistoryCount}
          transferProgress={transferProgress}
          isConnecting={isConnecting}
        />

        {/* Glucose Inputs */}
        <GlucoseInputForm
          readings={readings}
          setReadings={setReadings}
          latestTimestamp={latestTimestamp}
          setLatestTimestamp={setLatestTimestamp}
          onSubmit={handlePredict}
          isLoading={isLoading}
          formError={formError}
          setFormError={setFormError}
        />

        {/* Insulin & Carbs Section */}
        <InsulinCarbsForm
          insulinEnabled={insulinEnabled}
          carbsEnabled={carbsEnabled}
          onInsulinToggle={setInsulinEnabled}
          onCarbsToggle={setCarbsEnabled}
          bolusEvents={bolusEvents}
          setBolusEvents={setBolusEvents}
          basalRate={basalRate}
          setBasalRate={setBasalRate}
          carbEvents={carbEvents}
          setCarbEvents={setCarbEvents}
          latestTimestamp={latestTimestamp}
          warnings={[]}
        />

        {/* Prediction Results Section */}
        {predictionResult && (
          <section className="results-section">
            <ClinicalAlertCard
              alert={predictionResult.clinical_alert}
              experimentName={predictionResult.experiment_description || predictionResult.model_name}
              disclaimer={predictionResult.disclaimer}
              mode={predictionResult.mode}
              inputsUsed={predictionResult.inputs_used}
              compareWithCgmOnly={compareWithCgmOnly}
              onToggleCompare={handleToggleCompare}
              isComparing={isComparing}
            />

            <ForecastChart
              historicalReadings={readings}
              forecastData={predictionResult.forecast}
              units={predictionResult.units}
            />

            <ForecastTable
              forecast={predictionResult.forecast}
              units={predictionResult.units}
              compareWithCgmOnly={compareWithCgmOnly}
              horizonDiffs={horizonDiffs}
            />
          </section>
        )}

        {/* Model Information Card */}
        <ModelInfoCard
          modelInfo={modelInfo}
          activeExperiment={selectedExperiment}
          onSelectExperiment={(exp) => setSelectedExperiment(exp)}
        />
      </main>

      <footer className="app-footer">
        <p>
          GPFormer Blood Glucose Forecasting System &copy; 2026. Built with FastAPI backend and React frontend.
        </p>
      </footer>
    </div>
  );
}
