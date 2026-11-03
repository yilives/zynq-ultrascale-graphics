$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$out=Join-Path $root 'build/minecraft-java-125/dual-tmu'
Set-Location -LiteralPath $root
& 'F:/AMDXilinx/2026.1/Vivado/bin/vivado.bat' -mode batch -source scripts/create_java256_dual.tcl -log "$out/create.log" -journal "$out/create.jou" -tclargs board
if($LASTEXITCODE){throw 'Dual-TMU block design creation failed'}
& 'F:/AMDXilinx/2026.1/Vivado/bin/vivado.bat' -mode batch -source scripts/implement_java256_dual.tcl -log "$out/implement.log" -journal "$out/implement.jou"
if($LASTEXITCODE){throw 'Dual-TMU implementation failed'}
