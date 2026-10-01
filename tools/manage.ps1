param(
    [ValidateSet('状态','导入账单','复验','应用配置','受控重启','恢复配置','恢复台账')]
    [string]$操作 = '状态',
    [string]$设置 = (Join-Path $PSScriptRoot '..\local\optimization\settings.yaml'),
    [switch]$确认新账期
)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$repo = Split-Path $PSScriptRoot -Parent
$python = (Get-Command python -ErrorAction Stop).Source
$watch = Join-Path $PSScriptRoot 'watch.py'
$taskName = & $python -c "import sys,yaml;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8-sig'))['runtime'].get('task',''))" $设置
if ($LASTEXITCODE -ne 0) { throw '读取本机设置失败' }
if ($操作 -eq '状态') {
    $raw = & $python $watch status --settings $设置
    if ($LASTEXITCODE -ne 0) { throw '读取台账状态失败' }
    $state = $raw | ConvertFrom-Json
    $running = if ($taskName -and (Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { '正在运行' } else { '未由计划任务运行' }
    $recent = if ($state.heartbeat_recent) { '是' } else { '否' }
    $errorLabel = if ($state.error) { $state.error } else { '无' }
    $modeLabel = @{ rule='规则'; global='全局'; direct='直连' }[$state.mode]
    Write-Host ('当前模式：' + $modeLabel)
    Write-Host ('后台任务：{0}；最近有记录：{1}；错误：{2}' -f $running, $recent, $errorLabel)
    foreach ($source in $state.budgets.PSObject.Properties) {
        $b = $source.Value
        $label = if ($source.Name -eq 'primary') { 'TAG' } else { '奶昔' }
        $remaining = ($b.threshold_bytes - $b.baseline_bytes - $b.upper_bound_bytes) / 1GB
        $lockLabel = if ($b.blocked) { '已锁定' } else { '未锁定' }
        Write-Host ('{0}：账单 {1:N2} GiB，追加保守估算 {2:N2} GiB，距保护阈值 {3:N2} GiB；{4}' -f $label, ($b.baseline_bytes/1GB), ($b.upper_bound_bytes/1GB), $remaining, $lockLabel)
        Write-Host ('  账单收到时间：{0}；锁定原因：{1}' -f $b.billing_observed_at, $b.blocked_reason)
    }
    if ($state.pending_reason) { Write-Host ('待更新：' + $state.pending_reason) }
    foreach ($service in $state.services.PSObject.Properties) {
        $business = if ($service.Value.business -eq 'passed') { '已通过' } else { '待验收' }
        $available = if ($null -eq $service.Value.available) { '待确认' } elseif ($service.Value.available) { '可用' } else { '无合格线路' }
        if ($service.Value.manual) { $available = '手动选择，业务待确认' }
        $sourceLabel = @{ primary='TAG'; bulk='奶昔' }[[string]$service.Value.source]
        if (-not $sourceLabel) { $sourceLabel = '待确认' }
        $expiry = if ($service.Value.checked_at) { ([DateTimeOffset]::Parse($service.Value.checked_at)).AddHours(72).ToLocalTime().ToString('MM-dd HH:mm') } else { '待确认' }
        Write-Host ('{0}：{1}；来源 {2}；出口 {3}；备用 {4} 个；{5}；业务{6}；出口证据到期 {7}' -f $service.Name, $service.Value.current, $sourceLabel, $service.Value.exit_country, $service.Value.backup_count, $available, $business, $expiry)
    }
    exit 0
}
$modes = @{ '导入账单'='import-local-billing'; '复验'='recheck'; '应用配置'='apply-pending'; '受控重启'='controlled-restart'; '恢复配置'='restore'; '恢复台账'='recover-ledger' }
$wasRunning = $false
if ($taskName) {
    $task = Get-ScheduledTask -TaskName $taskName
    $wasRunning = $task.State -eq 'Running'
    if ($wasRunning) {
        Stop-ScheduledTask -TaskName $taskName
        for ($attempt=0; $attempt -lt 20; $attempt++) {
            if ((Get-ScheduledTask -TaskName $taskName).State -ne 'Running') { break }
            Start-Sleep -Milliseconds 250
        }
        if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { throw '后台尚未退出，停止台账修改' }
    }
}
try {
    $arguments = @($watch, $modes[$操作], '--settings', $设置)
    if ($确认新账期) { $arguments += '--confirm-cycle' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw ('操作失败：' + $操作) }
    Write-Host ('已完成：' + $操作)
} finally {
    if ($wasRunning) { Start-ScheduledTask -TaskName $taskName }
}
