package com.gpformer.glucosetransmitter.model

import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

/**
 * Represents a single blood glucose reading recorded either manually by the user
 * or automatically by the simulation engine.
 *
 * Conforms strictly to the GPFormer expected input specifications:
 * - Glucose value in mg/dL
 * - Sequence number increasing monotonically
 * - Timezone-aware ISO-8601 timestamp
 * - Source ("manual" or "simulated")
 */
data class GlucoseReading(
    val sequence: Long,
    val glucose: Double,
    val unit: String = UNIT_MG_DL,
    val timestamp: String,
    val source: String
) {
    /**
     * Serializes this reading to a JSONObject matching the BLE wire specification.
     */
    fun toJson(): JSONObject {
        return JSONObject().apply {
            put("type", "glucose_reading")
            put("sequence", sequence)
            put("glucose", glucose)
            put("unit", unit)
            put("timestamp", timestamp)
            put("source", source)
        }
    }

    /**
     * Converts the reading to compact JSON string for transmission over BLE.
     */
    fun toJsonString(): String = toJson().toString()

    /**
     * Categorizes glucose reading into physiological risk bands defined by the GPFormer pipeline:
     * - HYPO: < 70 mg/dL
     * - NORMAL: 70 - 180 mg/dL
     * - HYPER: > 180 mg/dL
     */
    val riskCategory: RiskCategory
        get() = when {
            glucose < HYPO_THRESHOLD -> RiskCategory.HYPO
            glucose > HYPER_THRESHOLD -> RiskCategory.HYPER
            else -> RiskCategory.NORMAL
        }

    enum class RiskCategory {
        HYPO,
        NORMAL,
        HYPER
    }

    companion object {
        const val UNIT_MG_DL = "mg/dL"
        const val SOURCE_MANUAL = "manual"
        const val SOURCE_SIMULATED = "simulated"

        const val MIN_PHYSIOLOGICAL_GLUCOSE = 20.0
        const val MAX_PHYSIOLOGICAL_GLUCOSE = 600.0
        const val HYPO_THRESHOLD = 70.0
        const val HYPER_THRESHOLD = 180.0

        /**
         * Validates whether a numerical glucose entry is within clinically plausible boundaries.
         */
        fun isValidGlucose(value: Double): Boolean {
            return !value.isNaN() && !value.isInfinite() &&
                    value in MIN_PHYSIOLOGICAL_GLUCOSE..MAX_PHYSIOLOGICAL_GLUCOSE
        }

        /**
         * Returns current timestamp formatted as ISO-8601 with timezone offset.
         * Example: 2026-11-02T12:10:49+05:30
         */
        fun currentIsoTimestamp(): String {
            return OffsetDateTime.now().format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        }

        /**
         * Factory method to build a new reading with automatic timestamp if not provided.
         */
        fun create(
            sequence: Long,
            glucose: Double,
            source: String,
            timestamp: String = currentIsoTimestamp()
        ): GlucoseReading {
            return GlucoseReading(
                sequence = sequence,
                glucose = (glucose * 10.0).toLong() / 10.0, // rounded to 1 decimal place
                unit = UNIT_MG_DL,
                timestamp = timestamp,
                source = source
            )
        }

        /**
         * Deserializes a GlucoseReading from a JSONObject.
         */
        fun fromJson(json: JSONObject): GlucoseReading {
            return GlucoseReading(
                sequence = json.optLong("sequence", 0L),
                glucose = json.optDouble("glucose", 100.0),
                unit = json.optString("unit", UNIT_MG_DL),
                timestamp = json.optString("timestamp", currentIsoTimestamp()),
                source = json.optString("source", SOURCE_MANUAL)
            )
        }
    }
}
