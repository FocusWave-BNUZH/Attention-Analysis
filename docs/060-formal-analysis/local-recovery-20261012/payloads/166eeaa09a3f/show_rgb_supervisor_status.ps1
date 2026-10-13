param(
    [int]$RefreshSeconds = 30
)

$ErrorActionPreference = "SilentlyContinue"
$OutputRoot = "D:\Project\厚粲杯\11_数据\04_Attention-Analysis_nvidia-cuda_RGB"
$InventoryPath = Join-Path $OutputRoot "rgb_inventory.csv"
$StatusPath = Join-Path $OutputRoot "cohort_status.csv"
$StatePath = Join-Path $OutputRoot "_supervisor\rgb_cohort_supervisor_state.json"

function Get-StageState {
    param([string]$Subject, [string]$Stage)
    $manifest = switch ($Stage) {
        "Motion" { Join-Path $OutputRoot "$Subject\$Subject`_motion_manifest.json" }
        "Pose" { Join-Path $OutputRoot "$Subject\$Subject`_pose_manifest.json" }
        "Face" { Join-Path $OutputRoot "$Subject\$Subject`_face_raw_manifest.json" }
    }
    if (-not (Test-Path -LiteralPath $manifest)) { return "未开始" }
    try {
        $j = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($j.completion_status -eq "complete") { return "已完成" }
        return "处理中"
    } catch { return "处理中" }
}

function Show-Status {
    Clear-Host
    $now = Get-Date
    $inventory = @(Import-Csv -LiteralPath $InventoryPath | Where-Object { $_.analysis_eligible -eq "True" })
    $status = @(Import-Csv -LiteralPath $StatusPath)
    $complete = @($status | Where-Object status -eq "complete").Count
    $skipped = @($status | Where-Object status -eq "skipped_complete").Count
    $failed = @($status | Where-Object status -eq "failed").Count
    $terminal = @($status | Where-Object status -in @("complete", "skipped_complete"))
    $terminalIds = @($terminal.subject)

    $active = @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -match "run_rgb_formal_cohort|run_rgb_formal_subject|rgb_formal_motion_pose|face_formal_cuda"
    })
    $subjectIds = @()
    foreach ($p in $active) {
        if ($p.CommandLine -match "--subject\s+(sub-\d+)") { $subjectIds += $Matches[1] }
    }
    $subjectIds = @($subjectIds | Sort-Object -Unique)
    $running = if ($subjectIds.Count -gt 0) { $subjectIds -join ", " } else { "没有检测到正在运行的被试" }

    $remainingIds = @($inventory.subject | Where-Object { $_ -notin $terminalIds -and $_ -notin $subjectIds } | Sort-Object)
    $progress = if ($inventory.Count -gt 0) { [math]::Round(($complete + $skipped) * 100 / $inventory.Count, 1) } else { 0 }

    $supervisor = "未检测到"
    $restart = "未知"
    if (Test-Path -LiteralPath $StatePath) {
        try {
            $s = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $supervisor = switch ($s.mode) {
                "monitoring" { "正常监控" }
                "running" { "正在运行 cohort" }
                "complete" { "已完成" }
                "blocked" { "已暂停：达到重试上限" }
                default { $s.mode }
            }
            $restart = "$($s.restarts) / $($s.max_restarts)"
        } catch { $supervisor = "状态文件读取中" }
    }

    Write-Host "RGB NVIDIA 分析中文状态窗口" -ForegroundColor Cyan
    Write-Host "更新时间：$($now.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host ""
    Write-Host "监督器：$supervisor"
    Write-Host "自动重启次数：$restart"
    Write-Host "当前运行：$running"
    Write-Host ""
    Write-Host ("总体进度：{0} / {1} 人（{2}%）" -f ($complete + $skipped), $inventory.Count, $progress)
    Write-Host ("实际完成：{0} 人    已有结果跳过：{1} 人    失败：{2} 人" -f $complete, $skipped, $failed)
    Write-Host ("等待开始：{0} 人" -f $remainingIds.Count)
    Write-Host ""

    foreach ($subject in $subjectIds) {
        Write-Host "当前被试 $subject：Motion=$(Get-StageState $subject 'Motion')，Pose=$(Get-StageState $subject 'Pose')，Face=$(Get-StageState $subject 'Face')" -ForegroundColor Yellow
    }
    if ($failed -gt 0) {
        Write-Host "失败被试：$(@($status | Where-Object status -eq 'failed' | ForEach-Object subject) -join ', ')" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "窗口每 $RefreshSeconds 秒刷新；按 Ctrl+C 可关闭窗口，不会停止分析。" -ForegroundColor DarkGray
}

while ($true) {
    Show-Status
    Start-Sleep -Seconds $RefreshSeconds
}
