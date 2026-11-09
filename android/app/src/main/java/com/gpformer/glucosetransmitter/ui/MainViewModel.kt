package com.gpformer.glucosetransmitter.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.gpformer.glucosetransmitter.ble.BleServerManager
import com.gpformer.glucosetransmitter.data.GlucoseRepository
import com.gpformer.glucosetransmitter.model.ClientCommand
import com.gpformer.glucosetransmitter.model.GlucoseReading
import com.gpformer.glucosetransmitter.simulation.GlucoseSimulator
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * ViewModel orchestrating data repository, simulation engine, and BLE server communications.
 * Holds presentation state and survives configuration changes.
 */
class MainViewModel(application: Application) : AndroidViewModel(application) {

    val repository = GlucoseRepository(application)

    private val _transferStatus = MutableStateFlow<String?>(null)
    val transferStatus: StateFlow<String?> = _transferStatus.asStateFlow()

    private val _userFeedback = MutableStateFlow<String?>(null)
    val userFeedback: StateFlow<String?> = _userFeedback.asStateFlow()

    // Initialize BLE Server Manager
    val bleManager = BleServerManager(application) { command ->
        handleClientCommand(command)
    }

    // Initialize Simulator
    val simulator = GlucoseSimulator(repository) { newReading ->
        // When simulation generates a reading, immediately transmit it via BLE notification
        bleManager.notifyReading(newReading)
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
     * Automatically notifies the connected BLE central.
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
        return true
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
                _transferStatus.value = "All $history.size packets sent (Transfer ID: $txId)"
                _userFeedback.value = "History transfer finished ($txId)"
            }
        )
    }

    /**
     * Pre-fills 24 realistic seed readings spaced 15 minutes apart.
     */
    fun seed24Readings() {
        repository.seedInitialHistory()
        _userFeedback.value = "Seeded 24 realistic chronological readings"
    }

    fun clearHistory() {
        repository.clearHistory()
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
