const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

let inMemoryCsrfToken = "";

export function setCsrfToken(token) {
  inMemoryCsrfToken = token || "";
}

export function getCsrfToken() {
  return inMemoryCsrfToken;
}

function getHeaders(customHeaders = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...customHeaders
  };
  if (inMemoryCsrfToken) {
    headers["X-CSRF-Token"] = inMemoryCsrfToken;
  }
  return headers;
}

// ---------------- AUTH API ----------------

export async function fetchCurrentUser() {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/me`, {
      method: "GET",
      credentials: "include",
      headers: getHeaders()
    });
    if (res.status === 401) {
      return null;
    }
    if (!res.ok) {
      throw new Error(`Failed to fetch current user (${res.status})`);
    }
    const data = await res.json();
    if (data?.csrf_token) {
      setCsrfToken(data.csrf_token);
    }
    return data;
  } catch (err) {
    return null;
  }
}

export function getGoogleLoginUrl() {
  return `${API_BASE_URL}/auth/google/login`;
}

export async function loginWithMock({ email = "researcher@example.org", name = "Dr. Research User", sub = null } = {}) {
  const res = await fetch(`${API_BASE_URL}/auth/mock/login`, {
    method: "POST",
    credentials: "include",
    headers: getHeaders(),
    body: JSON.stringify({ email, name, sub })
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.message || data?.error || `Mock login failed (${res.status})`);
  }
  if (data?.csrf_token) {
    setCsrfToken(data.csrf_token);
  }
  return data;
}

export async function updateProfile({ name, age, gender, consent, minor_confirmed = false }) {
  const res = await fetch(`${API_BASE_URL}/auth/profile`, {
    method: "POST",
    credentials: "include",
    headers: getHeaders(),
    body: JSON.stringify({
      name,
      age: Number(age),
      gender: gender || null,
      consent: Boolean(consent),
      minor_confirmed: Boolean(minor_confirmed)
    })
  });
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data?.message || data?.error || `Profile update failed (${res.status})`);
    err.details = data;
    throw err;
  }
  return data;
}

export async function logoutUser() {
  const res = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: getHeaders()
  });
  setCsrfToken("");
  return res.json();
}

export async function deleteUserAccount() {
  const res = await fetch(`${API_BASE_URL}/auth/me`, {
    method: "DELETE",
    credentials: "include",
    headers: getHeaders()
  });
  setCsrfToken("");
  return res.json();
}

// ---------------- FORECASTING API ----------------

export async function fetchHealth() {
  const res = await fetch(`${API_BASE_URL}/health`, {
    credentials: "include"
  });
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchModelInfo() {
  const res = await fetch(`${API_BASE_URL}/model-info`, {
    credentials: "include"
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch model info: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchV1Models() {
  const res = await fetch(`${API_BASE_URL}/v1/models`, {
    credentials: "include"
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch v1 models: ${res.statusText}`);
  }
  return res.json();
}

export async function forecastV1({
  modelId = "e1_gpformer",
  readings = [],
  units = "mg/dL",
  bolus = null,
  basal = null,
  carbs = null,
  grid = "manual",
  latestTimestamp = null,
  bolusEvents = undefined,
  basalEvents = undefined,
  carbEvents = undefined,
  insulinEvents = undefined
}) {
  const payload = {
    model_id: modelId,
    readings: readings.map(r => (typeof r === 'object' && r !== null) ? r : Number(r)),
    units,
    bolus,
    basal,
    carbs,
    grid,
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
    credentials: "include",
    headers: getHeaders(),
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if (!res.ok) {
    const errorMsg = data?.message || data?.error || (typeof data?.detail === "string" ? data.detail : data?.detail?.message) || `Error ${res.status}`;
    const errorObj = new Error(errorMsg);
    errorObj.status = res.status;
    errorObj.code = data?.code;
    errorObj.details = data;
    throw errorObj;
  }

  return data;
}

export async function predictGlucose(readings, latestTimestamp, experiment = "e1_gpformer", options = {}) {
  // Support both legacy predict and v1 forecast
  if (experiment === "e1_gpformer") {
    return forecastV1({
      modelId: "e1_gpformer",
      readings,
      latestTimestamp,
      bolus: options.bolus ?? null,
      basal: options.basal ?? null,
      carbs: options.carbs ?? null,
      grid: options.grid || "manual",
      bolusEvents: options.bolusEvents,
      basalEvents: options.basalEvents,
      carbEvents: options.carbEvents,
      insulinEvents: options.insulinEvents
    });
  }

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
    credentials: "include",
    headers: getHeaders(),
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

// ---------------- PATIENT CHATBOT API ----------------

export async function sendChatMessage({ message, history = [], glucoseContext = null }) {
  const payload = {
    message,
    history,
    glucose_context: glucoseContext
  };

  const res = await fetch(`${API_BASE_URL}/v1/chat`, {
    method: "POST",
    credentials: "include",
    headers: getHeaders(),
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if (!res.ok) {
    const errorMsg = data?.message || data?.error || (typeof data?.detail === "string" ? data.detail : data?.detail?.message) || `Chat error (${res.status})`;
    throw new Error(errorMsg);
  }

  return data;
}
