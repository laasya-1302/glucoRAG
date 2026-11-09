/**
 * Web Bluetooth Client for GPFormer GlucoseTransmitter
 *
 * Implements Web Bluetooth API to connect directly to the Android BLE peripheral,
 * listen for live glucose readings, handle 24-reading initial history transfers,
 * and send control commands (history requests, transfer ACKs).
 */

export const BLE_CONSTANTS = {
  // GPFormer Custom 128-bit Service and Characteristic UUIDs (lowercase for Web Bluetooth API)
  SERVICE_UUID: "1337beef-4750-466f-726d-657242470001".toLowerCase(),
  CHARACTERISTIC_DATA_UUID: "1337beef-4750-466f-726d-657242470002".toLowerCase(),
  CHARACTERISTIC_CONTROL_UUID: "1337beef-4750-466f-726d-657242470003".toLowerCase(),
  DEVICE_NAME: "GlucoseTransmitter",
};

export class BleClient {
  constructor() {
    this.device = null;
    this.server = null;
    this.service = null;
    this.dataChar = null;
    this.controlChar = null;

    this.onStatusChange = null;
    this.onReading = null;
    this.onHistoryProgress = null;
    this.onHistoryComplete = null;
    this.onError = null;

    // Buffer to reassemble history transfer items
    this.historyBuffer = new Map();
    this.activeTransferId = null;
    this.activeTotalPackets = 0;

    this.handleNotification = this.handleNotification.bind(this);
    this.handleDisconnected = this.handleDisconnected.bind(this);
  }

  /**
   * Checks whether Web Bluetooth API is supported in the current browser.
   */
  static isSupported() {
    return typeof navigator !== 'undefined' && 'bluetooth' in navigator;
  }

  /**
   * Prompts the user to select the GlucoseTransmitter device and connects GATT.
   */
  async connect() {
    if (!BleClient.isSupported()) {
      throw new Error(
        "Web Bluetooth is not supported in this browser. Please use Google Chrome or Microsoft Edge on desktop with HTTPS or localhost."
      );
    }

    this._updateStatus({ state: 'connecting', deviceName: null });

    try {
      // Request device with service filter and optionalServices so we can access characteristics
      this.device = await navigator.bluetooth.requestDevice({
        filters: [
          { name: BLE_CONSTANTS.DEVICE_NAME },
          { services: [BLE_CONSTANTS.SERVICE_UUID] }
        ],
        optionalServices: [BLE_CONSTANTS.SERVICE_UUID]
      });

      this.device.addEventListener('gattserverdisconnected', this.handleDisconnected);

      const deviceName = this.device.name || BLE_CONSTANTS.DEVICE_NAME;
      this._updateStatus({ state: 'connecting', deviceName });

      // Connect GATT Server
      this.server = await this.device.gatt.connect();

      // Discover Primary Glucose Service
      this.service = await this.server.getPrimaryService(BLE_CONSTANTS.SERVICE_UUID);

      // Discover Data Characteristic (NOTIFY | READ)
      this.dataChar = await this.service.getCharacteristic(BLE_CONSTANTS.CHARACTERISTIC_DATA_UUID);

      // Discover Control Characteristic (WRITE)
      this.controlChar = await this.service.getCharacteristic(BLE_CONSTANTS.CHARACTERISTIC_CONTROL_UUID);

      // Subscribe to Notifications
      await this.dataChar.startNotifications();
      this.dataChar.addEventListener('characteristicvaluechanged', this.handleNotification);

      this._updateStatus({
        state: 'connected',
        deviceName: deviceName
      });

      return {
        success: true,
        deviceName: deviceName
      };
    } catch (err) {
      this.disconnect();
      const message = err.name === 'NotFoundError' 
        ? "Bluetooth device selection was cancelled." 
        : err.message || "Failed to connect to Bluetooth device.";
      
      this._updateStatus({ state: 'disconnected', deviceName: null, error: message });
      throw new Error(message);
    }
  }

  /**
   * Disconnects active BLE GATT session and cleans up listeners.
   */
  disconnect() {
    try {
      if (this.dataChar) {
        this.dataChar.removeEventListener('characteristicvaluechanged', this.handleNotification);
        if (this.device?.gatt?.connected) {
          this.dataChar.stopNotifications().catch(() => {});
        }
      }
    } catch (e) {
      // Ignore cleanup error
    }

    if (this.device) {
      this.device.removeEventListener('gattserverdisconnected', this.handleDisconnected);
      if (this.device.gatt && this.device.gatt.connected) {
        this.device.gatt.disconnect();
      }
    }

    this.device = null;
    this.server = null;
    this.service = null;
    this.dataChar = null;
    this.controlChar = null;
    this.historyBuffer.clear();
    this.activeTransferId = null;

    this._updateStatus({ state: 'disconnected', deviceName: null });
  }

  /**
   * Requests the phone to stream its 24 initial readings.
   */
  async requestHistory() {
    if (!this.controlChar) {
      throw new Error("Cannot request history: Bluetooth is not connected.");
    }

    const command = JSON.stringify({
      cmd: "request_history",
      request_id: `req_${Date.now()}`
    });

    const payload = new TextEncoder().encode(command);
    await this.controlChar.writeValue(payload);
  }

  /**
   * Sends an acknowledgement back to the phone for a completed transfer.
   */
  async sendHistoryAck(transferId, status = "ok") {
    if (!this.controlChar) return;
    try {
      const ack = JSON.stringify({
        cmd: "history_ack",
        transfer_id: transferId,
        status: status
      });
      const payload = new TextEncoder().encode(ack);
      await this.controlChar.writeValue(payload);
    } catch (e) {
      console.warn("Failed to send history ACK over BLE:", e);
    }
  }

  /**
   * Internal handler for incoming BLE notifications.
   */
  handleNotification(event) {
    const value = event.target.value;
    if (!value || value.byteLength === 0) return;

    try {
      const text = new TextDecoder('utf-8').decode(value);
      const data = JSON.parse(text);

      switch (data.type) {
        case 'glucose_reading':
          // Single live reading (manual or simulated)
          if (this.onReading) {
            this.onReading(data);
          }
          break;

        case 'history_item':
          // One of the 24 history packets
          this._handleHistoryItem(data);
          break;

        case 'history_complete':
          // Batch transfer complete
          this._handleHistoryComplete(data);
          break;

        default:
          console.debug("Received unhandled BLE message type:", data.type, data);
      }
    } catch (err) {
      console.warn("Failed to parse BLE notification packet:", err);
    }
  }

  _handleHistoryItem(item) {
    const { transfer_id, packet_index, total_packets, reading } = item;
    if (!transfer_id || reading == null) return;

    // Reset buffer if this is a new transfer ID
    if (this.activeTransferId !== transfer_id) {
      this.activeTransferId = transfer_id;
      this.activeTotalPackets = total_packets || 24;
      this.historyBuffer.clear();
    }

    this.historyBuffer.set(packet_index, reading);

    if (this.onHistoryProgress) {
      this.onHistoryProgress({
        received: this.historyBuffer.size,
        total: this.activeTotalPackets,
        transferId: transfer_id,
        latestReading: reading
      });
    }

    // If all packets have arrived, trigger completion
    if (this.historyBuffer.size >= this.activeTotalPackets) {
      this._finalizeHistoryTransfer(transfer_id);
    }
  }

  _handleHistoryComplete(data) {
    const { transfer_id } = data;
    this._finalizeHistoryTransfer(transfer_id);
  }

  _finalizeHistoryTransfer(transferId) {
    if (this.historyBuffer.size === 0) return;

    // Reconstruct ordered readings array by packet index
    const sortedIndices = Array.from(this.historyBuffer.keys()).sort((a, b) => a - b);
    const readings = sortedIndices.map(idx => this.historyBuffer.get(idx));

    // Acknowledge back to the phone
    this.sendHistoryAck(transferId, "ok");

    if (this.onHistoryComplete) {
      this.onHistoryComplete({
        transferId,
        readings,
        count: readings.length
      });
    }

    // Clear buffer after dispatch
    this.historyBuffer.clear();
    this.activeTransferId = null;
  }

  handleDisconnected() {
    this._updateStatus({
      state: 'disconnected',
      deviceName: null,
      error: "Device disconnected."
    });
  }

  _updateStatus(status) {
    if (this.onStatusChange) {
      this.onStatusChange(status);
    }
  }
}

export const bleClient = new BleClient();
