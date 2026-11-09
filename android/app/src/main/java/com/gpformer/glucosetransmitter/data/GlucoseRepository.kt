package com.gpformer.glucosetransmitter.data

import android.content.Context
import android.content.SharedPreferences
import com.gpformer.glucosetransmitter.model.GlucoseReading
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.atomic.AtomicLong
import kotlin.random.Random

/**
 * Single source of truth for glucose readings in the application.
 *
 * Responsibilities:
 * - Maintains a strictly bounded buffer of the latest 24 chronological readings
 *   required by the GPFormer transformer model (SEQ_LEN = 24).
 * - Monotonically increments sequence numbers.
 * - Persists state across app restarts via SharedPreferences.
 * - Provides synthetic pre-seeding for instantaneous end-to-end testing.
 * - Exposes reactive StateFlow for clean, modern Android UI observation.
 */
class GlucoseRepository(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val sequenceCounter = AtomicLong(0L)

    private val _readings = MutableStateFlow<List<GlucoseReading>>(emptyList())
    val readings: StateFlow<List<GlucoseReading>> = _readings.asStateFlow()

    init {
        loadPersistedState()
        // If repo has never been initialized, seed initial 24 readings for quick-start convenience.
        // If the user has previously cleared history, respect that choice and do not auto-re-seed.
        val hasInitialized = prefs.getBoolean(KEY_HAS_INITIALIZED, false)
        if (!hasInitialized && _readings.value.isEmpty()) {
            seedInitialHistory()
            prefs.edit().putBoolean(KEY_HAS_INITIALIZED, true).apply()
        }
    }

    /**
     * Increments and returns the next sequence number.
     */
    fun nextSequence(): Long = sequenceCounter.incrementAndGet()

    /**
     * Adds a newly recorded reading (manual or simulated) to the repository.
     * Retains strictly the most recent MAX_HISTORY_CAPACITY (24) readings in chronological order.
     */
    @Synchronized
    fun addReading(reading: GlucoseReading) {
        val currentList = _readings.value.toMutableList()
        currentList.add(reading)

        // Keep only latest 24 readings (oldest at index 0, latest at index size-1)
        val trimmed = if (currentList.size > MAX_HISTORY_CAPACITY) {
            currentList.takeLast(MAX_HISTORY_CAPACITY)
        } else {
            currentList
        }

        _readings.value = trimmed
        savePersistedState(trimmed)
    }

    /**
     * Returns a snapshot of the current 24 readings in chronological order.
     */
    fun getChronologicalHistory(): List<GlucoseReading> {
        return _readings.value
    }

    /**
     * Clears all stored readings while preserving sequence count continuity
     * to avoid duplicate sequence IDs across sessions.
     */
    @Synchronized
    fun clearHistory() {
        _readings.value = emptyList()
        prefs.edit()
            .remove(KEY_READINGS_JSON)
            .putBoolean(KEY_HAS_INITIALIZED, true)
            .apply()
    }

    /**
     * Generates 24 realistic, physiologically plausible seed readings spaced 15 minutes apart,
     * ending at the current time. This allows immediate testing with GPFormer without manually
     * typing 24 values.
     */
    @Synchronized
    fun seedInitialHistory() {
        val now = OffsetDateTime.now()
        val seedList = mutableListOf<GlucoseReading>()
        var baseline = 115.0 + Random.nextDouble(-10.0, 10.0)

        for (i in (MAX_HISTORY_CAPACITY - 1) downTo 0) {
            val stepTime = now.minusMinutes((i * 15).toLong())
            val formattedTime = stepTime.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)

            // Natural physiological smooth drift (+- 3 mg/dL per 15 min step)
            val delta = Random.nextDouble(-4.5, 4.5)
            baseline = (baseline + delta).coerceIn(80.0, 170.0)

            val seq = sequenceCounter.incrementAndGet()
            seedList.add(
                GlucoseReading.create(
                    sequence = seq,
                    glucose = baseline,
                    source = GlucoseReading.SOURCE_SIMULATED,
                    timestamp = formattedTime
                )
            )
        }

        _readings.value = seedList
        savePersistedState(seedList)
    }

    private fun loadPersistedState() {
        val lastSeq = prefs.getLong(KEY_LAST_SEQUENCE, 0L)
        sequenceCounter.set(lastSeq)

        val rawJson = prefs.getString(KEY_READINGS_JSON, null) ?: return
        try {
            val array = JSONArray(rawJson)
            val restored = mutableListOf<GlucoseReading>()
            for (i in 0 until array.length()) {
                val item = array.getJSONObject(i)
                restored.add(GlucoseReading.fromJson(item))
            }
            _readings.value = restored.takeLast(MAX_HISTORY_CAPACITY)
        } catch (e: Exception) {
            // If parsing fails, start empty
            _readings.value = emptyList()
        }
    }

    private fun savePersistedState(list: List<GlucoseReading>) {
        try {
            val array = JSONArray()
            list.forEach { array.put(it.toJson()) }
            prefs.edit()
                .putLong(KEY_LAST_SEQUENCE, sequenceCounter.get())
                .putString(KEY_READINGS_JSON, array.toString())
                .apply()
        } catch (e: Exception) {
            // Ignore persistence errors in rare low-storage situations
        }
    }

    companion object {
        const val MAX_HISTORY_CAPACITY = 24
        private const val PREFS_NAME = "glucose_transmitter_prefs"
        private const val KEY_LAST_SEQUENCE = "key_last_sequence"
        private const val KEY_READINGS_JSON = "key_readings_json"
        private const val KEY_HAS_INITIALIZED = "key_has_initialized"
    }
}
