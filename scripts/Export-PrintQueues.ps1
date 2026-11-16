<#
.SYNOPSIS
    Exports the print queues of one or more Windows print servers to queues.csv for printfleet. Read-only.

.DESCRIPTION
    For every queue: server, name, share name, the address its port prints to, driver and driver version, status, jobs waiting and
    the age of the oldest job. Uses the PrintManagement module (Get-Printer, Get-PrinterPort, Get-PrinterDriver, Get-PrintJob); it
    changes nothing on the servers. Run it from a machine with the module, as a user who can read the print servers.

    devices.csv, supplies.csv and counters.csv come from your managed print portal or an SNMP scan (see docs/data-format.md for the
    columns); printers.csv is your printer register.

.EXAMPLE
    .\scripts\Export-PrintQueues.ps1 -PrintServers PRT-SRV01, PRT-SRV02 -OutputFolder .\data
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string[]] $PrintServers,
    [string] $OutputFolder = ".\data"
)

$ErrorActionPreference = "Stop"
Import-Module PrintManagement
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$now = Get-Date

function Format-DriverVersion([UInt64] $v) {
    # DriverVersion packs four 16-bit numbers: major.minor.build.revision
    "{0}.{1}.{2}.{3}" -f (($v -shr 48) -band 0xFFFF), (($v -shr 32) -band 0xFFFF), (($v -shr 16) -band 0xFFFF), ($v -band 0xFFFF)
}

$rows = foreach ($server in $PrintServers) {
    Write-Verbose "Reading $server"
    $ports = @{}
    Get-PrinterPort -ComputerName $server | ForEach-Object { $ports[$_.Name] = $_.PrinterHostAddress }
    $drivers = @{}
    Get-PrinterDriver -ComputerName $server | ForEach-Object { $drivers[$_.Name] = Format-DriverVersion $_.DriverVersion }
    foreach ($p in Get-Printer -ComputerName $server) {
        $jobs = @(Get-PrintJob -ComputerName $server -PrinterName $p.Name -ErrorAction SilentlyContinue)
        $oldest = 0
        if ($jobs.Count) {
            $first = ($jobs | Sort-Object SubmittedTime | Select-Object -First 1).SubmittedTime
            if ($first) { $oldest = [math]::Round(($now - $first).TotalMinutes) }
        }
        [pscustomobject]@{
            Server             = $server
            Name               = $p.Name
            ShareName          = $p.ShareName
            PrinterHostAddress = $ports[$p.PortName]
            DriverName         = $p.DriverName
            DriverVersion      = $drivers[$p.DriverName]
            PrinterStatus      = $p.PrinterStatus
            JobCount           = $jobs.Count
            OldestJobMinutes   = $oldest
        }
    }
}

$rows | Export-Csv -Path (Join-Path $OutputFolder "queues.csv") -NoTypeInformation -Encoding UTF8
Write-Host "queues.csv: $(@($rows).Count) queues from $($PrintServers -join ', ')"
