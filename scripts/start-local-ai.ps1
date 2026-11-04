param([switch]$Install, [string]$Model = 'qwen3:1.7b')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $projectRoot '.local-ai'
$portableExe = Join-Path $runtimePath 'ollama.exe'
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaExe = if ($ollamaCommand) { $ollamaCommand.Source } else { $portableExe }

New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
if (-not (Test-Path -LiteralPath $ollamaExe)) {
    if (-not $Install) { throw 'Ollama absent. Relancez avec : ./scripts/start-local-ai.ps1 -Install' }
    $archivePath = Join-Path $runtimePath 'ollama-windows-amd64.zip'
    Write-Host 'Téléchargement du moteur Ollama portable (environ 1,6 Go)...'
    & curl.exe --fail --location --retry 3 --continue-at - --output $archivePath 'https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-windows-amd64.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Téléchargement Ollama échoué.' }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimePath -Force
}

$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $runtimePath 'models'
$env:OLLAMA_NO_CLOUD = '1'
$env:PLM_LOCAL_MODEL = $Model
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 }
catch {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $runtimePath -RedirectStandardOutput (Join-Path $runtimePath 'server.log') -RedirectStandardError (Join-Path $runtimePath 'server-error.log') | Out-Null
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 1; $ready = $true; break } catch { }
    }
    if (-not $ready) { throw 'Le serveur Ollama ne répond pas. Consultez .local-ai/server-error.log.' }
}
$catalog = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags'
if (-not ($catalog.models | Where-Object { $_.name -eq $Model })) {
    Write-Host "Téléchargement du modèle $Model (environ 1,4 Go)..."
    & $ollamaExe pull $Model
    if ($LASTEXITCODE -ne 0) { throw 'Téléchargement du modèle échoué.' }
}
Write-Host "IA locale prête : $Model sur http://127.0.0.1:11434"
Write-Host 'Lancement webapp : python -m streamlit run app.py'
