# Run from M:\trading\visualiser\ in an Administrator PowerShell.
# Does everything: installs vcpkg, packages, clones ImGui/ImPlot, configures & builds.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$VCPKG_ROOT = "C:\vcpkg"
$IMGUI_TAG  = "v1.91.6"
$IMPLOT_TAG = "v0.17"

# ── 1. vcpkg ─────────────────────────────────────────────────────────────────
if (-not (Test-Path "$VCPKG_ROOT\vcpkg.exe")) {
    Write-Host "==> Cloning vcpkg to $VCPKG_ROOT"
    git clone https://github.com/microsoft/vcpkg.git $VCPKG_ROOT
    Write-Host "==> Bootstrapping vcpkg"
    & "$VCPKG_ROOT\bootstrap-vcpkg.bat" -disableMetrics
} else {
    Write-Host "==> vcpkg already at $VCPKG_ROOT, skipping clone"
}

# ── 2. vcpkg packages ────────────────────────────────────────────────────────
Write-Host "==> Installing glfw3 and sqlite3 (x64-windows)"
& "$VCPKG_ROOT\vcpkg.exe" install glfw3:x64-windows sqlite3:x64-windows

# ── 3. ImGui / ImPlot ────────────────────────────────────────────────────────
$scriptDir = Split-Path $MyInvocation.MyCommand.Path

if (-not (Test-Path "$scriptDir\third_party\imgui")) {
    Write-Host "==> Cloning Dear ImGui $IMGUI_TAG"
    git clone --depth 1 --branch $IMGUI_TAG https://github.com/ocornut/imgui.git "$scriptDir\third_party\imgui"
} else {
    Write-Host "==> third_party\imgui already exists, skipping"
}

if (-not (Test-Path "$scriptDir\third_party\implot")) {
    Write-Host "==> Cloning ImPlot $IMPLOT_TAG"
    git clone --depth 1 --branch $IMPLOT_TAG https://github.com/epezent/implot.git "$scriptDir\third_party\implot"
} else {
    Write-Host "==> third_party\implot already exists, skipping"
}

# ── 4. CMake configure ───────────────────────────────────────────────────────
$toolchain = "$VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake"
Write-Host "==> CMake configure"
cmake -B "$scriptDir\build" `
      -S "$scriptDir" `
      "-DCMAKE_TOOLCHAIN_FILE=$toolchain" `
      -DVCPKG_TARGET_TRIPLET=x64-windows `
      -DCMAKE_BUILD_TYPE=Release

# ── 5. Build ─────────────────────────────────────────────────────────────────
Write-Host "==> Building (Release)"
cmake --build "$scriptDir\build" --config Release --parallel

Write-Host ""
Write-Host "Build complete!"
Write-Host "Run the terminal with:"
Write-Host "  .\build\Release\trading_terminal.exe ..\..\market_data.db"
