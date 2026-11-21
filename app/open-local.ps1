param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$url='http://127.0.0.1:9000'
$mutex=New-Object System.Threading.Mutex($false,'Local\XianyuLocalLauncher')
if(-not $mutex.WaitOne(0)){exit 0}
try {
 & (Join-Path $r 'start-local.ps1') | Out-Null
 foreach($port in @(8089,8090,8091,9000)){
  $ready=$false
  $endpoint=if($port -eq 9000){$url}else{"http://127.0.0.1:$port/health"}
  for($i=0;$i -lt 90;$i++){
   try{$response=Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 2;if($response.StatusCode -eq 200){$ready=$true;break}}catch{}
   Start-Sleep -Seconds 1
  }
  if(-not $ready){throw "Service on port $port did not become ready"}
 }
 if(-not $CheckOnly){Start-Process $url}
 Write-Output 'All services ready; launcher check passed.'
} catch {
 $_ | Out-File -LiteralPath (Join-Path $r '.local/logs/launcher-error.log') -Append -Encoding utf8
 if($CheckOnly){throw}
 Add-Type -AssemblyName PresentationFramework
 [System.Windows.MessageBox]::Show("Startup failed. See: $r\.local\logs\launcher-error.log",'Xianyu launcher') | Out-Null
 exit 1
} finally {
 $mutex.ReleaseMutex()
 $mutex.Dispose()
}
