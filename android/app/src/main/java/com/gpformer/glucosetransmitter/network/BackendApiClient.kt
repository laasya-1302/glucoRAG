package com.gpformer.glucosetransmitter.network

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import com.gpformer.glucosetransmitter.model.GlucoseReading
import com.gpformer.glucosetransmitter.util.GlucoseTrendCalculator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * Data class encapsulating the full GPFormer prediction output returned by the backend.
 */
data class PredictionResult(
    val currentGlucose: Double,
    val trend: GlucoseTrendCalculator.Trend,
    val forecast30m: Double,
    val forecast60m: Double?,
    val forecast90m: Double?,
    val forecast120m: Double?,
    val q10_30m: Double,
    val q90_30m: Double,
    val hypoProbability: Double,
    val normalProbability: Double,
    val hyperProbability: Double,
    val riskClass: String,
    val clinicalAlertStatus: String, // "NORMAL", "HYPO_RISK", "HYPER_RISK"
    val clinicalAlertMessage: String,
    val clinicalAlertHorizon: Int?
) {
    val hypoProbPct: Int get() = (hypoProbability * 100.0).toInt().coerceIn(0, 100)
    val normalProbPct: Int get() = (normalProbability * 100.0).toInt().coerceIn(0, 100)
    val hyperProbPct: Int get() = (hyperProbability * 100.0).toInt().coerceIn(0, 100)
}

/**
 * Communicates with the FastAPI GPFormer backend over HTTP.
 *
 * Calls POST /predict with exactly 24 readings, parses multi-horizon quantile
 * predictions and calibrated risk probabilities, and determines risk alerts.
 */
class BackendApiClient(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, DEFAULT_BASE_URL) ?: DEFAULT_BASE_URL
        set(value) {
            val normalized = value.trim().removeSuffix("/")
            prefs.edit().putString(KEY_BASE_URL, normalized).apply()
        }

    /**
     * Executes prediction inference on the FastAPI backend using 24 readings.
     */
    suspend fun predict(readings: List<GlucoseReading>): Result<PredictionResult> =
        withContext(Dispatchers.IO) {
            if (readings.isEmpty()) {
                return@withContext Result.failure(IllegalArgumentException("Reading sequence is empty"))
            }

            val currentGlucose = readings.last().glucose
            val trend = GlucoseTrendCalculator.calculateTrend(readings)

            val urlString = "$baseUrl/predict"
            var connection: HttpURLConnection? = null

            try {
                val url = URL(urlString)
                connection = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 8000
                    readTimeout = 12000
                    doOutput = true
                    doInput = true
                    setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("Accept", "application/json")
                }

                // Construct PredictRequest JSON payload
                val payloadJson = buildPredictRequestJson(readings)

                // Write request body
                OutputStreamWriter(connection.outputStream, "UTF-8").use { writer ->
                    writer.write(payloadJson.toString())
                    writer.flush()
                }

                val responseCode = connection.responseCode
                if (responseCode !in 200..299) {
                    val errorStream = connection.errorStream ?: connection.inputStream
                    val errorBody = errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $responseCode"
                    Log.e(TAG, "Backend returned HTTP $responseCode: $errorBody")
                    return@withContext Result.failure(
                        Exception("Server error ($responseCode): $errorBody")
                    )
                }

                val responseText = connection.inputStream.bufferedReader().use { it.readText() }
                val responseJson = JSONObject(responseText)

                val result = parsePredictResponse(responseJson, currentGlucose, trend)
                Result.success(result)
            } catch (e: Exception) {
                Log.e(TAG, "Inference request to $urlString failed: ${e.message}", e)
                Result.failure(e)
            } finally {
                connection?.disconnect()
            }
        }

    /**
     * Serializes 24 readings into JSON compliant with PredictRequest backend schema.
     */
    fun buildPredictRequestJson(readings: List<GlucoseReading>): JSONObject {
        val json = JSONObject()
        val readingsArray = JSONArray()

        // Pass 24 readings as numeric float list
        for (r in readings) {
            readingsArray.put(r.glucose)
        }
        json.put("readings", readingsArray)

        // Latest timestamp
        val latestReading = readings.lastOrNull()
        if (latestReading != null) {
            json.put("latest_timestamp", latestReading.timestamp)
        }

        // Target model
        json.put("model_id", "e1_gpformer")

        return json
    }

    /**
     * Parses the PredictResponse JSON returned by FastAPI.
     */
    private fun parsePredictResponse(
        root: JSONObject,
        currentGlucose: Double,
        trend: GlucoseTrendCalculator.Trend
    ): PredictionResult {
        val forecastArray = root.getJSONArray("forecast")

        var f30 = currentGlucose
        var f60: Double? = null
        var f90: Double? = null
        var f120: Double? = null

        var q10 = currentGlucose - 10.0
        var q90 = currentGlucose + 10.0

        var hypoProb = 0.0
        var normalProb = 1.0
        var hyperProb = 0.0
        var riskClass = "NORMAL"

        for (i in 0 until forecastArray.length()) {
            val stepObj = forecastArray.getJSONObject(i)
            val horizon = stepObj.optInt("horizon_minutes", 0)
            val median = stepObj.optDouble("glucose_median", stepObj.optDouble("median", 0.0))

            when (horizon) {
                30 -> {
                    f30 = median
                    riskClass = stepObj.optString("predicted_risk_class", "NORMAL")

                    val quantiles = stepObj.optJSONObject("quantiles")
                    if (quantiles != null) {
                        q10 = quantiles.optDouble("q10", f30)
                        q90 = quantiles.optDouble("q90", f30)
                    }

                    val probs = stepObj.optJSONObject("risk_probabilities")
                    if (probs != null) {
                        hypoProb = probs.optDouble("hypo", 0.0)
                        normalProb = probs.optDouble("normal", 1.0)
                        hyperProb = probs.optDouble("hyper", 0.0)
                    }
                }
                60 -> f60 = median
                90 -> f90 = median
                120 -> f120 = median
            }
        }

        // Clinical alert object
        val clinicalAlertObj = root.optJSONObject("clinical_alert")
        val alertStatus = clinicalAlertObj?.optString("status", "NORMAL") ?: "NORMAL"
        val alertMessage = clinicalAlertObj?.optString("message", "No immediate risk flags.") ?: ""
        val alertHorizon = if (clinicalAlertObj?.has("alert_horizon_minutes") == true && !clinicalAlertObj.isNull("alert_horizon_minutes")) {
            clinicalAlertObj.getInt("alert_horizon_minutes")
        } else {
            null
        }

        return PredictionResult(
            currentGlucose = currentGlucose,
            trend = trend,
            forecast30m = f30,
            forecast60m = f60,
            forecast90m = f90,
            forecast120m = f120,
            q10_30m = q10,
            q90_30m = q90,
            hypoProbability = hypoProb,
            normalProbability = normalProb,
            hyperProbability = hyperProb,
            riskClass = riskClass,
            clinicalAlertStatus = alertStatus,
            clinicalAlertMessage = alertMessage,
            clinicalAlertHorizon = alertHorizon
        )
    }

    companion object {
        private const val TAG = "BackendApiClient"
        private const val PREFS_NAME = "gpformer_api_prefs"
        private const val KEY_BASE_URL = "key_base_url"

        // Defaults to your laptop's current active Wi-Fi IP address
        const val DEFAULT_BASE_URL = "http://192.168.1.6:8000"
    }
}
