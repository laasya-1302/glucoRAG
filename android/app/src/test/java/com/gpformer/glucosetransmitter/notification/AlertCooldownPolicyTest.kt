package com.gpformer.glucosetransmitter.notification

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class AlertCooldownPolicyTest {

    private lateinit var policy: AlertCooldownPolicy
    private val baseTime = 1000000L

    @Before
    fun setUp() {
        policy = AlertCooldownPolicy(
            cooldownDurationMs = 15 * 60 * 1000L, // 15 min
            escalationHypoDelta = 15.0,
            escalationHyperDelta = 25.0
        )
    }

    @Test
    fun testFirstAlertAlwaysFires() {
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, baseTime))
    }

    @Test
    fun testTestAlertAlwaysFiresEvenDuringCooldown() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, baseTime)
        // 10 seconds later, test alert should still fire
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.TEST, 120.0, baseTime + 10000L))
    }

    @Test
    fun testSameCategorySuppressedWithinCooldownWithoutEscalation() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, baseTime)

        // 5 minutes later with slightly lower glucose (60.0, delta = 5 < 15 threshold)
        val fiveMinutesLater = baseTime + (5 * 60 * 1000L)
        assertFalse(policy.shouldFire(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 60.0, fiveMinutesLater))
    }

    @Test
    fun testHypoEscalationOverridesCooldown() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, baseTime)

        // 3 minutes later with steep drop to 48.0 (delta = 17 >= 15 threshold)
        val threeMinutesLater = baseTime + (3 * 60 * 1000L)
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 48.0, threeMinutesLater))
    }

    @Test
    fun testTransitionToImmediateCriticalLowOverridesCooldown() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 68.0, baseTime)

        // Measured glucose drops into critical immediate low
        val twoMinutesLater = baseTime + (2 * 60 * 1000L)
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.IMMEDIATE_LOW, 62.0, twoMinutesLater))
    }

    @Test
    fun testHyperEscalationOverridesCooldown() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPER_RISK, 200.0, baseTime)

        // 4 minutes later rises by 30 mg/dL to 230.0 (delta = 30 >= 25 threshold)
        val fourMinutesLater = baseTime + (4 * 60 * 1000L)
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.HYPER_RISK, 230.0, fourMinutesLater))
    }

    @Test
    fun testCategoryChangeBetweenHypoAndHyperOverridesCooldown() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, baseTime)

        // Rebound hyperglycemia 10 minutes later
        val tenMinutesLater = baseTime + (10 * 60 * 1000L)
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.HYPER_RISK, 210.0, tenMinutesLater))
    }

    @Test
    fun testAlertFiresAfterCooldownElapsed() {
        policy.recordAlert(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, baseTime)

        // 16 minutes later (> 15 min cooldown)
        val sixteenMinutesLater = baseTime + (16 * 60 * 1000L)
        assertTrue(policy.shouldFire(GlucoseNotificationManager.AlertCategory.HYPO_RISK, 65.0, sixteenMinutesLater))
    }
}
