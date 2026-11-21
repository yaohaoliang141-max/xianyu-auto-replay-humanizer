$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$logs=Join-Path $r '.local/logs'
function Test-LocalPort($port){
 $client=New-Object System.Net.Sockets.TcpClient
 try { $task=$client.ConnectAsync('127.0.0.1',$port); return ($task.Wait(1000) -and $client.Connected) }
 catch { return $false }
 finally { $client.Dispose() }
}
function Start-Owned($name,$file,$arguments,$cwd,$port){
 if(Test-LocalPort $port){Write-Output "$name already listening on $port";return}
 $p=Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $cwd -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "$name.stdout.log") -RedirectStandardError (Join-Path $logs "$name.stderr.log") -PassThru
 Set-Content -LiteralPath (Join-Path $r ".local/$name.pid") -Value $p.Id
 $ready=$false
 for($attempt=0;$attempt -lt 60;$attempt++){
  $p.Refresh()
  if($p.HasExited){throw "$name exited before becoming ready; see .local/logs/$name.stderr.log"}
  if(Test-LocalPort $port){$ready=$true;break}
  Start-Sleep -Milliseconds 500
 }
 if(-not $ready){throw "$name did not open port $port"}
 Write-Output "$name PID $($p.Id)"
}
Start-Owned 'mysql' (Join-Path $r '.local/mysql/mysql-8.0.46-winx64/bin/mysqld.exe') @("--defaults-file=$r/.local/mysql.ini") $r 3307
Start-Owned 'redis' (Join-Path $r '.local/redis/Redis-8.4.7-Windows-x64-msys2/redis-server.exe') @('--bind','127.0.0.1','--port','6389','--protected-mode','yes','--appendonly','yes') (Join-Path $r '.local/data/redis') 6389
$py=Join-Path $r '.venv/Scripts/python.exe'
$runner=Join-Path $r '.local/run-service.py'
Start-Owned 'backend-web' $py @($runner,'backend-web') $r 8089
$ready=$false
for($i=0;$i -lt 60;$i++){
 try{$h=Invoke-RestMethod 'http://127.0.0.1:8089/health' -TimeoutSec 2; $ready=$true;break}catch{Start-Sleep -Seconds 1}
}
if(-not $ready){throw 'Backend health check timed out; see .local/logs/backend-web.stderr.log'}
Start-Owned 'websocket' $py @($runner,'websocket') $r 8090
Start-Owned 'scheduler' $py @($runner,'scheduler') $r 8091
Start-Owned 'frontend' (Get-Command node).Source @((Join-Path $r 'frontend/node_modules/vite/bin/vite.js'),'preview','--host','127.0.0.1','--port','9000','--strictPort') (Join-Path $r 'frontend') 9000
Write-Output 'Open http://127.0.0.1:9000'

