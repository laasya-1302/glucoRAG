package com.gpformer.glucosetransmitter.ui

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import com.gpformer.glucosetransmitter.R
import com.gpformer.glucosetransmitter.ble.BleServerManager
import com.gpformer.glucosetransmitter.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

/**
 * Main activity hosting the GlucoseTransmitter dashboard.
 *
 * Architecture overview:
 * - Uses ViewBinding for type-safe view access (no more findViewById).
 * - Uses AndroidViewModel to survive orientation changes.
 * - Observes StateFlows using lifecycle-aware coroutines.
 * - Handles BLE runtime permissions for both Android 12+ and legacy devices.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val viewModel: MainViewModel by viewModels()
    private lateinit var readingAdapter: ReadingHistoryAdapter

    // ── Permission launchers ──

    /**
     * Modern runtime permission launcher for Android 12+ (API 31) BLE permissions.
     * These new permissions (BLUETOOTH_ADVERTISE, BLUETOOTH_CONNECT) replaced the
     * legacy BLUETOOTH + BLUETOOTH_ADMIN permissions starting with Android 12.
     */
    private val blePermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            Toast.makeText(this, "Bluetooth permissions granted ✓", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, getString(R.string.error_permissions_denied), Toast.LENGTH_LONG).show()
        }
    }

    /**
     * Fallback launcher for requesting the user to enable Bluetooth hardware.
     */
    private val enableBluetoothLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            Toast.makeText(this, "Bluetooth enabled ✓", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, getString(R.string.error_bt_disabled), Toast.LENGTH_LONG).show()
        }
    }

    /**
     * Runtime permission launcher for Android 13+ (API 33+) POST_NOTIFICATIONS permission.
     */
    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            Toast.makeText(this, "Notification permission granted ✓", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "Notification permission denied - smartwatch mirroring disabled", Toast.LENGTH_LONG).show()
        }
    }

    // ── Lifecycle ──

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupRecyclerView()
        setupClickListeners()
        requestBlePermissions()
        requestNotificationPermission()
        observeStateFlows()
    }

    // ── RecyclerView ──

    private fun setupRecyclerView() {
        readingAdapter = ReadingHistoryAdapter()
        binding.rvReadings.apply {
            layoutManager = LinearLayoutManager(this@MainActivity).apply {
                // Show newest readings at the top of the list for natural readability
                reverseLayout = true
                stackFromEnd = true
            }
            adapter = readingAdapter
        }
    }

    // ── Button Click Handlers ──

    private fun setupClickListeners() {
        // Manual entry
        binding.btnAddReading.setOnClickListener {
            val inputText = binding.etGlucoseValue.text?.toString() ?: ""
            val success = viewModel.addManualReading(inputText)
            if (success) {
                binding.etGlucoseValue.text?.clear()
                hideKeyboard()
            }
        }

        // Simulation controls
        binding.btnStartSimulation.setOnClickListener {
            viewModel.startSimulation()
        }
        binding.btnStopSimulation.setOnClickListener {
            viewModel.stopSimulation()
        }

        // Simulation interval slider
        binding.sliderInterval.value = viewModel.simulationInterval.value.toFloat()
        binding.tvIntervalValue.text = "${viewModel.simulationInterval.value}s"
        binding.sliderInterval.addOnChangeListener { _, value, fromUser ->
            if (fromUser) {
                val seconds = value.toInt()
                viewModel.setSimulationInterval(seconds)
                binding.tvIntervalValue.text = "${seconds}s"
            }
        }

        // BLE advertising controls
        binding.btnStartAdvertising.setOnClickListener {
            ensureBluetoothEnabled {
                viewModel.startAdvertising()
            }
        }
        binding.btnStopAdvertising.setOnClickListener {
            viewModel.stopAdvertising()
        }

        // History controls
        binding.btnSendHistory.setOnClickListener {
            viewModel.sendInitialHistory()
        }
        binding.btnSeedHistory.setOnClickListener {
            viewModel.seed24Readings()
        }
        binding.btnSeedHypoPattern.setOnClickListener {
            viewModel.seedHypoReadings()
        }
        binding.btnSeedHyperPattern.setOnClickListener {
            viewModel.seedHyperReadings()
        }
        binding.btnClearHistory.setOnClickListener {
            viewModel.clearHistory()
        }

        // Smartwatch & Prediction Alerts controls
        binding.etBackendUrl.setText(viewModel.getBackendUrl())
        binding.btnSaveBackendUrl.setOnClickListener {
            val url = binding.etBackendUrl.text?.toString() ?: ""
            if (url.isNotBlank()) {
                viewModel.setBackendUrl(url)
                hideKeyboard()
            }
        }

        binding.btnTestSmartwatchNotification.setOnClickListener {
            requestNotificationPermission()
            viewModel.sendSmartwatchTestNotification()
        }

        binding.btnTestHypoAlert.setOnClickListener {
            requestNotificationPermission()
            viewModel.sendTestHypoAlert()
        }

        binding.btnTestHyperAlert.setOnClickListener {
            requestNotificationPermission()
            viewModel.sendTestHyperAlert()
        }

        binding.btnRunPredictionNow.setOnClickListener {
            viewModel.runPredictionInference()
        }

        binding.btnQuickSeedHypo.setOnClickListener {
            requestNotificationPermission()
            viewModel.seedHypoReadings()
        }

        binding.btnQuickSeedHyper.setOnClickListener {
            requestNotificationPermission()
            viewModel.seedHyperReadings()
        }
    }

    // ── State Observation ──

    /**
     * Subscribes to all reactive StateFlows from the ViewModel to keep the UI updated.
     * Uses lifecycle-aware collection that stops when the activity goes to background.
     */
    private fun observeStateFlows() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                // Reading list updates
                launch {
                    viewModel.readings.collect { readings ->
                        readingAdapter.submitList(readings.reversed()) // newest first display
                        binding.tvReadingsCount.text = "${readings.size} / 24"
                    }
                }

                // BLE advertising state
                launch {
                    viewModel.advertisingState.collect { state ->
                        when (state) {
                            is BleServerManager.AdvertisingStatus.Advertising -> {
                                binding.tvBleStatus.text = getString(R.string.status_advertising)
                                binding.tvBleStatus.setTextColor(
                                    ContextCompat.getColor(this@MainActivity, R.color.status_active)
                                )
                            }
                            is BleServerManager.AdvertisingStatus.Stopped -> {
                                binding.tvBleStatus.text = getString(R.string.status_not_advertising)
                                binding.tvBleStatus.setTextColor(
                                    ContextCompat.getColor(this@MainActivity, R.color.status_inactive)
                                )
                            }
                            is BleServerManager.AdvertisingStatus.Error -> {
                                binding.tvBleStatus.text = "Error: ${state.message}"
                                binding.tvBleStatus.setTextColor(
                                    ContextCompat.getColor(this@MainActivity, R.color.status_error)
                                )
                            }
                        }
                    }
                }

                // Connection state
                launch {
                    viewModel.connectionState.collect { state ->
                        when (state) {
                            is BleServerManager.ConnectionStatus.Connected -> {
                                binding.tvConnectionStatus.text = "Connected: ${state.deviceIdentifier}"
                                binding.tvConnectionStatus.setTextColor(
                                    ContextCompat.getColor(this@MainActivity, R.color.status_connected)
                                )
                            }
                            is BleServerManager.ConnectionStatus.Disconnected -> {
                                binding.tvConnectionStatus.text = getString(R.string.status_disconnected)
                                binding.tvConnectionStatus.setTextColor(
                                    ContextCompat.getColor(this@MainActivity, R.color.status_disconnected)
                                )
                            }
                        }
                    }
                }

                // Simulation mode indicator
                launch {
                    viewModel.isSimulating.collect { running ->
                        binding.tvModeStatus.text = if (running) {
                            getString(R.string.status_simulating)
                        } else {
                            getString(R.string.status_manual)
                        }
                        binding.tvModeStatus.setTextColor(
                            ContextCompat.getColor(
                                this@MainActivity,
                                if (running) R.color.badge_simulated else R.color.on_surface
                            )
                        )
                        binding.btnStartSimulation.isEnabled = !running
                        binding.btnStopSimulation.isEnabled = running
                    }
                }

                // Transfer progress
                launch {
                    viewModel.transferStatus.collect { status ->
                        binding.tvTransferStatus.text = status ?: "Idle"
                    }
                }

                // Last ACK from Web client
                launch {
                    viewModel.lastAckStatus.collect { ack ->
                        binding.tvAckStatus.text = ack ?: getString(R.string.status_no_ack)
                    }
                }

                // User feedback messages
                launch {
                    viewModel.userFeedback.collect { feedback ->
                        if (feedback != null) {
                            binding.tvFeedback.text = feedback
                            binding.tvFeedback.visibility = View.VISIBLE
                        } else {
                            binding.tvFeedback.visibility = View.GONE
                        }
                    }
                }

                // Hardware support check
                launch {
                    viewModel.hardwareSupported.collect { supported ->
                        if (!supported) {
                            binding.cardBleUnsupported.visibility = View.VISIBLE
                            binding.tvHardwareSupport.text = getString(R.string.status_hw_not_supported)
                            binding.tvHardwareSupport.setTextColor(
                                ContextCompat.getColor(this@MainActivity, R.color.status_error)
                            )
                            binding.btnStartAdvertising.isEnabled = false
                        } else {
                            binding.cardBleUnsupported.visibility = View.GONE
                            binding.tvHardwareSupport.text = getString(R.string.status_hw_supported)
                            binding.tvHardwareSupport.setTextColor(
                                ContextCompat.getColor(this@MainActivity, R.color.status_active)
                            )
                        }
                    }
                }

                // Alert status banner
                launch {
                    viewModel.alertStatusText.collect { text ->
                        binding.tvAlertStatusBanner.text = text
                    }
                }

                // Prediction running state
                launch {
                    viewModel.isPredicting.collect { predicting ->
                        binding.btnRunPredictionNow.isEnabled = !predicting
                        binding.btnRunPredictionNow.text = if (predicting) "Predicting..." else "Predict Now"
                    }
                }

                // Prediction results & probabilities
                launch {
                    viewModel.predictionResult.collect { result ->
                        if (result != null) {
                            binding.tvLiveTrend.text = result.trend.displayText
                            binding.tvLiveForecast30m.text = "${result.forecast30m} mg/dL"

                            val colorRes = when {
                                result.forecast30m < 70.0 -> R.color.risk_hypo
                                result.forecast30m > 180.0 -> R.color.risk_hyper
                                else -> R.color.risk_normal
                            }
                            binding.tvLiveForecast30m.setTextColor(
                                ContextCompat.getColor(this@MainActivity, colorRes)
                            )

                            binding.tvLiveProbabilities.text =
                                "Hypo: ${result.hypoProbPct}% | Normal: ${result.normalProbPct}% | Hyper: ${result.hyperProbPct}%"
                        } else {
                            binding.tvLiveTrend.text = "Stable →"
                            binding.tvLiveForecast30m.text = "-- mg/dL"
                            binding.tvLiveForecast30m.setTextColor(
                                ContextCompat.getColor(this@MainActivity, R.color.on_surface)
                            )
                            binding.tvLiveProbabilities.text = "Hypo: --% | Normal: --% | Hyper: --%"
                        }
                    }
                }
            }
        }
    }

    // ── Permissions ──

    /**
     * Requests BLE permissions based on Android version.
     *
     * Android 12+ (API 31+): needs BLUETOOTH_ADVERTISE, BLUETOOTH_CONNECT
     * Android 11 and below: needs BLUETOOTH, BLUETOOTH_ADMIN, ACCESS_FINE_LOCATION
     */
    private fun requestBlePermissions() {
        val permissionsNeeded = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(
                Manifest.permission.BLUETOOTH_ADVERTISE,
                Manifest.permission.BLUETOOTH_CONNECT
            )
        } else {
            arrayOf(
                Manifest.permission.BLUETOOTH,
                Manifest.permission.BLUETOOTH_ADMIN,
                Manifest.permission.ACCESS_FINE_LOCATION
            )
        }

        val ungranted = permissionsNeeded.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (ungranted.isNotEmpty()) {
            blePermissionLauncher.launch(ungranted.toTypedArray())
        }
    }

    /**
     * Requests POST_NOTIFICATIONS permission on Android 13+ (API 33+)
     * required for posting notifications mirrored to the smartwatch.
     */
    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val status = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.POST_NOTIFICATIONS
            )
            if (status != PackageManager.PERMISSION_GRANTED) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    /**
     * Checks if Bluetooth is enabled and prompts the user to turn it on if not.
     */
    private fun ensureBluetoothEnabled(onEnabled: () -> Unit) {
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        val adapter = bluetoothManager?.adapter
        if (adapter == null || !adapter.isEnabled) {
            try {
                val enableBtIntent = Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)
                enableBluetoothLauncher.launch(enableBtIntent)
            } catch (e: SecurityException) {
                Toast.makeText(this, getString(R.string.error_permissions_denied), Toast.LENGTH_LONG).show()
            }
        } else {
            onEnabled()
        }
    }

    private fun hideKeyboard() {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
        imm?.hideSoftInputFromWindow(binding.root.windowToken, 0)
    }
}
