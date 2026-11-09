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
  insulinEvents = [],
  carbEvents = []
}) {
  const payload = {
    model_id: modelId,
    readings: readings.map(r => (typeof r === 'object' && r !== null) ? r : Number(r)),
    latest_timestamp: latestTimestamp || null,
    insulin_events: insulinEvents,
    carb_events: carbEvents
  };

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

export async function predictGlucose(readings, latestTimestamp, experiment = "gp_A", options = {}) {
  const payload = {
    readings: readings.map(r => (typeof r === 'object' && r !== null) ? r : Number(r)),
    latest_timestamp: latestTimestamp || null,
    experiment: experiment,
    model_id: experiment,
    insulin_events: options.insulinEvents || [],
    carb_events: options.carbEvents || []
  };

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
