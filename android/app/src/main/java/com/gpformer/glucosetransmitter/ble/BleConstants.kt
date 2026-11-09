package com.gpformer.glucosetransmitter.ble

import java.util.UUID

/**
 * Standard Bluetooth Low Energy GATT UUID definitions for the GPFormer GlucoseTransmitter system.
 *
 * The Android phone acts as a BLE GATT Server / Peripheral advertising the custom SERVICE_UUID.
 * The laptop browser (Chrome Web Bluetooth) acts as the BLE Central / Client, connecting to this
 * service, subscribing to notifications on CHARACTERISTIC_GLUCOSE_DATA_UUID, and issuing control
 * commands / ACKs on CHARACTERISTIC_CONTROL_UUID.
 */
object BleConstants {

    /**
     * GPFormer Custom Glucose Service UUID.
     */
    val SERVICE_UUID: UUID = UUID.fromString("1337BEEF-4750-466F-726D-657242470001")

    /**
     * Glucose Data Characteristic UUID (Properties: NOTIFY | READ).
     * Transmits real-time readings and 24-history packets to the laptop.
     */
    val CHARACTERISTIC_GLUCOSE_DATA_UUID: UUID = UUID.fromString("1337BEEF-4750-466F-726D-657242470002")

    /**
     * Control & Acknowledge Characteristic UUID (Properties: WRITE | WRITE_NO_RESPONSE).
     * Used by laptop Web Bluetooth to request history transfer or send packet acknowledgements.
     */
    val CHARACTERISTIC_CONTROL_UUID: UUID = UUID.fromString("1337BEEF-4750-466F-726D-657242470003")

    /**
     * Bluetooth SIG Standard Client Characteristic Configuration Descriptor (CCCD).
     * Written by Web Bluetooth client (`startNotifications()`) to enable characteristic notifications.
     */
    val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805F9B34FB")

    /**
     * BLE Peripheral Broadcast Local Name.
     */
    const val DEVICE_NAME = "GlucoseTransmitter"

    /**
     * Pacing delay (in milliseconds) between history packet transmissions to avoid BLE GATT buffer overflow.
     */
    const val HISTORY_PACKET_PACING_MS = 60L
}
