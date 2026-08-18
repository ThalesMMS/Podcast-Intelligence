param(
  [string]$Target = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Media = Join-Path $Root "build\media\$Target"
New-Item -ItemType Directory -Force -Path $Media | Out-Null

foreach ($Command in @("uv", "npm", "cargo", "python")) {
  if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
    throw "$Command is required"
  }
}

python (Join-Path $Root "scripts\fetch_media_tools.py") --target $Target --output-dir $Media
$Attribution = Join-Path $Root "frontend\src-tauri\third_party\ffmpeg"
New-Item -ItemType Directory -Force -Path $Attribution | Out-Null
Copy-Item (Join-Path $Media "SOURCE.json") (Join-Path $Attribution "SOURCE.json") -Force
foreach ($Notice in @("UPSTREAM-LICENSE.txt", "UPSTREAM-README.txt")) {
  $SourceNotice = Join-Path $Media $Notice
  if (Test-Path $SourceNotice) {
    Copy-Item $SourceNotice (Join-Path $Attribution $Notice) -Force
  }
}
Push-Location (Join-Path $Root "backend")
try {
  uv sync --extra desktop --extra dev
  uv run python scripts\build_engine.py `
    --target $Target `
    --ffmpeg (Join-Path $Media "ffmpeg.exe") `
    --ffprobe (Join-Path $Media "ffprobe.exe")
}
finally {
  Pop-Location
}

Push-Location (Join-Path $Root "frontend")
try {
  npm install --no-audit --no-fund
  npm run tauri build -- --target $Target
}
finally {
  Pop-Location
}
