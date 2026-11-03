param(
 [ValidateSet('prepare','check','candidate','board','postproc','neural','classicube','arm','launcher')][string]$Action='check',
 [string]$VivadoBin='F:\AMDXilinx\2026.1\Vivado\bin'
)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
Push-Location $PSScriptRoot
try {
 if($Action -eq 'launcher') {
  & scripts/build_launcher_library.ps1
  return
 }
 if($Action -eq 'arm') {
  $wslRoot='/mnt/'+$PSScriptRoot.Substring(0,1).ToLower()+($PSScriptRoot.Substring(2) -replace '\\','/')
  & wsl -d Ubuntu --exec bash "$wslRoot/scripts/build_java_arm_mainline_r1.sh"
  if($LASTEXITCODE) {throw 'ARM frontend mainline verification/relink failed'}
  return
 }
 if($Action -eq 'classicube') {
  & python scripts/fetch_classicube.py
  if($LASTEXITCODE) {throw 'ClassiCube source/assets verification failed'}
  $wslRoot='/mnt/'+$PSScriptRoot.Substring(0,1).ToLower()+($PSScriptRoot.Substring(2) -replace '\\','/')
  & wsl -d Ubuntu --exec bash "$wslRoot/scripts/build_classicube.sh"
  if($LASTEXITCODE) {throw 'ClassiCube AArch64 build failed'}
  & python scripts/package_classicube.py
  if($LASTEXITCODE) {throw 'ClassiCube packaging failed'}
  return
 }
 if($Action -eq 'neural') {
  & scripts/build_neural_style.ps1 -Mode hardware -VivadoBin $VivadoBin
  return
 }
 if($Action -eq 'postproc') {
  & scripts/build_postproc_touch.ps1 -VivadoBin $VivadoBin
  return
 }
 & python scripts/generate_config.py
 if($LASTEXITCODE) {throw 'Configuration failed'}
 & python scripts/prepare_sources.py
 if($LASTEXITCODE) {throw 'Source preparation failed'}
 & python scripts/generate_top.py
 if($LASTEXITCODE) {throw 'Top generation failed'}
 & python scripts/inspect_game.py
 if($LASTEXITCODE) {throw 'API inventory failed'}
 if($Action -eq 'check') {
  & scripts/run_sim.ps1 -VivadoBin $VivadoBin
  & scripts/run_gpu_sim.ps1 -VivadoBin $VivadoBin
  & "$VivadoBin/vivado.bat" -mode batch -nolog -nojournal -source scripts/top_ooc.tcl
  if($LASTEXITCODE) {throw 'Top synthesis failed'}
 }
 if($Action -in @('candidate','board')) {
  & "$VivadoBin/vivado.bat" -mode batch -nolog -nojournal -source scripts/create_board.tcl -tclargs $Action
  if($LASTEXITCODE) {throw 'Board project failed'}
 }
 if($Action -eq 'board') {
  & python scripts/generate_linux.py
  if($LASTEXITCODE) {throw 'Linux board generation failed'}
  & "$VivadoBin/vivado.bat" -mode batch -nolog -nojournal -source scripts/build_board.tcl
  if($LASTEXITCODE) {throw 'Board implementation/export failed'}
 }
 & python scripts/release_manifest.py
 if($LASTEXITCODE) {throw 'Manifest generation failed'}
} finally {Pop-Location}
