param([ValidateSet('check','hardware','package')][string]$Mode='check',[string]$VivadoBin='F:/AMDXilinx/2026.1/Vivado/bin')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
 if($Mode -ne 'package'){
  & python scripts/prepare_cnn_vectors.py
  if($LASTEXITCODE){throw 'Train/export both neural models first; see NEURAL_STYLE_2026-10-20.md'}
  & scripts/run_cnn_sim.ps1 -Full -VivadoBin $VivadoBin
  & scripts/run_postproc_sim.ps1 -VivadoBin $VivadoBin
  & scripts/run_scale5_full_sim.ps1 -VivadoBin $VivadoBin
  & scripts/run_frame_bridge_burst_sim.ps1 -VivadoBin $VivadoBin
  $wslRoot='/mnt/'+$root.Substring(0,1).ToLower()+($root.Substring(2) -replace '\\','/')
  & wsl -d Ubuntu --exec bash "$wslRoot/scripts/build_neural_style_cpu.sh"
  if($LASTEXITCODE){throw 'CNN CPU build/bit-exact comparison failed'}
 }
 if($Mode -eq 'hardware'){
  & "$VivadoBin/vivado.bat" -mode batch -source scripts/create_neural_style_board.tcl -notrace -log report/neural-style/board-create.log -journal report/neural-style/board-create.jou -tclargs board *> report/neural-style/board-create-console.log
  if($LASTEXITCODE){throw 'CNN independent board creation failed'}
  & "$VivadoBin/vivado.bat" -mode batch -source scripts/build_neural_style_board.tcl -notrace -log report/neural-style/board-build.log -journal report/neural-style/board-build.jou *> report/neural_style_build_console.log
  if($LASTEXITCODE){throw 'CNN whole-board implementation failed'}
  & wsl -d Ubuntu --exec python3 "$wslRoot/scripts/prepare_neural_style_dtb.py"
  if($LASTEXITCODE){throw 'CNN device tree failed'}
  & scripts/package_neural_style_boot.ps1
 }
 & python scripts/package_neural_style.py
 if($LASTEXITCODE){throw 'CNN runtime package failed'}
 Write-Output "NEURAL_STYLE_BUILD_COMPLETE mode=$Mode; no board write performed by this build entry"
}finally{Pop-Location}
