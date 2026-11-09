package com.gpformer.glucosetransmitter.model

import org.json.JSONObject

/**
 * Encapsulates the messages exchanged over BLE between the Android GATT server
 * and the laptop central client (Web Bluetooth).
 */
sealed class BleMessage {
    abstract val type: String
    abstract fun toJson(): JSONObject
    fun toJsonString(): String = toJson().toString()
}

/**
 * Message carrying a single item during initial history synchronization.
 */
data class HistoryItemMessage(
    val transferId: String,
    val packetIndex: Int,
    val totalPackets: Int,
    val reading: GlucoseReading
) : BleMessage() {
    override val type: String = "history_item"

    override fun toJson(): JSONObject {
        return JSONObject().apply {
            put("type", type)
            put("transfer_id", transferId)
            put("packet_index", packetIndex)
            put("total_packets", totalPackets)
            put("reading", reading.toJson())
        }
    }

    companion object {
        fun fromJson(json: JSONObject): HistoryItemMessage? {
            val transferId = json.optString("transfer_id", "")
            val packetIndex = json.optInt("packet_index", -1)
            val totalPackets = json.optInt("total_packets", 0)
            val readingObj = json.optJSONObject("reading") ?: return null
            val reading = GlucoseReading.fromJson(readingObj)
            return HistoryItemMessage(transferId, packetIndex, totalPackets, reading)
        }
    }
}

/**
 * Message notifying the client that all history items for transferId have been dispatched.
 */
data class HistoryCompleteMessage(
    val transferId: String,
    val totalPackets: Int,
    val status: String = "complete"
) : BleMessage() {
    override val type: String = "history_complete"

    override fun toJson(): JSONObject {
        return JSONObject().apply {
            put("type", type)
            put("transfer_id", transferId)
            put("total_packets", totalPackets)
            put("status", status)
        }
    }
}

/**
 * Commands received from the Web Bluetooth client written to the Control Characteristic.
 */
sealed class ClientCommand {
    data class RequestHistory(val requestId: String? = null) : ClientCommand()
    data class AcknowledgeTransfer(val transferId: String, val status: String) : ClientCommand()
    data class RequestSinglePacket(val transferId: String, val packetIndex: Int) : ClientCommand()
    data class Unknown(val raw: String) : ClientCommand()

    companion object {
        fun parse(payload: String): ClientCommand {
            return try {
                val json = JSONObject(payload)
                val cmd = json.optString("cmd", json.optString("type", ""))
                when (cmd.lowercase()) {
                    "request_history", "get_history" -> {
                        val reqId = if (json.has("request_id")) json.optString("request_id") else null
                        RequestHistory(reqId)
                    }
                    "history_ack", "ack" -> {
                        val txId = json.optString("transfer_id", "")
                        val status = json.optString("status", "ok")
                        AcknowledgeTransfer(txId, status)
                    }
                    "request_packet" -> {
                        val txId = json.optString("transfer_id", "")
                        val index = json.optInt("packet_index", -1)
                        RequestSinglePacket(txId, index)
                    }
                    else -> Unknown(payload)
                }
            } catch (e: Exception) {
                Unknown(payload)
            }
        }
    }
}
