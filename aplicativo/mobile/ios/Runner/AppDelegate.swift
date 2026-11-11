import Flutter
import UIKit
import UserNotifications

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var proximityChannel: FlutterMethodChannel?
  private var proximityObserver: NSObjectProtocol?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    UNUserNotificationCenter.current().delegate = self
    application.registerForRemoteNotifications()
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  override func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    super.application(application, didRegisterForRemoteNotificationsWithDeviceToken: deviceToken)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "GsfibraProximity") {
      setupProximityChannel(messenger: registrar.messenger())
    }
  }

  private func setupProximityChannel(messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(name: "gsfibra/proximity", binaryMessenger: messenger)
    channel.setMethodCallHandler { [weak self] call, result in
      switch call.method {
      case "enable":
        result(self?.enableProximity() ?? false)
      case "disable":
        self?.disableProximity()
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
    proximityChannel = channel
  }

  private func enableProximity() -> Bool {
    let device = UIDevice.current
    device.isProximityMonitoringEnabled = true
    guard device.isProximityMonitoringEnabled else { return false }
    if proximityObserver == nil {
      proximityObserver = NotificationCenter.default.addObserver(
        forName: UIDevice.proximityStateDidChangeNotification,
        object: device,
        queue: .main
      ) { [weak self] _ in
        self?.proximityChannel?.invokeMethod("onProximity", arguments: UIDevice.current.proximityState)
      }
    }
    return true
  }

  private func disableProximity() {
    if let observer = proximityObserver {
      NotificationCenter.default.removeObserver(observer)
      proximityObserver = nil
    }
    UIDevice.current.isProximityMonitoringEnabled = false
  }
}
