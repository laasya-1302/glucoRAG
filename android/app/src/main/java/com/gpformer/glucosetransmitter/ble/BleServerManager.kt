package com.gpformer.glucosetransmitter.ble

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.BluetoothLeAdvertiser
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.ParcelUuid
import android.util.Log
import com.gpformer.glucosetransmitter.model.BleMessage
import com.gpformer.glucosetransmitter.model.ClientCommand
import com.gpformer.glucosetransmitter.model.GlucoseReading
import com.gpformer.glucosetransmitter.model.HistoryCompleteMessage
import com.gpformer.glucosetransmitter.model.HistoryItemMessage
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap

/**
 * Manages the Bluetooth Low Energy (BLE) GATT Server and Advertising Peripheral.
 *
 * Responsibilities:
 * - Verifies device BLE hardware support (Multiple Advertisement / Peripheral mode).
 * - Hosts custom GATT Service and Characteristics (Glucose Data Notify & Control Write).
 * - Advertises presence to laptop Chrome browser (Web Bluetooth).
 * - Transmits live individual readings via notifications.
 * - Streams reliable multi-packet 24-history transfers.
 * - Processes incoming client control commands and acknowledgements.
 */
class BleServerManager(
    private val context: Context,
    private val onClientCommand: (ClientCommand) -> Unit
) {
    private val tag = "BleServerManager"

    private val bluetoothManager: BluetoothManager? =
        context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    private val bluetoothAdapter: BluetoothAdapter? = bluetoothManager?.adapter

    private var advertiser: BluetoothLeAdvertiser? = null
    private var gattServer: BluetoothGattServer? = null
    private var dataCharacteristic: BluetoothGattCharacteristic? = null
    private var controlCharacteristic: BluetoothGattCharacteristic? = null

    // Track connected client devices (thread-safe set)
    private val connectedDevices = ConcurrentHashMap.newKeySet<BluetoothDevice>()

    // Track devices that have enabled CCCD notifications
    private val subscribedDevices = ConcurrentHashMap.newKeySet<BluetoothDevice>()

    // GATT service registration state
    @Volatile
    private var isServiceAdded = false

    // Cached latest data characteristic bytes for direct READ requests
    @Volatile
    private var latestDataBytes: ByteArray = ByteArray(0)

    // Coroutine scope for asynchronous history transmissions
    private val transferScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var activeTransferJob: Job? = null

    // Reactive State Flows
    private val _advertisingState = MutableStateFlow<AdvertisingStatus>(AdvertisingStatus.Stopped)
    val advertisingState: StateFlow<AdvertisingStatus> = _advertisingState.asStateFlow()

    private val _connectionState = MutableStateFlow<ConnectionStatus>(ConnectionStatus.Disconnected)
    val connectionState: StateFlow<ConnectionStatus> = _connectionState.asStateFlow()

    private val _hardwareSupported = MutableStateFlow(true)
    val hardwareSupported: StateFlow<Boolean> = _hardwareSupported.asStateFlow()

    private val _lastAckStatus = MutableStateFlow<String?>(null)
    val lastAckStatus: StateFlow<String?> = _lastAckStatus.asStateFlow()

    sealed class AdvertisingStatus {
        object Stopped : AdvertisingStatus()
        object Advertising : AdvertisingStatus()
        data class Error(val message: String) : AdvertisingStatus()
    }

    sealed class ConnectionStatus {
        object Disconnected : ConnectionStatus()
        data class Connected(val deviceIdentifier: String) : ConnectionStatus()
    }

    init {
        checkHardwareCapabilities()
    }

    /**
     * Checks whether the device hardware supports BLE peripheral and advertisement capabilities.
     */
    fun checkHardwareCapabilities(): Boolean {
        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)) {
            Log.e(tag, "BLE is not supported on this device hardware.")
            _hardwareSupported.value = false
            return false
        }
        if (bluetoothAdapter == null) {
            Log.e(tag, "BluetoothAdapter is null on this device.")
            _hardwareSupported.value = false
            return false
        }
        val isLePeripheralSupported = bluetoothAdapter.isMultipleAdvertisementSupported ||
                bluetoothAdapter.bluetoothLeAdvertiser != null
        _hardwareSupported.value = isLePeripheralSupported
        if (!isLePeripheralSupported) {
            Log.e(tag, "BLE Multiple Advertisement (Peripheral Mode) is not supported.")
        }
        return isLePeripheralSupported
    }

    /**
     * Initializes and opens the GATT Server hosting the GPFormer Glucose Service.
     */
    @SuppressLint("MissingPermission")
    fun startGattServer(): Boolean {
        if (gattServer != null) return true
        if (bluetoothManager == null) return false

        try {
            gattServer = bluetoothManager.openGattServer(context, gattServerCallback)
            if (gattServer == null) {
                Log.e(tag, "Failed to open GATT Server.")
                return false
            }

            // Create primary service
            val service = BluetoothGattService(
                BleConstants.SERVICE_UUID,
                BluetoothGattService.SERVICE_TYPE_PRIMARY
            )

            // Characteristic 1: Glucose Data (NOTIFY | READ)
            val dataChar = BluetoothGattCharacteristic(
                BleConstants.CHARACTERISTIC_GLUCOSE_DATA_UUID,
                BluetoothGattCharacteristic.PROPERTY_NOTIFY or BluetoothGattCharacteristic.PROPERTY_READ,
                BluetoothGattCharacteristic.PERMISSION_READ
            )

            // Add standard Client Characteristic Configuration Descriptor (CCCD) for notification subscriptions
            val cccdDescriptor = BluetoothGattDescriptor(
                BleConstants.CCCD_UUID,
                BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE
            )
            cccdDescriptor.value = BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
            dataChar.addDescriptor(cccdDescriptor)

            // Characteristic 2: Control & Acknowledge (WRITE | WRITE_NO_RESPONSE)
            val controlChar = BluetoothGattCharacteristic(
                BleConstants.CHARACTERISTIC_CONTROL_UUID,
                BluetoothGattCharacteristic.PROPERTY_WRITE or BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
                BluetoothGattCharacteristic.PERMISSION_WRITE
            )

            service.addCharacteristic(dataChar)
            service.addCharacteristic(controlChar)

            val added = gattServer?.addService(service) ?: false
            if (added) {
                dataCharacteristic = dataChar
                controlCharacteristic = controlChar
                Log.i(tag, "GATT Server configured and service added successfully.")
            } else {
                Log.e(tag, "Failed to add service to GATT Server.")
            }
            return added
        } catch (e: SecurityException) {
            Log.e(tag, "SecurityException while opening GATT Server: ${e.message}")
            return false
        }
    }

    /**
     * Starts advertising the BLE Peripheral so Chrome Web Bluetooth can discover and connect to it.
     */
    @SuppressLint("MissingPermission")
    fun startAdvertising() {
        if (!checkHardwareCapabilities()) {
            _advertisingState.value = AdvertisingStatus.Error("BLE Peripheral mode unsupported by hardware.")
            return
        }

        if (bluetoothAdapter?.isEnabled != true) {
            _advertisingState.value = AdvertisingStatus.Error("Bluetooth is currently turned OFF. Please enable it.")
            return
        }

        val serverStarted = startGattServer()
        if (!serverStarted) {
            _advertisingState.value = AdvertisingStatus.Error("Failed to initialize GATT server.")
            return
        }

        advertiser = bluetoothAdapter.bluetoothLeAdvertiser
        if (advertiser == null) {
            _advertisingState.value = AdvertisingStatus.Error("Bluetooth LE Advertiser unavailable.")
            return
        }

        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .setTimeout(0) // Advertise indefinitely until explicitly stopped
            .build()

//        val data = AdvertiseData.Builder()
//            .setIncludeDeviceName(true)
//            .addServiceUuid(ParcelUuid(BleConstants.SERVICE_UUID))
//            .build()
        val data = AdvertiseData.Builder()
            .setIncludeDeviceName(false)
            .addServiceUuid(ParcelUuid(BleConstants.SERVICE_UUID))
            .build()

        try {
            advertiser?.startAdvertising(settings, data, advertiseCallback)
        } catch (e: SecurityException) {
            Log.e(tag, "Missing BLUETOOTH_ADVERTISE permission: ${e.message}")
            _advertisingState.value = AdvertisingStatus.Error("Missing Bluetooth Advertise permission.")
        }
    }

    /**
     * Stops BLE advertising.
     */
    @SuppressLint("MissingPermission")
    fun stopAdvertising() {
        try {
            advertiser?.stopAdvertising(advertiseCallback)
        } catch (e: SecurityException) {
            Log.e(tag, "Error stopping advertising: ${e.message}")
        }
        _advertisingState.value = AdvertisingStatus.Stopped
    }

    /**
     * Notifies connected Web Bluetooth client of a newly recorded single glucose reading.
     */
    fun notifyReading(reading: GlucoseReading) {
        val payload = reading.toJsonString()
        dispatchNotification(payload)
    }

    /**
     * Executes reliable initial 24-reading transfer.
     * Dispatches packets sequentially with pacing to avoid BLE GATT queue drops.
     */
    fun sendInitialHistory(
        readings: List<GlucoseReading>,
        onProgress: (sent: Int, total: Int) -> Unit,
        onComplete: (transferId: String) -> Unit
    ) {
        activeTransferJob?.cancel()
        activeTransferJob = transferScope.launch {
            val transferId = "tx_${System.currentTimeMillis()}"
            val total = readings.size

            for (index in readings.indices) {
                if (!isActive) break
                val packet = HistoryItemMessage(
                    transferId = transferId,
                    packetIndex = index,
                    totalPackets = total,
                    reading = readings[index]
                )
                dispatchNotification(packet.toJsonString())
                withContext(Dispatchers.Main) {
                    onProgress(index + 1, total)
                }
                delay(BleConstants.HISTORY_PACKET_PACING_MS)
            }

            if (isActive) {
                // Send completion sentinel packet
                val completePacket = HistoryCompleteMessage(
                    transferId = transferId,
                    totalPackets = total
                )
                dispatchNotification(completePacket.toJsonString())
                withContext(Dispatchers.Main) {
                    onComplete(transferId)
                }
            }
        }
    }

    /**
     * Resends a single packet during history synchronization with its original transferId and packetIndex.
     */
    fun resendSinglePacket(
        transferId: String,
        packetIndex: Int,
        totalPackets: Int,
        reading: GlucoseReading
    ) {
        val packet = HistoryItemMessage(
            transferId = transferId,
            packetIndex = packetIndex,
            totalPackets = totalPackets,
            reading = reading
        )
        dispatchNotification(packet.toJsonString())
    }

    /**
     * Sends a raw UTF-8 string payload via GATT notification to all connected clients.
     */
    @SuppressLint("MissingPermission")
    private fun dispatchNotification(payload: String) {
        val characteristic = dataCharacteristic ?: return
        val server = gattServer ?: return
        if (connectedDevices.isEmpty()) return

        val bytes = payload.toByteArray(StandardCharsets.UTF_8)
        latestDataBytes = bytes

        for (device in connectedDevices) {
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    characteristic.value = bytes
                    val status = server.notifyCharacteristicChanged(device, characteristic, false, bytes)
                    Log.d(tag, "notifyCharacteristicChanged (Tiramisu+) returned $status for ${device.address}")
                } else {
                    @Suppress("DEPRECATION")
                    characteristic.value = bytes
                    @Suppress("DEPRECATION")
                    val status = server.notifyCharacteristicChanged(device, characteristic, false)
                    Log.d(tag, "notifyCharacteristicChanged (<Tiramisu) returned $status for ${device.address}")
                }
            } catch (e: SecurityException) {
                Log.e(tag, "SecurityException during notification dispatch: ${e.message}")
            } catch (e: Exception) {
                Log.e(tag, "Error sending notification to ${device.address}: ${e.message}")
            }
        }
    }

    // --- BLE Callbacks ---

    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
            Log.i(tag, "BLE Advertising started successfully.")
            _advertisingState.value = AdvertisingStatus.Advertising
        }

        override fun onStartFailure(errorCode: Int) {
            val msg = when (errorCode) {
                ADVERTISE_FAILED_ALREADY_STARTED -> "Already started"
                ADVERTISE_FAILED_DATA_TOO_LARGE -> "Data too large"
                ADVERTISE_FAILED_FEATURE_UNSUPPORTED -> "Peripheral mode unsupported"
                ADVERTISE_FAILED_INTERNAL_ERROR -> "Internal error"
                ADVERTISE_FAILED_TOO_MANY_ADVERTISERS -> "Too many advertisers"
                else -> "Error code $errorCode"
            }
            Log.e(tag, "BLE Advertising failed: $msg")
            _advertisingState.value = AdvertisingStatus.Error(msg)
        }
    }

    private val gattServerCallback = object : BluetoothGattServerCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
            Log.i(tag, "GATT connection state changed for ${device.address}: status=$status, newState=$newState")
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                connectedDevices.add(device)
                val identifier = try {
                    device.name ?: device.address
                } catch (e: SecurityException) {
                    device.address
                }
                _connectionState.value = ConnectionStatus.Connected(identifier)
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connectedDevices.remove(device)
                subscribedDevices.remove(device)
                if (connectedDevices.isEmpty()) {
                    _connectionState.value = ConnectionStatus.Disconnected
                } else {
                    val remaining = connectedDevices.first()
                    _connectionState.value = ConnectionStatus.Connected(remaining.address)
                }
            }
        }

        override fun onServiceAdded(status: Int, service: BluetoothGattService?) {
            isServiceAdded = (status == BluetoothGatt.GATT_SUCCESS)
            Log.i(tag, "GATT onServiceAdded: status=$status, success=$isServiceAdded")
        }

        override fun onMtuChanged(device: BluetoothDevice?, mtu: Int) {
            Log.i(tag, "BLE MTU negotiated to $mtu for device ${device?.address}")
        }

        @SuppressLint("MissingPermission")
        override fun onCharacteristicReadRequest(
            device: BluetoothDevice,
            requestId: Int,
            offset: Int,
            characteristic: BluetoothGattCharacteristic
        ) {
            if (characteristic.uuid == BleConstants.CHARACTERISTIC_GLUCOSE_DATA_UUID) {
                val value = if (latestDataBytes.isNotEmpty()) latestDataBytes else (characteristic.value ?: ByteArray(0))
                val responseData = if (offset < value.size) {
                    value.copyOfRange(offset, value.size)
                } else {
                    ByteArray(0)
                }
                gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, responseData)
            } else {
                gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_FAILURE, 0, null)
            }
        }

        @SuppressLint("MissingPermission")
        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice,
            requestId: Int,
            characteristic: BluetoothGattCharacteristic,
            preparedWrite: Boolean,
            responseNeeded: Boolean,
            offset: Int,
            value: ByteArray?
        ) {
            if (characteristic.uuid == BleConstants.CHARACTERISTIC_CONTROL_UUID && value != null) {
                val commandString = String(value, StandardCharsets.UTF_8)
                Log.i(tag, "Received client command on Control Characteristic: $commandString")
                val command = ClientCommand.parse(commandString)

                if (command is ClientCommand.AcknowledgeTransfer) {
                    _lastAckStatus.value = "Verified (Transfer ID: ${command.transferId}, status: ${command.status})"
                }

                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
                }

                onClientCommand(command)
            } else {
                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_FAILURE, 0, null)
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onDescriptorReadRequest(
            device: BluetoothDevice,
            requestId: Int,
            offset: Int,
            descriptor: BluetoothGattDescriptor
        ) {
            val value = descriptor.value ?: ByteArray(0)
            gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
        }

        @SuppressLint("MissingPermission")
        override fun onDescriptorWriteRequest(
            device: BluetoothDevice,
            requestId: Int,
            descriptor: BluetoothGattDescriptor,
            preparedWrite: Boolean,
            responseNeeded: Boolean,
            offset: Int,
            value: ByteArray?
        ) {
            if (descriptor.uuid == BleConstants.CCCD_UUID && value != null) {
                descriptor.value = value
                val notificationsEnabled = value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                if (notificationsEnabled) {
                    subscribedDevices.add(device)
                } else {
                    subscribedDevices.remove(device)
                }
                Log.i(tag, "Client notifications changed for ${device.address}: enabled=$notificationsEnabled (subscribed: ${subscribedDevices.size})")
                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
                }
            } else {
                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_FAILURE, 0, null)
                }
            }
        }
    }

    /**
     * Shuts down GATT server, cancels active jobs, and releases BLE resources.
     */
    @SuppressLint("MissingPermission")
    fun close() {
        stopAdvertising()
        activeTransferJob?.cancel()
        transferScope.cancel()
        try {
            gattServer?.close()
        } catch (e: Exception) {
            Log.e(tag, "Error closing GATT server: ${e.message}")
        }
        gattServer = null
        connectedDevices.clear()
        subscribedDevices.clear()
        isServiceAdded = false
        _connectionState.value = ConnectionStatus.Disconnected
    }
}
