import React, { useState, useEffect, useRef, useCallback } from 'react';
import Header from './components/Header';
import BluetoothCard from './components/BluetoothCard';
import GlucoseInputForm from './components/GlucoseInputForm';
import ForecastChart from './components/ForecastChart';
import ForecastTable from './components/ForecastTable';
import ClinicalAlertCard from './components/ClinicalAlertCard';
import ModelInfoCard from './components/ModelInfoCard';
import ErrorBanner from './components/ErrorBanner';
import RequestInspector from './components/RequestInspector';
import LoginPage from './components/LoginPage';
import ProfileCompletionModal from './components/ProfileCompletionModal';
import Chatbot from './components/Chatbot';
import { AuthProvider, useAuth } from './context/AuthContext';
import { fetchHealth, fetchModelInfo, forecastV1 } from './services/api';
import { bleClient } from './services/ble';

const DEFAULT_READINGS = [
  "142", "138", "135", "132", "129", "127", "125", "128", "131", "134", "139", "145",
  "148", "151", "147", "143", "140", "136", "133", "130", "128", "131", "135", "139"
];

function getLocalDateTimeString() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function MainApp() {
  const { user, isLoading: isAuthLoading, isProfileModalOpen, setIsProfileModalOpen } = useAuth();

  const [readings, setReadings] = useState(DEFAULT_READINGS);
  const [latestTimestamp, setLatestTimestamp] = useState(getLocalDateTimeString());
  const [selectedExperiment, setSelectedExperiment] = useState("e1_gpformer");

  // Multimodal Inputs State
  const [isInsulinOn, setIsInsulinOn] = useState(false);
  const [isCarbsOn, setIsCarbsOn] = useState(false);
  const [bolusSlots, setBolusSlots] = useState(Array(24).fill(''));
  const [carbSlots, setCarbSlots] = useState(Array(24).fill(''));
  const [basalRate, setBasalRate] = useState('');
  const [basalStartTime, setBasalStartTime] = useState('');
  const [isDemoActive, setIsDemoActive] = useState(false);
  
  // API State
  const [health, setHealth] = useState({ online: false });
  const [modelInfo, setModelInfo] = useState(null);
  const [predictionResult, setPredictionResult] = useState(null);
  const [lastSentPayload, setLastSentPayload] = useState(null);
  const [isDev, setIsDev] = useState(() => {
    return typeof window !== 'undefined' && window.location.search.includes('dev=true');
  });
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [formError, setFormError] = useState(null);

  // Bluetooth (BLE) State
  const [bleStatus, setBleStatus] = useState({ state: 'disconnected', deviceName: null, error: null });
  const [isConnecting, setIsConnecting] = useState(false);
  const [latestBleReading, setLatestBleReading] = useState(null);
  const [bleHistoryCount, setBleHistoryCount] = useState(0);
  const [transferProgress, setTransferProgress] = useState(null);

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
   * Helper to trigger GPFormer model inference.
   */
  const runPrediction = useCallback(async (currentReadings, timestamp, experiment) => {
    const valid = currentReadings.map(r => parseFloat(r)).filter(n => !isNaN(n) && n >= 20 && n <= 600);
    if (valid.length !== 24) return;

    setIsLoading(true);
    setApiError(null);

    // Compute slot timestamps for bolus and carbs using local wall-clock ISO (no UTC 'Z' offset shifting)
    const baseDate = timestamp ? new Date(timestamp) : new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const formatLocalIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

    const slotDts = [];
    for (let i = 0; i < 24; i++) {
      const d = new Date(baseDate.getTime() - (23 - i) * 15 * 60000);
      slotDts.push(formatLocalIso(d));
    }

    // Build bolus payload state: toggle OFF -> null; toggle ON, empty -> []; toggle ON, values -> list of events
    let bolusPayload = null;
    let basalPayload = null;
    if (isInsulinOn) {
      const events = [];
      bolusSlots.forEach((val, idx) => {
        const u = parseFloat(val);
        if (!isNaN(u) && u > 0) {
          events.push({ time: slotDts[idx], units: u });
        }
      });
      bolusPayload = events; // [] if none given
      basalPayload = basalRate !== '' && !isNaN(parseFloat(basalRate)) ? parseFloat(basalRate) : 0.9;
    }

    // Build carbs payload state: toggle OFF -> null; toggle ON, empty -> []; toggle ON, values -> list of events
    let carbsPayload = null;
    if (isCarbsOn) {
      const events = [];
      carbSlots.forEach((val, idx) => {
        const g = parseFloat(val);
        if (!isNaN(g) && g > 0) {
          events.push({ time: slotDts[idx], carbs: g });
        }
      });
      carbsPayload = events; // [] if none given
    }

    const payload = {
      modelId: experiment,
      readings: currentReadings,
      units: "mg/dL",
      bolus: bolusPayload,
      basal: basalPayload,
      carbs: carbsPayload,
      grid: "manual",
      latestTimestamp: timestamp
    };
    setLastSentPayload(payload);

    try {
      const response = await forecastV1(payload);
      setPredictionResult(response);
      setHealth({ online: true });
    } catch (err) {
      setApiError(err);
    } finally {
      setIsLoading(false);
    }
  }, [isInsulinOn, isCarbsOn, bolusSlots, carbSlots, basalRate]);

  /**
   * Configures BLE callbacks and handles connection lifecycle.
   */
  useEffect(() => {
    bleClient.onStatusChange = (status) => {
      setBleStatus(status);
      if (status.state === 'connected') {
        setIsConnecting(false);
      } else if (status.state === 'disconnected') {
        setIsConnecting(false);
        setTransferProgress(null);
      }
    };

    bleClient.onReading = (readingMsg) => {
      if (!readingMsg || readingMsg.glucose == null) return;

      if (readingMsg.sequence != null) {
        if (processedSequencesRef.current.has(readingMsg.sequence)) {
          return;
        }
        processedSequencesRef.current.add(readingMsg.sequence);
      }

      setLatestBleReading(readingMsg);

      setReadings((prev) => {
        const nextList = [...prev.slice(1), String(readingMsg.glucose)];
        return nextList;
      });

      setBleHistoryCount(prev => prev + 1);

      if (readingMsg.timestamp) {
        try {
          const parsed = new Date(readingMsg.timestamp);
          if (!isNaN(parsed.getTime())) {
            parsed.setMinutes(parsed.getMinutes() - parsed.getTimezoneOffset());
            const localFormatted = parsed.toISOString().slice(0, 16);
            setLatestTimestamp(localFormatted);
          }
        } catch {}
      }

      const updatedWindow = [...readingsRef.current.slice(1), String(readingMsg.glucose)];
      runPrediction(updatedWindow, readingMsg.timestamp, selectedExperimentRef.current);
    };

    bleClient.onHistoryProgress = (progress) => {
      setTransferProgress(progress);
      if (progress.latestReading) {
        setLatestBleReading(progress.latestReading);
      }
    };

    bleClient.onHistoryComplete = ({ readings: transferredReadings, count }) => {
      setTransferProgress(null);
      if (!transferredReadings || transferredReadings.length === 0) return;

      const sorted = [...transferredReadings].sort((a, b) => {
        if (a.sequence != null && b.sequence != null) {
          return a.sequence - b.sequence;
        }
        return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      });

      const stringified = sorted.map(r => String(r.glucose));
      setReadings(stringified);
      setBleHistoryCount(count);

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

      sorted.forEach(r => {
        if (r.sequence != null) processedSequencesRef.current.add(r.sequence);
      });

      if (stringified.length === 24) {
        runPrediction(stringified, lastPoint?.timestamp, selectedExperimentRef.current);
      }
    };

    return () => {
      bleClient.onStatusChange = null;
      bleClient.onReading = null;
      bleClient.onHistoryProgress = null;
      bleClient.onHistoryComplete = null;
    };
  }, [runPrediction]);

  // Connect BLE Device
  const handleConnectBle = async (acceptAll = false) => {
    setIsConnecting(true);
    setBleStatus(prev => ({ ...prev, error: null }));
    try {
      await bleClient.connect({ acceptAll });
    } catch (err) {
      setIsConnecting(false);
    }
  };

  const handleDisconnectBle = () => {
    bleClient.disconnect();
  };

  const handleRequestHistory = async () => {
    try {
      await bleClient.requestHistory();
    } catch (err) {
      setBleStatus(prev => ({ ...prev, error: err.message }));
    }
  };

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

    await runPrediction(readings, latestTimestamp, selectedExperiment);
  };

  // Auth loading state
  if (isAuthLoading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading GPFormer Forecasting System...</p>
      </div>
    );
  }

  // If user is not logged in, show clinical LoginPage
  if (!user) {
    return <LoginPage />;
  }

  return (
    <div className="app-layout">
      {/* Profile Completion / Edit Modal */}
      <ProfileCompletionModal
        isOpen={isProfileModalOpen || !user.profile_complete}
        onClose={() => setIsProfileModalOpen(false)}
      />

      <Header
        selectedExp={selectedExperiment}
        onSelectExp={(exp) => setSelectedExperiment(exp)}
        availableExps={modelInfo?.available_experiments}
        healthStatus={health}
        onRefreshHealth={checkHealthAndModel}
        onOpenProfile={() => setIsProfileModalOpen(true)}
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

        {/* Glucose & Multimodal Inputs */}
        <GlucoseInputForm
          readings={readings}
          setReadings={setReadings}
          latestTimestamp={latestTimestamp}
          setLatestTimestamp={setLatestTimestamp}
          onSubmit={handlePredict}
          isLoading={isLoading}
          formError={formError}
          setFormError={setFormError}
          isInsulinOn={isInsulinOn}
          setIsInsulinOn={setIsInsulinOn}
          isCarbsOn={isCarbsOn}
          setIsCarbsOn={setIsCarbsOn}
          bolusSlots={bolusSlots}
          setBolusSlots={setBolusSlots}
          carbSlots={carbSlots}
          setCarbSlots={setCarbSlots}
          basalRate={basalRate}
          setBasalRate={setBasalRate}
          basalStartTime={basalStartTime}
          setBasalStartTime={setBasalStartTime}
          isDemoActive={isDemoActive}
          setIsDemoActive={setIsDemoActive}
        />

        {/* Prediction Results Section */}
        {predictionResult && (
          <section className="results-section">
            <ClinicalAlertCard
              alert={predictionResult.clinical_alert}
              experimentName={predictionResult.model_name || predictionResult.experiment_description}
              disclaimer={predictionResult.disclaimer}
              mode={predictionResult.mode}
              inputsUsed={predictionResult.inputs_used}
            />

            <ForecastChart
              historicalReadings={readings}
              forecastData={predictionResult.forecast}
              units={predictionResult.units}
            />

            <ForecastTable
              forecast={predictionResult.forecast}
              units={predictionResult.units}
              mode={predictionResult.mode}
              inputsUsed={predictionResult.inputs_used}
              modelName={predictionResult.model_name}
              checkpointHashes={predictionResult.checkpoint_sha256}
            />

            <RequestInspector
              requestPayload={lastSentPayload}
              predictionResult={predictionResult}
              isDev={isDev}
              onToggleDev={() => setIsDev(prev => !prev)}
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

      {/* Patient Decision Support Chatbot */}
      <Chatbot
        latestReading={readings && readings.length > 0 ? readings[readings.length - 1] : null}
        predictionResult={predictionResult}
      />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}
