package com.gpformer.glucosetransmitter.util

import com.gpformer.glucosetransmitter.model.GlucoseReading

/**
 * Calculates physiological glucose rate of change and trend direction
 * based on the most recent consecutive glucose readings.
 *
 * Conforms to clinical CGM trend arrow conventions (e.g. Dexcom / Abbott):
 * - Rising fast: delta >= +5.0 mg/dL (or >= 2 mg/dL/min over 15m)
 * - Rising: delta in [+2.0, +5.0) mg/dL
 * - Stable: delta in (-2.0, +2.0) mg/dL
 * - Falling: delta in (-5.0, -2.0] mg/dL
 * - Falling fast: delta <= -5.0 mg/dL
 */
object GlucoseTrendCalculator {

    enum class Trend(
        val label: String,
        val arrow: String,
        val displayText: String
    ) {
        RISING_FAST("Rising Fast", "↑↑", "Rising fast ⇈"),
        RISING("Rising", "↗", "Rising ↗"),
        STABLE("Stable", "→", "Stable →"),
        FALLING("Falling", "↘", "Falling ↘"),
        FALLING_FAST("Falling Fast", "↓↓", "Falling fast ⇊");
    }

    /**
     * Computes the current glucose trend from a chronological list of readings.
     * Index size - 1 is the latest reading.
     */
    fun calculateTrend(readings: List<GlucoseReading>): Trend {
        if (readings.size < 2) {
            return Trend.STABLE
        }

        val latest = readings[readings.size - 1].glucose
        val previous = readings[readings.size - 2].glucose
        val delta = latest - previous

        return determineTrendFromDelta(delta)
    }

    fun determineTrendFromDelta(delta: Double): Trend {
        return when {
            delta >= 5.0 -> Trend.RISING_FAST
            delta >= 2.0 -> Trend.RISING
            delta <= -5.0 -> Trend.FALLING_FAST
            delta <= -2.0 -> Trend.FALLING
            else -> Trend.STABLE
        }
    }
}
