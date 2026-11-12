const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchModelInfo() {
  const res = await fetch(`${API_BASE_URL}/model-info`);
  if (!res.ok) {
    throw new Error(`Failed to fetch model info: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchV1Models() {
  const res = await fetch(`${API_BASE_URL}/v1/models`);
  if (!res.ok) {
    throw new Error(`Failed to fetch v1 models: ${res.statusText}`);
  }
  return res.json();
}

export async function forecastV1({
  modelId = "e1_gpformer",
  readings = [],
  latestTimestamp = null,
  bolusEvents = undefined,
  basalEvents = undefined,
  carbEvents = undefined,
  insulinEvents = undefined
}) {
  const payload = {
    model_id: modelId,
    readings: readings.map(r => (typeof r === 'object' && r !== null) ? r : Number(r)),
    latest_timestamp: latestTimestamp || null,
  };

  if (bolusEvents !== undefined) {
    payload.bolus_events = bolusEvents;
  }
  if (basalEvents !== undefined) {
    payload.basal_events = basalEvents;
  }
  if (carbEvents !== undefined) {
    payload.carb_events = carbEvents;
  }
  if (insulinEvents !== undefined) {
    payload.insulin_events = insulinEvents;
  }

  const res = await fetch(`${API_BASE_URL}/v1/forecast`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if (!res.ok) {
    const errorMsg = data?.message || data?.error || (typeof data?.detail === "string" ? data.detail : data?.detail?.message) || `Error ${res.status}`;
    const errorObj = new Error(errorMsg);
    errorObj.status = res.status;
    errorObj.details = data;
    throw errorObj;
  }

  return data;
}

export async function predictGlucose(readings, latestTimestamp, experiment = "e1_gpformer", options = {}) {
  const payload = {
    readings: readings.map(r => (typeof r === 'object' && r !== null) ? r : Number(r)),
    latest_timestamp: latestTimestamp || null,
    experiment: experiment,
    model_id: experiment,
  };

  // Three-state logic: null = not available, [] = available/no events, [...] = events present
  if (options.bolusEvents !== undefined) {
    payload.bolus_events = options.bolusEvents;
  } else if (options.insulinEvents !== undefined) {
    payload.bolus_events = options.insulinEvents;
  }

  if (options.basalEvents !== undefined) {
    payload.basal_events = options.basalEvents;
  }

  if (options.carbEvents !== undefined) {
    payload.carb_events = options.carbEvents;
  }

  const res = await fetch(`${API_BASE_URL}/predict`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if (!res.ok) {
    const errorMsg = data?.message || data?.error || (typeof data?.detail === "string" ? data.detail : data?.detail?.message) || `Error ${res.status}`;
    const errorObj = new Error(errorMsg);
    errorObj.status = res.status;
    errorObj.details = data;
    throw errorObj;
  }

  return data;
}
