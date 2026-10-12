<##
Low-power, single-instance supervisor for the NVIDIA RGB formal cohort.

Safety contract:
  - never stops or kills an analysis process;
  - never starts a second cohort while any known cohort/stage process is alive;
  - only restarts the existing cohort runner after its process chain is gone;
  - keeps append-only supervisor logs and one log pair per restart attempt;
  - uses the normal resume behavior of run_rgb_formal_cohort.ps1;
  - never uses -Force and never changes the scientific parameters automatically.

This script is intentionally conservative around orphaned live stage processes:
it waits rather than trying to repair or terminate them.
##>

param(
    [string]$CudaDevice = "cuda",

    [int]$FaceBatch = 0,

    [int]$PollSeconds = 90,

    [int]$RetryDelaySeconds = 120,

    [int]$MaxRestarts = 5,

    [switch]$Once
)

$ErrorActionPreference = "Stop"

if ($PollSeconds -lt 30) { throw "PollSeconds must be at least 30 for low-power supervision." }
if ($RetryDelaySeconds -lt 30) { throw "RetryDelaySeconds must be at least 30." }
if ($MaxRestarts -lt 1) { throw "MaxRestarts must be positive." }
if ($CudaDevice -notmatch '^cuda(?::\d+)?$') {
    throw "CudaDevice must be cuda or cuda:<index>; got: $CudaDevice"
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$OutputRoot = "D:\Project\厚粲杯\11_数据\04_Attention-Analysis_nvidia-cuda_RGB"
$InventoryPath = Join-Path $OutputRoot "rgb_inventory.csv"
$SupervisorDir = Join-Path $OutputRoot "_supervisor"
$SupervisorLog = Join-Path $SupervisorDir "rgb_cohort_supervisor.log"
$StatePath = Join-Path $SupervisorDir "rgb_cohort_supervisor_state.json"
$CohortScript = Join-Path $RepoRoot "scripts\run_rgb_formal_cohort.ps1"

New-Item -ItemType Directory -Force -Path $SupervisorDir | Out-Null

# A named mutex is released by Windows if this supervisor is terminated.
$mutex = New-Object System.Threading.Mutex($false, "Local\AttentionAnalysisRgbNvidiaCohortSupervisor")
if (-not $mutex.WaitOne(0)) {
    throw "Another RGB cohort supervisor is already running; no action taken."
}

function Write-SupervisorLog {
    param([string]$Message)
    $line = "{0} {1}" -f ([DateTime]::UtcNow.ToString("o")), $Message
    Add-Content -LiteralPath $SupervisorLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Save-State {
    param(
        [int]$Restarts,
        [string]$LastEvent,
        [string]$LastExitCode,
        [string]$Mode
    )
    $state = [ordered]@{
        schema_version = "rgb-cohort-supervisor-v1"
        updated_utc = [DateTime]::UtcNow.ToString("o")
        mode = $Mode
        restarts = $Restarts
        max_restarts = $MaxRestarts
        poll_seconds = $PollSeconds
        retry_delay_seconds = $RetryDelaySeconds
        cuda_device = $CudaDevice
        face_batch = $(if ($FaceBatch -gt 0) { $FaceBatch } else { $null })
        last_event = $LastEvent
        last_exit_code = $LastExitCode
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

function Get-ActiveRgbProcess {
    $patterns = @(
        "run_rgb_formal_cohort\.ps1",
        "run_rgb_formal_subject\.ps1",
        "rgb_formal_motion_pose\.py",
        "face_formal_prepare\.py",
        "face_formal_cuda\.py",
        "rgb_formal_validate\.py"
    )
    $regex = ($patterns -join "|")
    $selfPid = $PID
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $selfPid -and
        $_.CommandLine -and
        $_.CommandLine -match $regex
    })
}

function Test-EligibleWorkRemaining {
    if (-not (Test-Path -LiteralPath $InventoryPath -PathType Leaf)) {
        return $true
    }
    $inventory = @(Import-Csv -LiteralPath $InventoryPath | Where-Object { $_.analysis_eligible -eq "True" })
    if ($inventory.Count -eq 0) { return $false }
    foreach ($row in $inventory) {
        $subject = $row.subject
        $manifest = Join-Path $OutputRoot "$subject\$subject`_manifest.json"
        if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { return $true }
        try {
            $data = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($data.completion_status -ne "complete" -or $data.extraction_complete -ne $true) {
                return $true
            }
        }
        catch {
            return $true
        }
    }
    return $false
}

function Start-CohortAttempt {
    param([int]$AttemptNumber)
    $stamp = [DateTime]::Now.ToString("yyyyMMdd-HHmmss")
    $stdout = Join-Path $SupervisorDir "$stamp-cohort.stdout.log"
    $stderr = Join-Path $SupervisorDir "$stamp-cohort.stderr.log"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $CohortScript,
        "-CudaDevice", $CudaDevice
    )
    if ($FaceBatch -gt 0) { $args += @("-FaceBatch", "$FaceBatch") }
    Write-SupervisorLog "Starting cohort attempt=$AttemptNumber; logs=$stdout,$stderr"
    return Start-Process -FilePath "pwsh.exe" -ArgumentList $args -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -NoNewWindow -PassThru
}

try {
    $restartCount = 0
    Save-State $restartCount "started" "" "monitoring"
    Write-SupervisorLog "Started; poll=${PollSeconds}s; retry_delay=${RetryDelaySeconds}s; max_restarts=$MaxRestarts"

    while ($true) {
        $active = @(Get-ActiveRgbProcess)
        if ($active.Count -gt 0) {
            $names = @($active | ForEach-Object { "{0}:{1}" -f $_.ProcessId, $_.Name }) -join ","
            Save-State $restartCount "active_processes=$names" "" "monitoring"
            if ($Once) {
                Write-SupervisorLog "Once check: active RGB process chain detected; no action taken."
                break
            }
            Start-Sleep -Seconds $PollSeconds
            continue
        }

        if (-not (Test-EligibleWorkRemaining)) {
            Save-State $restartCount "cohort_complete" "0" "complete"
            Write-SupervisorLog "All eligible subject manifests are complete; supervisor exiting without starting a process."
            break
        }

        if ($Once) {
            Save-State $restartCount "work_remaining_no_process" "" "idle"
            Write-SupervisorLog "Once check: work remains but no RGB process is active; no process started."
            break
        }

        if ($restartCount -ge $MaxRestarts) {
            Save-State $restartCount "restart_limit_reached" "" "blocked"
            Write-SupervisorLog "Restart limit reached; supervisor is stopping without killing or changing any process."
            break
        }

        # Close the small race between the first process scan and launch.
        $activeBeforeLaunch = @(Get-ActiveRgbProcess)
        if ($activeBeforeLaunch.Count -gt 0) {
            Write-SupervisorLog "A RGB process appeared before launch; no second cohort started."
            Start-Sleep -Seconds $PollSeconds
            continue
        }

        $restartCount++
        $proc = Start-CohortAttempt $restartCount
        Save-State $restartCount "cohort_started_pid=$($proc.Id)" "" "running"

        while (-not $proc.HasExited) {
            Start-Sleep -Seconds $PollSeconds
            $proc.Refresh()
        }
        $proc.Refresh()
        $exitCode = "$($proc.ExitCode)"
        if ($proc.ExitCode -eq 0) {
            Write-SupervisorLog "Cohort runner exited 0; checking manifests before deciding whether to exit or resume."
            Save-State $restartCount "cohort_exit_0" $exitCode "checking"
        }
        else {
            Write-SupervisorLog "Cohort runner exited code=$exitCode; original runner logs retained; waiting before resume."
            Save-State $restartCount "cohort_exit_nonzero" $exitCode "backoff"
        }

        if (Test-EligibleWorkRemaining) {
            Write-SupervisorLog "Work remains; sleeping ${RetryDelaySeconds}s before the next single-runner attempt."
            Start-Sleep -Seconds $RetryDelaySeconds
        }
        else {
            Save-State $restartCount "cohort_complete_after_attempt" $exitCode "complete"
            Write-SupervisorLog "All eligible subject manifests are complete after this attempt; supervisor exiting."
            break
        }
    }
}
finally {
    if ($mutex) {
        $mutex.ReleaseMutex() | Out-Null
        $mutex.Dispose()
    }
}
