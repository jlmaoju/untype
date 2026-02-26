#!/usr/bin/env pwsh
# UnType Demo GIF Recorder
# Usage: .\scripts\record_demo.ps1
# Requirements: ffmpeg (https://ffmpeg.org/download.html)

$ErrorActionPreference = "Stop"

# Configuration
$OutputDir = "media"
$GifOutput = "$OutputDir\demo.gif"
$Mp4Output = "$OutputDir\demo.mp4"

# Create output directory if not exists
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    Write-Host "Created output directory: $OutputDir" -ForegroundColor Green
}

# Check ffmpeg
Write-Host "Checking ffmpeg..." -ForegroundColor Cyan
try {
    $null = ffmpeg -version 2>&1
} catch {
    Write-Host "ERROR: ffmpeg not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install ffmpeg:"
    Write-Host "  1. Download from https://ffmpeg.org/download.html#build-windows"
    Write-Host "  2. Extract to a folder (e.g., C:\ffmpeg)"
    Write-Host "  3. Add to PATH: setx PATH '%PATH%;C:\ffmpeg\bin'"
    Write-Host "  4. Restart terminal"
    exit 1
}

# Get screen dimensions
Add-Type -AssemblyName System.Windows.Forms
$Screen = [System.Windows.Forms.Screen]::PrimaryScreen
$ScreenWidth = $Screen.Bounds.Width
$ScreenHeight = $Screen.Bounds.Height

# Calculate recording area (center, about 1200x800 for good demo)
$RecWidth = 1200
$RecHeight = 800
$RecX = ($ScreenWidth - $RecWidth) / 2
$RecY = ($ScreenHeight - $RecHeight) / 2

Write-Host ""
Write-Host "=== UnType Demo Recorder ===" -ForegroundColor Cyan
Write-Host "Screen: ${ScreenWidth}x$ScreenHeight" -ForegroundColor Gray
Write-Host "Recording area: ${RecWidth}x$RecHeight at ($RecX, $RecY)" -ForegroundColor Gray
Write-Host ""

# Demo script for the user to follow
Write-Host "DEMO SCRIPT (practice this first!):" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Open Notepad and position in the center of screen"
Write-Host "  2. Press Enter to START recording"
Write-Host "  3. Press F6, say: '你好，我想请问一下这个产品什么时候发货'"
Write-Host "  4. Press F6 again to stop"
Write-Host "  5. Wait for polished text to appear"
Write-Host "  6. Press 'q' to STOP recording"
Write-Host ""
Write-Host "Tips:" -ForegroundColor Gray
Write-Host "  - Speak clearly at normal pace" -ForegroundColor Gray
Write-Host "  - The capsule should appear near your cursor" -ForegroundColor Gray
Write-Host "  - Keep mic close but not too close" -ForegroundColor Gray
Write-Host ""

# Countdown
Write-Host "Recording starts in..." -ForegroundColor Cyan
for ($i = 3; $i -gt 0; $i--) {
    Write-Host "  $i..." -ForegroundColor Yellow
    Start-Sleep -Seconds 1
}
Write-Host "  REC!" -ForegroundColor Green
Write-Host ""
Write-Host "(Press 'q' to stop recording)" -ForegroundColor Gray

# Record with ffmpeg
ffmpeg -y -f gdigrab -framerate 30 -i_offset=$RecY -video_size "${RecWidth}x${RecHeight}" -offset_x $RecX -offset_y $RecY -draw_mouse 1 $Mp4Output 2>&1 | Out-Null

# Check if recording was successful
if (Test-Path $Mp4Output) {
    $FileSize = (Get-Item $Mp4Output).Length / 1MB
    Write-Host ""
    Write-Host "Recording saved: $Mp4Output ($([math]::Round($FileSize, 2)) MB)" -ForegroundColor Green

    # Convert to GIF
    Write-Host "Converting to GIF..." -ForegroundColor Cyan
    ffmpeg -y -i $Mp4Output -vf "fps=15,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 $GifOutput 2>&1 | Out-Null

    if (Test-Path $GifOutput) {
        $GifSize = (Get-Item $GifOutput).Length / 1KB
        Write-Host "GIF created: $GifOutput ($([math]::Round($GifSize, 2)) KB)" -ForegroundColor Green

        Write-Host ""
        Write-Host "Done! Add to README:" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  ![Demo](media/demo.gif)"
        Write-Host ""
    } else {
        Write-Host "WARNING: GIF conversion failed, but MP4 is available" -ForegroundColor Yellow
    }
} else {
    Write-Host "ERROR: Recording failed" -ForegroundColor Red
}
