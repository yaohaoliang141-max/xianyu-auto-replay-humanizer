param([switch]$AppsOnly)
$py=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$script=Join-Path $PSScriptRoot '.local/stop-local.py'
if($AppsOnly){& $py $script --apps-only}else{& $py $script}
