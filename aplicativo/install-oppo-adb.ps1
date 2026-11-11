$inf = "E:\niohub\supreme_network\oppo_adb_driver\android_winusb.inf"
Write-Host "Installing driver package..."
pnputil /add-driver $inf /install
Write-Host "Updating ADB Interface device..."
$dev = Get-PnpDevice -FriendlyName "ADB Interface" -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "*VID_22D9*" } | Select-Object -First 1
if ($dev) {
  Write-Host "Device: $($dev.InstanceId)"
  pnputil /update-driver $inf /deviceid "$($dev.InstanceId)" /force
} else {
  Write-Host "No present ADB Interface found for Oppo"
}
Write-Host "DONE"
pause
