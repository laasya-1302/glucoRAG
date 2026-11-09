# GlucoseTransmitter – BLE Communication Protocol & Integration Guide

## 1. Architecture Overview

```
┌──────────────────────┐         BLE          ┌──────────────────────────┐
│  Android Phone       │◄────────────────────►│  Laptop Chrome Browser   │
│  (GATT Server /      │   Notifications      │  (GATT Client /          │
│   Peripheral)        │   Writes             │   Central)               │
│                      │                      │                          │
│  GlucoseTransmitter  │                      │  Web Bluetooth API       │
│  App                 │                      │  → React Frontend        │
│                      │                      │  → FastAPI Backend       │
│                      │                      │  → GPFormer Model        │
└──────────────────────┘                      └──────────────────────────┘
```

**Key concept:** The Android phone is the BLE **Peripheral** (GATT Server). The laptop Chrome browser is the BLE **Central** (GATT Client). Data flows from phone → laptop via BLE notifications.

---

## 2. GATT Service & Characteristic UUIDs

| Item | UUID | Properties |
|------|------|------------|
| **Glucose Service** | `1337BEEF-4750-466F-726D-657242470001` | Primary Service |
| **Glucose Data Characteristic** | `1337BEEF-4750-466F-726D-657242470002` | NOTIFY, READ |
| **Control Characteristic** | `1337BEEF-4750-466F-726D-657242470003` | WRITE, WRITE_NO_RESPONSE |
| **CCCD Descriptor** | `00002902-0000-1000-8000-00805F9B34FB` | Standard BLE CCCD |

**Device Advertised Name:** `GlucoseTransmitter`

---

## 3. Message Formats (JSON over BLE)

All messages are UTF-8 encoded JSON strings sent as BLE characteristic values.

### 3.1 Single Glucose Reading (Phone → Laptop)

Sent as a notification on the Glucose Data Characteristic whenever a new reading is added (manual or simulated).

```json
{
  "type": "glucose_reading",
  "sequence": 25,
  "glucose": 145.0,
  "unit": "mg/dL",
  "timestamp": "2026-11-02T12:45:00+05:30",
  "source": "manual"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"glucose_reading"` for individual readings |
| `sequence` | integer | Monotonically increasing sequence number (starts at 1) |
| `glucose` | number | Blood glucose value in mg/dL (range: 20.0–600.0) |
| `unit` | string | Always `"mg/dL"` |
| `timestamp` | string | ISO 8601 with timezone offset (e.g., `2026-11-02T12:45:00+05:30`) |
| `source` | string | `"manual"` for user-entered, `"simulated"` for auto-generated |

### 3.2 History Item (Phone → Laptop)

Sent during initial 24-reading history transfer. Each of the 24 readings is wrapped in a history envelope:

```json
{
  "type": "history_item",
  "transfer_id": "tx_1730530200000",
  "packet_index": 0,
  "total_packets": 24,
  "reading": {
    "type": "glucose_reading",
    "sequence": 1,
    "glucose": 112.5,
    "unit": "mg/dL",
    "timestamp": "2026-11-02T06:45:00+05:30",
    "source": "simulated"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"history_item"` |
| `transfer_id` | string | Unique ID for this transfer batch (format: `tx_<timestamp_ms>`) |
| `packet_index` | integer | Zero-based index within the transfer (0 to total_packets-1) |
| `total_packets` | integer | Total number of readings in this transfer (typically 24) |
| `reading` | object | The glucose reading object (same format as Section 3.1) |

### 3.3 History Transfer Complete (Phone → Laptop)

Sent after all history items have been dispatched:

```json
{
  "type": "history_complete",
  "transfer_id": "tx_1730530200000",
  "total_packets": 24,
  "status": "complete"
}
```

### 3.4 Client Commands (Laptop → Phone)

Written to the Control Characteristic by the Web Bluetooth client.

#### Request History Transfer
```json
{
  "cmd": "request_history",
  "request_id": "optional_client_id"
}
```

#### Acknowledge Transfer
```json
{
  "cmd": "history_ack",
  "transfer_id": "tx_1730530200000",
  "status": "ok"
}
```

#### Request Single Missing Packet
```json
{
  "cmd": "request_packet",
  "transfer_id": "tx_1730530200000",
  "packet_index": 5
}
```

---

## 4. Initial 24-Reading History Transfer Protocol

```
Laptop (Central)                           Phone (Peripheral)
     │                                          │
     │  Connect to GATT Service                 │
     │────────────────────────────────────────►  │
     │                                          │
     │  Subscribe to Glucose Data notifications │
     │────────────────────────────────────────►  │
     │                                          │
     │  Write "request_history" to Control      │
     │────────────────────────────────────────►  │
     │                                          │
     │  ◄── history_item (packet_index=0)  ────│
     │  ◄── history_item (packet_index=1)  ────│
     │  ◄── ...                            ────│
     │  ◄── history_item (packet_index=23) ────│
     │  ◄── history_complete               ────│
     │                                          │
     │  Write "history_ack" to Control          │
     │────────────────────────────────────────►  │
     │                                          │
     │  [Now receiving live notifications]      │
     │  ◄── glucose_reading (sequence=25)  ────│
     │  ◄── glucose_reading (sequence=26)  ────│
     │  ...                                     │
```

**Pacing:** Packets are sent with ~60ms delays between them to avoid BLE GATT buffer overflow.

**Missing packets:** If the laptop detects a gap in `packet_index`, it can write a `request_packet` command to request retransmission of the specific missing packet.

---

## 5. React Frontend Integration (Web Bluetooth)

### 5.1 Discovering & Connecting

```javascript
// UUIDs matching the Android GATT server
const SERVICE_UUID         = '1337beef-4750-466f-726d-657242470001';
const DATA_CHAR_UUID       = '1337beef-4750-466f-726d-657242470002';
const CONTROL_CHAR_UUID    = '1337beef-4750-466f-726d-657242470003';

let device, server, service, dataChar, controlChar;

async function connectToTransmitter() {
  // Step 1: Request device (shows browser pairing dialog)
  device = await navigator.bluetooth.requestDevice({
    filters: [{ name: 'GlucoseTransmitter' }],
    optionalServices: [SERVICE_UUID]
  });

  // Step 2: Connect to GATT server
  server = await device.gatt.connect();

  // Step 3: Get the Glucose Service
  service = await server.getPrimaryService(SERVICE_UUID);

  // Step 4: Get characteristics
  dataChar    = await service.getCharacteristic(DATA_CHAR_UUID);
  controlChar = await service.getCharacteristic(CONTROL_CHAR_UUID);

  // Step 5: Subscribe to notifications
  await dataChar.startNotifications();
  dataChar.addEventListener('characteristicvaluechanged', handleNotification);

  // Step 6: Handle disconnection
  device.addEventListener('gattserverdisconnected', onDisconnected);

  console.log('Connected to GlucoseTransmitter!');
}
```

### 5.2 Handling Notifications

```javascript
function handleNotification(event) {
  const decoder = new TextDecoder('utf-8');
  const jsonString = decoder.decode(event.target.value);
  const message = JSON.parse(jsonString);

  switch (message.type) {
    case 'glucose_reading':
      handleLiveReading(message);
      break;

    case 'history_item':
      handleHistoryItem(message);
      break;

    case 'history_complete':
      handleHistoryComplete(message);
      break;

    default:
      console.warn('Unknown message type:', message.type);
  }
}
```

### 5.3 Requesting Initial History

```javascript
async function requestHistory() {
  const encoder = new TextEncoder();
  const command = JSON.stringify({ cmd: 'request_history' });
  await controlChar.writeValue(encoder.encode(command));
}
```

### 5.4 Collecting History & Detecting Missing Packets

```javascript
const historyBuffer = new Map(); // packet_index → reading
let expectedTransferId = null;
let expectedTotal = 0;

function handleHistoryItem(msg) {
  expectedTransferId = msg.transfer_id;
  expectedTotal = msg.total_packets;
  historyBuffer.set(msg.packet_index, msg.reading);
}

function handleHistoryComplete(msg) {
  if (msg.transfer_id !== expectedTransferId) return;

  // Check for missing packets
  const missing = [];
  for (let i = 0; i < msg.total_packets; i++) {
    if (!historyBuffer.has(i)) missing.push(i);
  }

  if (missing.length > 0) {
    // Request retransmission of missing packets
    missing.forEach(async (idx) => {
      const cmd = JSON.stringify({
        cmd: 'request_packet',
        transfer_id: msg.transfer_id,
        packet_index: idx
      });
      await controlChar.writeValue(new TextEncoder().encode(cmd));
    });
  } else {
    // All packets received — assemble chronological array
    const readings = [];
    for (let i = 0; i < msg.total_packets; i++) {
      readings.push(historyBuffer.get(i));
    }

    // Send ACK to phone
    acknowledgeTransfer(msg.transfer_id);

    // Forward to your existing GPFormer pipeline
    sendToBackend(readings);
  }
}

async function acknowledgeTransfer(transferId) {
  const cmd = JSON.stringify({
    cmd: 'history_ack',
    transfer_id: transferId,
    status: 'ok'
  });
  await controlChar.writeValue(new TextEncoder().encode(cmd));
}
```

### 5.5 Forwarding to FastAPI Backend

```javascript
async function sendToBackend(readings) {
  // Extract glucose values in chronological order (matches GPFormer SEQ_LEN=24)
  const glucoseValues = readings.map(r => r.glucose);
  const latestTimestamp = readings[readings.length - 1].timestamp;

  const response = await fetch('http://localhost:8000/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      readings: glucoseValues,
      latest_timestamp: latestTimestamp,
      experiment: 'gp_A'
    })
  });

  const prediction = await response.json();
  // Render prediction in your existing ForecastChart/ForecastTable components
}

function handleLiveReading(reading) {
  // Append to your sliding window of 24 readings
  // and re-run prediction
  addToSlidingWindow(reading);
  const latestWindow = getSlidingWindow(); // latest 24
  if (latestWindow.length === 24) {
    sendToBackend(latestWindow);
  }
}
```

### 5.6 Reconnection

```javascript
function onDisconnected() {
  console.log('GlucoseTransmitter disconnected. Attempting reconnect...');
  setTimeout(async () => {
    try {
      server = await device.gatt.connect();
      service = await server.getPrimaryService(SERVICE_UUID);
      dataChar = await service.getCharacteristic(DATA_CHAR_UUID);
      controlChar = await service.getCharacteristic(CONTROL_CHAR_UUID);
      await dataChar.startNotifications();
      dataChar.addEventListener('characteristicvaluechanged', handleNotification);
      console.log('Reconnected!');
    } catch (err) {
      console.error('Reconnection failed:', err);
    }
  }, 3000);
}
```

---

## 6. Build & Install Instructions

### Prerequisites
- **Android Studio** (Hedgehog 2023.1+ or later)
- **JDK 17** (Zulu or Adoptium recommended)
- **Android phone** with BLE Peripheral support (most phones from 2018+)
- **USB cable** or Wi-Fi debugging enabled

### Building
1. Open Android Studio.
2. Select **File → Open** and navigate to `diabetes/android/`.
3. Wait for Gradle sync to complete (it downloads dependencies automatically).
4. Connect your Android phone via USB with **USB Debugging** enabled.
5. Click **Run ▶** (or `Shift+F10`).

### Manual APK Build
```bash
cd diabetes/android
./gradlew assembleDebug
```
The APK will be at: `app/build/outputs/apk/debug/app-debug.apk`

### Installing via ADB
```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

---

## 7. Testing Phone-to-Laptop Communication

### Step 1: Start the Android App
1. Open **GlucoseTransmitter** on your phone.
2. Grant Bluetooth permissions when prompted.
3. Tap **Start Advertising**.
4. The BLE Status should show "Advertising ✓".

### Step 2: Connect from Laptop Chrome
1. Open Chrome on your laptop.
2. Navigate to your React frontend (or a test page with the Web Bluetooth code from Section 5).
3. Call `connectToTransmitter()` (e.g., via a "Connect BLE" button).
4. Chrome shows a device picker — select **GlucoseTransmitter**.
5. The phone's Connection Status should change to "Connected".

### Step 3: Send a Test Reading
1. On the phone, type a glucose value (e.g., `142`) and tap **Add Reading**.
2. The laptop should receive a notification with the glucose JSON.

### Step 4: Send Full History
1. On the phone, tap **Send Initial History**.
2. The laptop receives 24 `history_item` packets followed by a `history_complete` packet.
3. The laptop sends `history_ack` back.
4. Forward the 24 glucose values to your FastAPI `/predict` endpoint.

### Step 5: Live Predictions
1. Start simulation on the phone (set interval to 5 seconds).
2. Each generated reading is automatically sent to the laptop.
3. Your React frontend maintains a sliding 24-reading window and re-runs predictions.

---

## 8. Important Notes

- **Web Bluetooth requires HTTPS** (or `localhost`). Your React dev server at `localhost:5173` works fine.
- **Chrome only**: Web Bluetooth is supported in Chrome/Edge, not Firefox/Safari.
- **BLE MTU**: Default BLE MTU is 20 bytes for the payload, but modern devices negotiate higher MTUs automatically. The JSON messages are typically 150-200 bytes. Android and Chrome handle MTU negotiation transparently.
- **Simulated readings** are always flagged with `"source": "simulated"` — they are not real CGM data.
- The phone does **not** need internet connectivity. BLE is a direct radio link.
