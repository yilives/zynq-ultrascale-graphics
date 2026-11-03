param([string]$VitisBin='F:\AMDXilinx\2026.1\Vitis\bin', [switch]$Java120)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$buildRoot=[IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
# Vitis GCC dependency-file names can exceed Windows MAX_PATH in this project.
# R: is a reversible alias of this project's build directory, never another disk.
$maps=& subst
if(Test-Path -LiteralPath 'R:\') {
    $expected='R:\: => '+$buildRoot
    if($maps -notcontains $expected) {throw 'R: is occupied; choose a free build alias before running Vitis'}
} else {
    & subst R: $buildRoot
    if($LASTEXITCODE) {throw 'Cannot establish project build alias R:'}
}
$environmentNames=@('RIX_VITIS_WORKSPACE','RIX_VITIS_XSA','RIX_VITIS_WORKSPACE_DIR','RIX_VITIS_REPORT','RIX_VITIS_PS_INIT_REFERENCE')
$previousEnvironment=@{}
foreach($name in $environmentNames) {$previousEnvironment[$name]=[Environment]::GetEnvironmentVariable($name)}
try {
    $env:RIX_VITIS_WORKSPACE='R:/vws'
    if($Java120) {
        $candidate=Join-Path $buildRoot 'java256-fold16-split-120'
        $env:RIX_VITIS_XSA=Join-Path $candidate 'java256-fold16.xsa'
        if(-not (Test-Path -LiteralPath $env:RIX_VITIS_XSA -PathType Leaf)) {
            throw 'Build and sign off the Java 120 MHz hardware first'
        }
        $env:RIX_VITIS_WORKSPACE='R:/j12v'
        $env:RIX_VITIS_WORKSPACE_DIR=Join-Path $buildRoot 'j12v'
        $env:RIX_VITIS_REPORT=Join-Path $candidate 'vitis-boot-artifacts.json'
        $env:RIX_VITIS_PS_INIT_REFERENCE=Join-Path $buildRoot 'j12c/rix_java256_fold16.gen/sources_1/bd/rasterix_system/ip/rasterix_system_ps_0/psu_init.c'
    }
    & "$VitisBin\vitis.bat" -s (Join-Path $PSScriptRoot 'create_vitis_platform.py')
    if($LASTEXITCODE) {throw 'Vitis boot platform failed'}
} finally {
    foreach($name in $environmentNames) {[Environment]::SetEnvironmentVariable($name,$previousEnvironment[$name])}
}
