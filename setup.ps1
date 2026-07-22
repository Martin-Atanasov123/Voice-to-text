# FlowLocal setup: creates the venv, installs Python deps, detects the GPU,
# and pulls the right-sized Ollama cleanup models for THIS machine's VRAM.
#
# Run once after cloning:  powershell -ExecutionPolicy Bypass -File setup.ps1
#
# Safe to re-run: never overwrites an existing config.json, and skips any
# Ollama model that's already pulled.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== FlowLocal setup ==" -ForegroundColor Cyan

# 1. Python venv + dependencies
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "Installing Python dependencies (this can take a few minutes)..."
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt

# 2. Detect GPU (NVIDIA only -- ctranslate2's CUDA path needs it; anything
# else correctly falls back to CPU via the app's own "auto" whisper device).
Write-Host "`nDetecting GPU..."
$gpuTotalMB = 0
try {
    $out = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) {
        $parts = $out -split ","
        $gpuName = $parts[0].Trim()
        $gpuTotalMB = [int]$parts[1].Trim()
        Write-Host "  Found: $gpuName ($gpuTotalMB MB VRAM)"
    }
} catch {}
if ($gpuTotalMB -eq 0) {
    Write-Host "  No NVIDIA GPU detected -- whisper will run on CPU (still works, just slower)."
}

# 3. Pick cleanup models by VRAM tier.
#
# BG is pinned to qwen3:4b regardless of tier: this is the one model verified
# against real Bulgarian recordings in this project (2026-07-23) -- qwen2.5:3b
# was found to mangle Bulgarian, qwen3:4b did not. No bigger model has been
# benchmarked for BG, so we deliberately do NOT extrapolate upward without
# evidence, even on a much stronger GPU.
#
# EN scales with VRAM on the standard (but NOT independently verified in this
# project) assumption that a bigger Qwen instruct model gives better English
# cleanup. If that turns out wrong for some model size, downgrade it in
# Settings -> Models & AI -- nothing else in the app depends on this choice.
$bgModel = "qwen3:4b-instruct-2507-q4_K_M"
if ($gpuTotalMB -le 4096)      { $enModel = "qwen2.5:3b-instruct" }
elseif ($gpuTotalMB -le 16384) { $enModel = "qwen2.5:7b-instruct" }
elseif ($gpuTotalMB -le 24576) { $enModel = "qwen2.5:14b-instruct" }
else                           { $enModel = "qwen2.5:32b-instruct" }

Write-Host "`nRecommended cleanup models for this hardware:"
Write-Host "  EN: $enModel"
Write-Host "  BG: $bgModel"

# 4. Ollama: detect only, never silently install third-party software.
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaPath = if ($ollamaCmd) { $ollamaCmd.Source } else {
    $candidate = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $candidate) { $candidate } else { $null }
}

if (-not $ollamaPath) {
    Write-Host "`nOllama not found." -ForegroundColor Yellow
    Write-Host "Install it from https://ollama.com, then re-run this script to pull the cleanup models."
} else {
    Write-Host "`nOllama found at $ollamaPath"

    # Mirror the fix in flowlocal/cleanup.py: the Windows tray app is known to
    # start the server with OLLAMA_MODELS pointing at the wrong directory,
    # which makes it report zero models while holding the real ones untouched
    # on disk. Start our own server with the correct path if none is running.
    if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
        Write-Host "Starting Ollama server..."
        $env:OLLAMA_MODELS = Join-Path $env:USERPROFILE ".ollama\models"
        Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }

    $installed = & $ollamaPath list 2>$null
    foreach ($m in @($enModel, $bgModel) | Select-Object -Unique) {
        if ($installed -match [regex]::Escape($m)) {
            Write-Host "  $m already installed"
        } else {
            Write-Host "  Pulling $m ..."
            & $ollamaPath pull $m
        }
    }
}

# 5. Write config.json ONLY if none exists yet -- never touch a user's
# existing settings on re-run.
$configDir = Join-Path $env:APPDATA "FlowLocal"
$configPath = Join-Path $configDir "config.json"
if (-not (Test-Path $configPath)) {
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    @{ ollama_model_en = $enModel; ollama_model_bg = $bgModel } |
        ConvertTo-Json | Set-Content -Path $configPath -Encoding utf8
    Write-Host "`nWrote $configPath with the recommended cleanup models."
} else {
    Write-Host "`n$configPath already exists -- your existing settings are untouched."
    Write-Host "If you want the recommended models above, set them in Settings -> Models & AI."
}

Write-Host "`n== Setup complete ==" -ForegroundColor Green
Write-Host "Run FlowLocal with:  .\.venv\Scripts\pythonw.exe run_flowlocal.pyw"
