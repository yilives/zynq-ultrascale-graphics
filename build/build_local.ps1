param([switch]$RebuildHardware,[switch]$PackageOnly,[string]$Distro='Ubuntu')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$projectRoot=$PSScriptRoot
Set-Location $projectRoot
$linuxRoot='/mnt/'+$projectRoot.Substring(0,1).ToLower()+($projectRoot.Substring(2) -replace '\\','/')
function Run-Linux([string]$script,[switch]$AsRoot) {
    if($AsRoot) {& wsl -d $Distro --user root --exec bash "$linuxRoot/scripts/$script"}
    else {& wsl -d $Distro --exec bash "$linuxRoot/scripts/$script"}
    if($LASTEXITCODE) {throw "Linux build failed: $script"}
}
if($RebuildHardware -and $PackageOnly) {throw 'Choose a complete rebuild or package reuse'}
if($RebuildHardware) {& .\build.ps1 -Action board}
if(-not (Test-Path build\rasterix_linux.xsa)) {throw 'Build hardware first with -RebuildHardware'}
if(-not $PackageOnly) {
$configuration=(Get-Content -LiteralPath generated\config.sha256 -Raw).Trim()
if(-not (Test-Path -LiteralPath build\top_ooc\checks.txt) -or -not (Select-String -LiteralPath build\top_ooc\checks.txt -SimpleMatch $configuration -Quiet)) {
    & F:\AMDXilinx\2026.1\Vivado\bin\vivado.bat -mode batch -nolog -nojournal -source scripts\top_ooc.tcl *> report\blocker_fix_ooc_console.log
    if($LASTEXITCODE) {throw 'Current-configuration OOC synthesis failed'}
}
& F:\AMDXilinx\2026.1\Vivado\bin\vivado.bat -mode batch -nolog -nojournal -source scripts\inspect_routed.tcl *> report\routed_review_final_console.log
if($LASTEXITCODE) {throw 'Routed timing/CDC review failed'}
& scripts\generate_sdt.ps1
& scripts\build_vitis.ps1
Run-Linux 'test_dma_initialization.sh'
& wsl -d $Distro --exec python3 "$linuxRoot/scripts/record_dma_initialization.py"
if($LASTEXITCODE) {throw 'DMA initialization regression failed'}
& wsl -d $Distro --exec python3 "$linuxRoot/scripts/test_display_layout.py"
if($LASTEXITCODE) {throw 'LCD layout regression failed'}
Run-Linux 'use_vendor_sdk.sh'
Run-Linux 'build_vendor_kernel.sh'
Run-Linux 'build_dtb.sh'
Run-Linux 'build_tfa.sh'
Run-Linux 'build_uboot.sh'
Run-Linux 'build_x11_dummy.sh'
Run-Linux 'build_rootfs.sh' -AsRoot
}
& wsl -d $Distro --user root --exec python3 "$linuxRoot/scripts/check_rootfs.py"
if($LASTEXITCODE) {throw 'Rootfs validation failed'}
& scripts\package_boot.ps1
& wsl -d $Distro --exec python3 "$linuxRoot/scripts/build_sd_image.py"
if($LASTEXITCODE) {throw 'SD image assembly failed'}
& python scripts\release_manifest.py --require-complete
if($LASTEXITCODE) {throw 'Release manifest failed'}
Write-Output 'LOCAL_BUILD_COMPLETE: inspect physical acceptance evidence separately'
