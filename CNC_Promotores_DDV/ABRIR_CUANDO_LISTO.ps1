param([int]$Port = 8520)
$base = "http://127.0.0.1:$Port"
for ($i = 0; $i -lt 90; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "$base/_stcore/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Start-Process "$base"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 1
}
Write-Host "El servidor no llego a estar disponible en $base"
