# Run once to clone ImGui and ImPlot into third_party/
# Requires git. Run from the visualiser/ directory.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$IMPLOT_TAG = "v0.17"

# Must use the 'docking' branch — standard release tags don't include DockSpace/viewports
Write-Host "==> Cloning Dear ImGui (docking branch)"
git clone --depth 1 --branch docking https://github.com/ocornut/imgui.git third_party/imgui

Write-Host "==> Cloning ImPlot $IMPLOT_TAG"
git clone --depth 1 --branch $IMPLOT_TAG https://github.com/epezent/implot.git third_party/implot

Write-Host ""
Write-Host "Done. Now install vcpkg packages:"
Write-Host "  vcpkg install glfw3 sqlite3 opengl"
Write-Host ""
Write-Host "Then configure & build:"
Write-Host "  cmake -B build -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake"
Write-Host "  cmake --build build --config Release"
