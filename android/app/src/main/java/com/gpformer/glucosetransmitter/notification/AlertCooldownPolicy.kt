package com.gpformer.glucosetransmitter.notification

/**
 * Encapsulates cooldown timing, deduplication, and clinical escalation override rules
 * for smartwatch blood glucose alerts.
 */
class AlertCooldownPolicy(
    val cooldownDurationMs: Long = DEFAULT_COOLDOWN_MS,
    val escalationHypoDelta: Double = DEFAULT_ESCALATION_HYPO_DELTA,
    val escalationHyperDelta: Double = DEFAULT_ESCALATION_HYPER_DELTA
) {
    data class AlertRecord(
        val category: GlucoseNotificationManager.AlertCategory,
        val timestampMs: Long,
        val glucose: Double
    )

    var lastAlertRecord: AlertRecord? = null
        private set

    var isCooldownEnabled: Boolean = true

    fun recordAlert(
        category: GlucoseNotificationManager.AlertCategory,
        glucose: Double,
        timestampMs: Long = System.currentTimeMillis()
    ) {
        // Test alerts must NEVER trigger a clinical cooldown lockout
        if (category == GlucoseNotificationManager.AlertCategory.TEST) {
            return
        }
        lastAlertRecord = AlertRecord(category, timestampMs, glucose)
    }

    fun clear() {
        lastAlertRecord = null
    }

    /**
     * Evaluates if a notification should be fired or suppressed.
     */
    fun shouldFire(
        category: GlucoseNotificationManager.AlertCategory,
        currentGlucose: Double,
        currentTimeMs: Long = System.currentTimeMillis()
    ): Boolean {
        if (!isCooldownEnabled || category == GlucoseNotificationManager.AlertCategory.TEST) {
            return true
        }

        val last = lastAlertRecord ?: return true
        val timeSinceLast = currentTimeMs - last.timestampMs

        if (timeSinceLast >= cooldownDurationMs) {
            return true
        }

        // Escalation: transitioning to immediate critical low from any prior category
        if (category == GlucoseNotificationManager.AlertCategory.IMMEDIATE_LOW &&
            last.category != GlucoseNotificationManager.AlertCategory.IMMEDIATE_LOW
        ) {
            return true
        }

        // Category change between hypo and hyper
        if (category != last.category) {
            return true
        }

        // Physiological escalation within cooldown window
        return when (category) {
            GlucoseNotificationManager.AlertCategory.HYPO_RISK,
            GlucoseNotificationManager.AlertCategory.IMMEDIATE_LOW -> {
                (last.glucose - currentGlucose) >= escalationHypoDelta
            }
            GlucoseNotificationManager.AlertCategory.HYPER_RISK -> {
                (currentGlucose - last.glucose) >= escalationHyperDelta
            }
            else -> false
        }
    }

    companion object {
        const val DEFAULT_COOLDOWN_MS = 15 * 60 * 1000L // 15 minutes
        const val DEFAULT_ESCALATION_HYPO_DELTA = 15.0 // mg/dL
        const val DEFAULT_ESCALATION_HYPER_DELTA = 25.0 // mg/dL
    }
}
