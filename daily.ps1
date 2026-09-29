<#
.SYNOPSIS
    Ejecuta la actualización diaria del SVG de perfil y realiza commit & push.
.DESCRIPTION
    Script local para actualizar Uptime, Age y estadísticas de GitHub en img/CodeMe.svg,
    creando un commit diario y subiendo los cambios a GitHub.
.EXAMPLE
    .\daily.ps1
    .\daily.ps1 --dry-run
    .\daily.ps1 --no-push
#>

param(
    [switch]$DryRun,
    [switch]$NoPush,
    [switch]$Force
)

$argsList = @()
if ($DryRun) { $argsList += "--dry-run" }
if ($NoPush) { $argsList += "--no-push" }
if ($Force) { $argsList += "--force" }

python "$PSScriptRoot\today.py" @argsList
