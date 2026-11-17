package com.gpformer.glucosetransmitter.util

import com.gpformer.glucosetransmitter.model.GlucoseReading
import org.junit.Assert.assertEquals
import org.junit.Test

class GlucoseTrendCalculatorTest {

    private fun reading(glucose: Double): GlucoseReading {
        return GlucoseReading.create(
            sequence = 1,
            glucose = glucose,
            source = GlucoseReading.SOURCE_MANUAL,
            timestamp = "2026-11-16T10:00:00+05:30"
        )
    }

    @Test
    fun testEmptyOrSingleReadingDefaultsToStable() {
        assertEquals(GlucoseTrendCalculator.Trend.STABLE, GlucoseTrendCalculator.calculateTrend(emptyList()))
        assertEquals(GlucoseTrendCalculator.Trend.STABLE, GlucoseTrendCalculator.calculateTrend(listOf(reading(100.0))))
    }

    @Test
    fun testRisingFast() {
        val readings = listOf(reading(100.0), reading(106.0)) // delta = +6.0
        val trend = GlucoseTrendCalculator.calculateTrend(readings)
        assertEquals(GlucoseTrendCalculator.Trend.RISING_FAST, trend)
        assertEquals("Rising fast ⇈", trend.displayText)
    }

    @Test
    fun testRising() {
        val readings = listOf(reading(100.0), reading(103.5)) // delta = +3.5
        val trend = GlucoseTrendCalculator.calculateTrend(readings)
        assertEquals(GlucoseTrendCalculator.Trend.RISING, trend)
        assertEquals("Rising ↗", trend.displayText)
    }

    @Test
    fun testStable() {
        val readings = listOf(reading(100.0), reading(101.0)) // delta = +1.0
        val trend = GlucoseTrendCalculator.calculateTrend(readings)
        assertEquals(GlucoseTrendCalculator.Trend.STABLE, trend)
        assertEquals("Stable →", trend.displayText)
    }

    @Test
    fun testFalling() {
        val readings = listOf(reading(100.0), reading(96.5)) // delta = -3.5
        val trend = GlucoseTrendCalculator.calculateTrend(readings)
        assertEquals(GlucoseTrendCalculator.Trend.FALLING, trend)
        assertEquals("Falling ↘", trend.displayText)
    }

    @Test
    fun testFallingFast() {
        val readings = listOf(reading(100.0), reading(93.0)) // delta = -7.0
        val trend = GlucoseTrendCalculator.calculateTrend(readings)
        assertEquals(GlucoseTrendCalculator.Trend.FALLING_FAST, trend)
        assertEquals("Falling fast ⇊", trend.displayText)
    }
}
