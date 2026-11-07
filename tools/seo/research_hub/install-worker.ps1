param(
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$DataDirectory = '',
    [switch]$Remove,
    [switch]$ReplaceExisting
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$entry = (Resolve-Path -LiteralPath (Join-Path $repoRoot 'tools/seo/launch.py')).Path
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$windowlessPython = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (Test-Path -LiteralPath $windowlessPython) { $pythonPath = (Resolve-Path -LiteralPath $windowlessPython).Path }
if (-not $DataDirectory) { $DataDirectory = Join-Path $repoRoot 'artifacts/seo-research' }
$researchData = (Resolve-Path -LiteralPath $DataDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $researchData 'config.private.json'))) {
    throw 'Initialize and review the local research configuration first.'
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$name = 'SEO Research Worker'
$arguments = '"' + $entry + '" --home "' + $researchData + '" daemon'
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    $matches = @($existing.Actions | Where-Object { $_.Execute -eq $pythonPath -and $_.Arguments -eq $arguments })
    if ($matches.Count -ne 1) {
        $owned = @($existing.Actions | Where-Object {
            $_.Arguments -match 'research_hub_app.py|tools[\\/]seo[\\/]launch.py' -and
            $_.Arguments.Contains($researchData)
        })
        if (-not $ReplaceExisting -or $owned.Count -ne 1 -or @($existing.Actions).Count -ne 1) {
            throw 'This task uses a different command. Review it and use -ReplaceExisting to migrate the existing SEO worker.'
        }
        Stop-ScheduledTask -TaskName $name
        $action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $repoRoot
        Set-ScheduledTask -TaskName $name -Action $action | Out-Null
    }
}
if ($Remove) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output 'Research worker startup removed. Stored evidence and queued jobs were preserved.'
    exit
}
# Register an ordinary owner process at sign-in, independently of MCP client lifetime.
# No password, elevated service account, recurring provider schedule or notifications.
if (-not $existing) {
    $action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $repoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -Hidden -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
}
Start-ScheduledTask -TaskName $name
Write-Output 'Independent research worker registered and started; provider collection follows the reviewed local configuration.'
