package com.gsfibra.app

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.PowerManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity(), SensorEventListener {
    private var proximityChannel: MethodChannel? = null
    private var sensorManager: SensorManager? = null
    private var proximitySensor: Sensor? = null
    private var screenOffLock: PowerManager.WakeLock? = null
    private var lastNear: Boolean? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        proximityChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "gsfibra/proximity").also { channel ->
            channel.setMethodCallHandler { call, result ->
                when (call.method) {
                    "enable" -> result.success(enableProximity())
                    "disable" -> {
                        disableProximity()
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
        }
    }

    private fun enableProximity(): Boolean {
        val manager = sensorManager
            ?: (getSystemService(Context.SENSOR_SERVICE) as SensorManager).also { sensorManager = it }
        val sensor = proximitySensor
            ?: manager.getDefaultSensor(Sensor.TYPE_PROXIMITY)?.also { proximitySensor = it }
            ?: return false

        manager.unregisterListener(this)
        lastNear = null
        manager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)

        val power = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (screenOffLock == null && power.isWakeLockLevelSupported(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK)) {
            screenOffLock = power.newWakeLock(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK, "gsfibra:audio_proximity")
        }
        screenOffLock?.let { if (!it.isHeld) it.acquire(30 * 60 * 1000L) }
        return true
    }

    private fun disableProximity() {
        sensorManager?.unregisterListener(this)
        screenOffLock?.let { if (it.isHeld) it.release(PowerManager.RELEASE_FLAG_WAIT_FOR_NO_PROXIMITY) }
        lastNear = null
    }

    override fun onSensorChanged(event: SensorEvent) {
        val sensor = event.sensor ?: return
        val distance = event.values.firstOrNull() ?: return
        val near = distance < minOf(sensor.maximumRange, 5f)
        if (near == lastNear) return
        lastNear = near
        proximityChannel?.invokeMethod("onProximity", near)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onDestroy() {
        disableProximity()
        super.onDestroy()
    }
}
