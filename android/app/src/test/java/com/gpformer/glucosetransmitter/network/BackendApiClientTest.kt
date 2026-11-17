package com.gpformer.glucosetransmitter.network

import com.gpformer.glucosetransmitter.model.GlucoseReading
import com.gpformer.glucosetransmitter.util.GlucoseTrendCalculator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BackendApiClientTest {

    @Test
    fun testPredictionResultPercentageFormatting() {
        val result = PredictionResult(
            currentGlucose = 85.0,
            trend = GlucoseTrendCalculator.Trend.STABLE,
            forecast30m = 84.2,
            forecast60m = 83.1,
            forecast90m = 82.5,
            forecast120m = 82.0,
            q10_30m = 78.0,
            q90_30m = 90.0,
            hypoProbability = 0.042,
            normalProbability = 0.941,
            hyperProbability = 0.017,
            riskClass = "NORMAL",
            clinicalAlertStatus = "NORMAL",
            clinicalAlertMessage = "No risk",
            clinicalAlertHorizon = null
        )

        assertEquals(4, result.hypoProbPct)
        assertEquals(94, result.normalProbPct)
        assertEquals(1, result.hyperProbPct)
    }

    @Test
    fun testPredictionResultRiskBoundaries() {
        val hypoResult = PredictionResult(
            currentGlucose = 65.0,
            trend = GlucoseTrendCalculator.Trend.FALLING,
            forecast30m = 58.0,
            forecast60m = 52.0,
            forecast90m = 50.0,
            forecast120m = 55.0,
            q10_30m = 50.0,
            q90_30m = 65.0,
            hypoProbability = 0.89,
            normalProbability = 0.11,
            hyperProbability = 0.00,
            riskClass = "HYPO",
            clinicalAlertStatus = "HYPO_RISK",
            clinicalAlertMessage = "Possible low glucose detected at +30 min.",
            clinicalAlertHorizon = 30
        )

        assertEquals(89, hypoResult.hypoProbPct)
        assertEquals(11, hypoResult.normalProbPct)
        assertEquals(0, hypoResult.hyperProbPct)
        assertEquals("HYPO_RISK", hypoResult.clinicalAlertStatus)
        assertTrue(hypoResult.forecast30m < 70.0)
    }
}
