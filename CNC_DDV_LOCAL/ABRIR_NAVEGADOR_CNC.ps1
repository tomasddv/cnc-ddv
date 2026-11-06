param(
    [int]$Port = 8515
)
$uri = "http://127.0.0.1:$Port/_stcore/health"
for ($i=0; $i -lt 180; $i++) {
    try {
        $respuesta = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2
        if ($respuesta.StatusCode -eq 200) {
            Start-Process "http://localhost:$Port"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 1
}
Write-Host "No se detecto Streamlit. Revisar diagnostico_inicio.txt"
