package com.gpformer.glucosetransmitter.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.gpformer.glucosetransmitter.ble.BleServerManager
import com.gpformer.glucosetransmitter.data.GlucoseRepository
import com.gpformer.glucosetransmitter.model.ClientCommand
import com.gpformer.glucosetransmitter.model.GlucoseReading
import com.gpformer.glucosetransmitter.network.BackendApiClient
import com.gpformer.glucosetransmitter.network.PredictionResult
import com.gpformer.glucosetransmitter.notification.GlucoseNotificationManager
import com.gpformer.glucosetransmitter.simulation.GlucoseSimulator
import com.gpformer.glucosetransmitter.util.GlucoseTrendCalculator
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * ViewModel orchestrating data repository, simulation engine, BLE communications,
 * backend prediction pipeline, and smartwatch notification delivery.
 * Holds presentation state and survives configuration changes.
 */
class MainViewModel(application: Application) : AndroidViewModel(application) {

    val repository = GlucoseRepository(application)
    val notificationManager = GlucoseNotificationManager(application)
    val apiClient = BackendApiClient(application)

    private val _transferStatus = MutableStateFlow<String?>(null)
    val transferStatus: StateFlow<String?> = _transferStatus.asStateFlow()

    private val _userFeedback = MutableStateFlow<String?>(null)
    val userFeedback: StateFlow<String?> = _userFeedback.asStateFlow()

    // GPFormer Prediction & Alert State
    private val _predictionResult = MutableStateFlow<PredictionResult?>(null)
    val predictionResult: StateFlow<PredictionResult?> = _predictionResult.asStateFlow()

    private val _isPredicting = MutableStateFlow(false)
    val isPredicting: StateFlow<Boolean> = _isPredicting.asStateFlow()

    private val _alertStatusText = MutableStateFlow("Alerts ready")
    val alertStatusText: StateFlow<String> = _alertStatusText.asStateFlow()

    // Initialize BLE Server Manager
    val bleManager = BleServerManager(application) { command ->
        handleClientCommand(command)
    }

    // Initialize Simulator
    val simulator = GlucoseSimulator(repository) { newReading ->
        // 1. Immediately transmit via BLE notification to connected website
        bleManager.notifyReading(newReading)
        // 2. Process real-time prediction and smartwatch alert pipeline
        processGlucosePipeline(repository.getChronologicalHistory())
    }

    val readings: StateFlow<List<GlucoseReading>> = repository.readings
    val isSimulating: StateFlow<Boolean> = simulator.isSimulating
    val simulationInterval: StateFlow<Int> = simulator.intervalSeconds
    val advertisingState: StateFlow<BleServerManager.AdvertisingStatus> = bleManager.advertisingState
    val connectionState: StateFlow<BleServerManager.ConnectionStatus> = bleManager.connectionState
    val hardwareSupported: StateFlow<Boolean> = bleManager.hardwareSupported
    val lastAckStatus: StateFlow<String?> = bleManager.lastAckStatus

    /**
     * Validates and records a manual blood glucose entry from the user.
     * Automatically notifies the connected BLE central and triggers the prediction alert pipeline.
     */
    fun addManualReading(inputString: String): Boolean {
        val trimmed = inputString.trim()
        if (trimmed.isEmpty()) {
            _userFeedback.value = "Please enter a glucose value."
            return false
        }

        val parsedValue = trimmed.toDoubleOrNull()
        if (parsedValue == null) {
            _userFeedback.value = "Invalid number format."
            return false
        }

        if (!GlucoseReading.isValidGlucose(parsedValue)) {
            _userFeedback.value = "Value must be between ${GlucoseReading.MIN_PHYSIOLOGICAL_GLUCOSE.toInt()} and ${GlucoseReading.MAX_PHYSIOLOGICAL_GLUCOSE.toInt()} mg/dL."
            return false
        }

        val seq = repository.nextSequence()
        val reading = GlucoseReading.create(
            sequence = seq,
            glucose = parsedValue,
            source = GlucoseReading.SOURCE_MANUAL
        )

        repository.addReading(reading)
        bleManager.notifyReading(reading)
        _userFeedback.value = "Added manual reading #${reading.sequence}: ${reading.glucose} mg/dL"

        // Trigger real-time prediction and alert check
        processGlucosePipeline(repository.getChronologicalHistory())
        return true
    }

    /**
     * Processes real-time glucose prediction and triggers smartwatch alerts:
     * 1. Evaluates immediate measured hypoglycemia (< 70 mg/dL).
     * 2. If 24 readings are available, calls GPFormer backend inference.
     * 3. Evaluates predicted hypo/hyper risk and dispatches smartwatch notifications.
     */
    fun processGlucosePipeline(history: List<GlucoseReading>) {
        if (history.isEmpty()) return

        val latest = history.last()
        val trend = GlucoseTrendCalculator.calculateTrend(history)

        // Step 1: Immediate measured critical low check (< 70 mg/dL)
        if (latest.glucose < GlucoseReading.HYPO_THRESHOLD) {
            val fired = notificationManager.showImmediateLowAlert(latest.glucose, trend)
            if (fired) {
                _alertStatusText.value = "CRITICAL: Immediate low alert sent to smartwatch (${latest.glucose} mg/dL)"
            }
        }

        // Step 2: Predictive model inference if 24 readings are available
        if (history.size >= GlucoseRepository.MAX_HISTORY_CAPACITY) {
            runPredictionInference(history)
        } else {
            _alertStatusText.value = "Need 24 readings for prediction (${history.size}/24 available)"
        }
    }

    /**
     * Calls the FastAPI backend to compute future predictions and evaluates risk alerts.
     */
    fun runPredictionInference(history: List<GlucoseReading> = repository.getChronologicalHistory()) {
        if (history.size < GlucoseRepository.MAX_HISTORY_CAPACITY) {
            _userFeedback.value = "Requires exactly 24 readings. Currently have ${history.size}."
            return
        }

        // Clear cooldown on explicit manual prediction requests so watch vibrates immediately
        notificationManager.clearCooldown()

        viewModelScope.launch {
            _isPredicting.value = true
            val result = apiClient.predict(history)

            result.onSuccess { pred ->
                _predictionResult.value = pred
                evaluatePredictionAlerts(pred)
            }.onFailure { err ->
                _predictionResult.value = null
                _alertStatusText.value = "Inference error: ${err.message}"
                _userFeedback.value = "Connection error: ${err.message}. Please check that backend URL is http://192.168.1.2:8000"
            }

            _isPredicting.value = false
        }
    }

    /**
     * Evaluates prediction results against clinical risk thresholds and triggers notifications.
     */
    private fun evaluatePredictionAlerts(pred: PredictionResult) {
        val isHypo = pred.clinicalAlertStatus == "HYPO_RISK" ||
                pred.forecast30m < GlucoseReading.HYPO_THRESHOLD ||
                pred.hypoProbability >= 0.40

        val isHyper = pred.clinicalAlertStatus == "HYPER_RISK" ||
                pred.forecast30m > GlucoseReading.HYPER_THRESHOLD ||
                pred.hyperProbability >= 0.50

        when {
            isHypo -> {
                val fired = notificationManager.showHypoAlert(
                    currentGlucose = pred.currentGlucose,
                    trend = pred.trend,
                    predicted30m = pred.forecast30m,
                    hypoProbPct = pred.hypoProbPct
                )
                _alertStatusText.value = if (fired) {
                    "ALERT: Low glucose risk sent to watch (+30m: ${pred.forecast30m} mg/dL)"
                } else {
                    "Low risk detected (cooldown active - notification throttled)"
                }
            }
            isHyper -> {
                val fired = notificationManager.showHyperAlert(
                    currentGlucose = pred.currentGlucose,
                    trend = pred.trend,
                    predicted30m = pred.forecast30m,
                    hyperProbPct = pred.hyperProbPct
                )
                _alertStatusText.value = if (fired) {
                    "ALERT: High glucose risk sent to watch (+30m: ${pred.forecast30m} mg/dL)"
                } else {
                    "High risk detected (cooldown active - notification throttled)"
                }
            }
            else -> {
                _alertStatusText.value = "Glucose normal (+30m: ${pred.forecast30m} mg/dL, ${pred.trend.displayText}) — Safe range (no watch alarm needed)"
                _userFeedback.value = "Prediction: ${pred.forecast30m} mg/dL (Normal). Smartwatch alert triggers when < 70 or > 180 mg/dL."
            }
        }
    }

    // ── Smartwatch Manual Test Triggers ──

    /**
     * Sends a direct test notification with vibration to confirm smartwatch mirroring works.
     */
    fun sendSmartwatchTestNotification(): Boolean {
        val success = notificationManager.showTestAlert()
        _userFeedback.value = "Smartwatch test notification sent ✓ (Check watch display and vibration)"
        return success
    }

    /**
     * Sends a simulated Hypo Alert notification to inspect formatting on the watch.
     */
    fun sendTestHypoAlert(): Boolean {
        notificationManager.clearCooldown()
        val success = notificationManager.showHypoAlert(
            currentGlucose = 68.0,
            trend = GlucoseTrendCalculator.Trend.FALLING,
            predicted30m = 54.0,
            hypoProbPct = 92
        )
        _userFeedback.value = "Simulated Hypo Alert sent to smartwatch ✓"
        return success
    }

    /**
     * Sends a simulated Hyper Alert notification to inspect formatting on the watch.
     */
    fun sendTestHyperAlert(): Boolean {
        notificationManager.clearCooldown()
        val success = notificationManager.showHyperAlert(
            currentGlucose = 210.0,
            trend = GlucoseTrendCalculator.Trend.RISING,
            predicted30m = 245.0,
            hyperProbPct = 88
        )
        _userFeedback.value = "Simulated Hyper Alert sent to smartwatch ✓"
        return success
    }

    fun getBackendUrl(): String = apiClient.baseUrl

    fun setBackendUrl(url: String) {
        apiClient.baseUrl = url
        _userFeedback.value = "Backend URL saved: ${apiClient.baseUrl}"
    }

    /**
     * Starts automatic synthetic glucose generation.
     */
    fun startSimulation() {
        simulator.startSimulation()
        _userFeedback.value = "Simulation started (${simulator.intervalSeconds.value}s interval)"
    }

    /**
     * Stops automatic synthetic glucose generation.
     */
    fun stopSimulation() {
        simulator.stopSimulation()
        _userFeedback.value = "Simulation stopped"
    }

    fun setSimulationInterval(seconds: Int) {
        simulator.setIntervalSeconds(seconds)
    }

    fun startAdvertising() {
        bleManager.startAdvertising()
    }

    fun stopAdvertising() {
        bleManager.stopAdvertising()
    }

    /**
     * Sends the latest 24 readings across BLE to the laptop central.
     */
    fun sendInitialHistory() {
        val history = repository.getChronologicalHistory()
        if (history.isEmpty()) {
            _userFeedback.value = "No readings to send. Add readings or generate seed history."
            return
        }

        _transferStatus.value = "Initiating transfer (0/${history.size})..."
        bleManager.sendInitialHistory(
            readings = history,
            onProgress = { sent, total ->
                _transferStatus.value = "Transmitting packet $sent / $total..."
            },
            onComplete = { txId ->
                _transferStatus.value = "All ${history.size} packets sent (Transfer ID: $txId)"
                _userFeedback.value = "History transfer finished ($txId)"
            }
        )
    }

    /**
     * Pre-fills 24 realistic seed readings spaced 15 minutes apart and evaluates prediction.
     */
    fun seed24Readings() {
        repository.seedInitialHistory()
        _userFeedback.value = "Seeded 24 realistic chronological readings"
        processGlucosePipeline(repository.getChronologicalHistory())
    }

    /**
     * Seeds 24 readings declining into hypoglycemia (~52 mg/dL) and runs prediction.
     */
    fun seedHypoReadings() {
        notificationManager.clearCooldown()
        repository.seedHypoHistory()
        _userFeedback.value = "Seeded 24 Hypo readings (ending at 52 mg/dL)"
        processGlucosePipeline(repository.getChronologicalHistory())
    }

    /**
     * Seeds 24 readings rising into hyperglycemia (~240 mg/dL) and runs prediction.
     */
    fun seedHyperReadings() {
        notificationManager.clearCooldown()
        repository.seedHyperHistory()
        _userFeedback.value = "Seeded 24 Hyper readings (ending at 240 mg/dL)"
        processGlucosePipeline(repository.getChronologicalHistory())
    }

    fun clearHistory() {
        repository.clearHistory()
        _predictionResult.value = null
        _alertStatusText.value = "History cleared"
        _userFeedback.value = "Reading history cleared"
    }

    fun clearFeedback() {
        _userFeedback.value = null
    }

    /**
     * Handles commands initiated remotely by the Web Bluetooth client.
     */
    private fun handleClientCommand(command: ClientCommand) {
        when (command) {
            is ClientCommand.RequestHistory -> {
                viewModelScope.launch {
                    _userFeedback.value = "Web client requested initial history transfer."
                    sendInitialHistory()
                }
            }
            is ClientCommand.AcknowledgeTransfer -> {
                viewModelScope.launch {
                    _userFeedback.value = "Web client verified transfer: ${command.transferId} (${command.status})"
                }
            }
            is ClientCommand.RequestSinglePacket -> {
                viewModelScope.launch {
                    val history = repository.getChronologicalHistory()
                    if (command.packetIndex in history.indices) {
                        bleManager.resendSinglePacket(
                            transferId = command.transferId,
                            packetIndex = command.packetIndex,
                            totalPackets = history.size,
                            reading = history[command.packetIndex]
                        )
                        _userFeedback.value = "Resent packet #${command.packetIndex} for transfer ${command.transferId}"
                    }
                }
            }
            is ClientCommand.Unknown -> {
                // Ignore unrecognized command
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        simulator.release()
        bleManager.close()
    }
}
