package com.gpformer.glucosetransmitter.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.gpformer.glucosetransmitter.ui.MainActivity
import com.gpformer.glucosetransmitter.util.GlucoseTrendCalculator

/**
 * Manages blood glucose prediction notifications and smartwatch alerting.
 *
 * Configured specifically for high-priority notification mirroring to the
 * ZEB-FIT 20 Series smartwatch via the official companion app:
 * - Uses a dedicated HIGH importance NotificationChannel with custom vibration.
 * - Double-pulse vibration pattern: 500ms on, 200ms off, 500ms on.
 * - Formats concise titles and body messages tailored for smartwatch screen widths.
 * - Includes deduplication and a 15-minute cooldown window to avoid notification spam.
 * - Escalation override: fires immediately if glucose deteriorates significantly.
 */
class GlucoseNotificationManager(private val context: Context) {

    private val notificationManager: NotificationManager =
        context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    enum class AlertCategory {
        IMMEDIATE_LOW,
        HYPO_RISK,
        HYPER_RISK,
        TEST
    }

    val cooldownPolicy = AlertCooldownPolicy(
        cooldownDurationMs = COOLDOWN_DURATION_MS,
        escalationHypoDelta = ESCALATION_HYPO_DELTA,
        escalationHyperDelta = ESCALATION_HYPER_DELTA
    )

    init {
        createNotificationChannel()
    }

    /**
     * Initializes the high-priority alert notification channel with vibration.
     */
    fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val existing = notificationManager.getNotificationChannel(CHANNEL_ID)
            if (existing == null) {
                val channel = NotificationChannel(
                    CHANNEL_ID,
                    CHANNEL_NAME,
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = CHANNEL_DESCRIPTION
                    enableLights(true)
                    lightColor = Color.RED
                    enableVibration(true)
                    vibrationPattern = VIBRATION_PATTERN
                    lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
                    setBypassDnd(true)

                    val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
                    val audioAttributes = AudioAttributes.Builder()
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .build()
                    setSound(soundUri, audioAttributes)
                }
                notificationManager.createNotificationChannel(channel)
                Log.d(TAG, "Created notification channel: $CHANNEL_ID")
            }
        }
    }

    /**
     * Immediate alert when a measured glucose reading falls below 70 mg/dL.
     * Evaluated instantly without waiting for model inference.
     */
    fun showImmediateLowAlert(
        currentGlucose: Double,
        trend: GlucoseTrendCalculator.Trend
    ): Boolean {
        if (!shouldFireAlert(AlertCategory.IMMEDIATE_LOW, currentGlucose)) {
            Log.d(TAG, "Immediate low alert suppressed by cooldown.")
            return false
        }

        val title = "GPFORMER - CRITICAL LOW GLUCOSE"
        val body = "Current: ${formatGlucose(currentGlucose)} mg/dL (CRITICAL LOW) | Trend: ${trend.displayText} | Check glucose immediately!"

        dispatchNotification(
            notificationId = NOTIFICATION_ID_IMMEDIATE,
            title = title,
            body = body,
            color = COLOR_CRITICAL_RED,
            category = NotificationCompat.CATEGORY_ALARM
        )

        recordAlert(AlertCategory.IMMEDIATE_LOW, currentGlucose)
        return true
    }

    /**
     * Predictive hypoglycemia risk alert (+30m forecast < 70 mg/dL or clinical alert).
     */
    fun showHypoAlert(
        currentGlucose: Double,
        trend: GlucoseTrendCalculator.Trend,
        predicted30m: Double,
        hypoProbPct: Int
    ): Boolean {
        if (!shouldFireAlert(AlertCategory.HYPO_RISK, currentGlucose)) {
            Log.d(TAG, "Hypo risk alert suppressed by cooldown.")
            return false
        }

        val title = "GPFORMER - LOW GLUCOSE RISK"
        val body = "Now: ${formatGlucose(currentGlucose)} mg/dL (${trend.displayText}) | +30m: ${formatGlucose(predicted30m)} mg/dL | Risk: ${hypoProbPct}% | Check glucose immediately!"

        dispatchNotification(
            notificationId = NOTIFICATION_ID_HYPO,
            title = title,
            body = body,
            color = COLOR_WARNING_RED,
            category = NotificationCompat.CATEGORY_ALARM
        )

        recordAlert(AlertCategory.HYPO_RISK, currentGlucose)
        return true
    }

    /**
     * Predictive hyperglycemia risk alert (+30m forecast > 180 mg/dL or clinical alert).
     */
    fun showHyperAlert(
        currentGlucose: Double,
        trend: GlucoseTrendCalculator.Trend,
        predicted30m: Double,
        hyperProbPct: Int
    ): Boolean {
        if (!shouldFireAlert(AlertCategory.HYPER_RISK, currentGlucose)) {
            Log.d(TAG, "Hyper risk alert suppressed by cooldown.")
            return false
        }

        val title = "GPFORMER - HIGH GLUCOSE RISK"
        val body = "Now: ${formatGlucose(currentGlucose)} mg/dL (${trend.displayText}) | +30m: ${formatGlucose(predicted30m)} mg/dL | Risk: ${hyperProbPct}% | Check glucose immediately!"

        dispatchNotification(
            notificationId = NOTIFICATION_ID_HYPER,
            title = title,
            body = body,
            color = COLOR_WARNING_ORANGE,
            category = NotificationCompat.CATEGORY_REMINDER
        )

        recordAlert(AlertCategory.HYPER_RISK, currentGlucose)
        return true
    }

    /**
     * Test notification triggered manually from the UI to verify smartwatch
     * screen mirroring and vibration without waiting for ML events.
     * Bypasses cooldown logic.
     */
    fun showTestAlert(): Boolean {
        val title = "GPFORMER TEST ALERT"
        val body = "Your GPFormer smartwatch notification connection is working. Vibration pattern verified."

        dispatchNotification(
            notificationId = NOTIFICATION_ID_TEST,
            title = title,
            body = body,
            color = COLOR_TEST_BLUE,
            category = NotificationCompat.CATEGORY_STATUS
        )

        recordAlert(AlertCategory.TEST, 120.0)
        return true
    }

    /**
     * Builds and posts the high-priority notification to NotificationManager.
     */
    private fun dispatchNotification(
        notificationId: Int,
        title: String,
        body: String,
        color: Int,
        category: String
    ) {
        val tapIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId,
            tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(category)
            .setColor(color)
            .setVibrate(VIBRATION_PATTERN)
            .setAutoCancel(true)
            .setOngoing(false)
            .setContentIntent(pendingIntent)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)

        try {
            NotificationManagerCompat.from(context).notify(notificationId, builder.build())
            Log.i(TAG, "Notification #$notificationId dispatched: '$title'")
        } catch (e: SecurityException) {
            Log.e(TAG, "Permission denied while posting notification: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to post notification: ${e.message}")
        }
    }

    /**
     * Determines whether an alert should be dispatched or suppressed by cooldown.
     *
     * Rules:
     * - TEST alerts are always allowed.
     * - If no previous alert within COOLDOWN_DURATION_MS (15 min), allow.
     * - If category changed (e.g. from HYPO to IMMEDIATE_LOW), allow (escalation).
     * - If same category within cooldown, check if condition escalated significantly:
     *   - Hypo: glucose dropped by >= 15 mg/dL lower than last alerted value.
     *   - Hyper: glucose rose by >= 25 mg/dL higher than last alerted value.
     */
    fun shouldFireAlert(
        category: AlertCategory,
        currentGlucose: Double,
        currentTimeMs: Long = System.currentTimeMillis()
    ): Boolean {
        return cooldownPolicy.shouldFire(category, currentGlucose, currentTimeMs)
    }

    private fun recordAlert(category: AlertCategory, glucose: Double) {
        cooldownPolicy.recordAlert(category, glucose)
    }

    fun clearCooldown() {
        cooldownPolicy.clear()
    }

    fun getLastAlertTime(): Long? = cooldownPolicy.lastAlertRecord?.timestampMs

    private fun formatGlucose(value: Double): String {
        return (Math.round(value * 10.0) / 10.0).toString()
    }

    companion object {
        private const val TAG = "GlucoseNotificationMgr"

        const val CHANNEL_ID = "gpformer_glucose_alerts"
        const val CHANNEL_NAME = "GPFormer Glucose Alerts"
        const val CHANNEL_DESCRIPTION = "High-priority real-time blood glucose risk alerts and forecasts for ZEB-FIT smartwatch"

        // Vibration pattern: 0ms delay, 500ms vibrate, 200ms pause, 500ms vibrate
        val VIBRATION_PATTERN = longArrayOf(0, 500, 200, 500)

        const val NOTIFICATION_ID_IMMEDIATE = 1001
        const val NOTIFICATION_ID_HYPO = 1002
        const val NOTIFICATION_ID_HYPER = 1003
        const val NOTIFICATION_ID_TEST = 1004

        const val COOLDOWN_DURATION_MS = 15 * 60 * 1000L // 15 minutes
        const val ESCALATION_HYPO_DELTA = 15.0 // mg/dL drop to override cooldown
        const val ESCALATION_HYPER_DELTA = 25.0 // mg/dL rise to override cooldown

        private const val COLOR_CRITICAL_RED = 0xFFD32F2F.toInt()
        private const val COLOR_WARNING_RED = 0xFFE53935.toInt()
        private const val COLOR_WARNING_ORANGE = 0xFFF57C00.toInt()
        private const val COLOR_TEST_BLUE = 0xFF1976D2.toInt()
    }
}
