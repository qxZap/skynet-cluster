<#
Launch a POOL of real opencode workers that wait for work.

Each worker is a persistent daemon (scripts/worker_daemon.py) that parks on the
cluster's SSE event stream and wakes a real `opencode run` whenever a task matching
its skills appears — event-driven, no polling. They keep running until you stop them.

  ./scripts/launch-workers.ps1            # 3 workers, waiting
  ./scripts/seed.ps1                      # ...then drop work; the pool reacts

  Get-Job | Receive-Job -Keep             # see worker output
  Get-Job | Stop-Job; Get-Job | Remove-Job   # stop the pool

Prereqs: cluster running (docker compose up -d), python+httpx, opencode logged
into the model.
#>
param(
  [string]$ClusterUrl = "http://localhost:8080",
  [string]$Model = "minimax-coding-plan/MiniMax-M3"
)

$WorkerDir = (Join-Path $PSScriptRoot "..\workers\opencode" | Resolve-Path).Path
$Daemon    = (Join-Path $PSScriptRoot "worker_daemon.py" | Resolve-Path).Path
$Config    = (Join-Path $WorkerDir "opencode.jsonc")

$roles = @(
  @{ id="wkr-architect"; name="Architect"; skills="architecture,reasoning,review";
     persona="a pragmatic senior architect who plans before building and delegates implementation" },
  @{ id="wkr-coder";     name="Coder";     skills="coding,debugging,refactoring";
     persona="a fast, concrete implementer who writes the actual code" },
  @{ id="wkr-muse";      name="Muse";      skills="brainstorming,writing,naming";
     persona="a creative thinker who names things and pitches ideas" }
)

foreach ($r in $roles) {
  Start-Job -Name $r.name -ScriptBlock {
    param($role, $clusterUrl, $model, $daemon, $config)
    $env:CLUSTER_URL = $clusterUrl
    $env:WORKER_MODEL = $model
    $env:OPENCODE_CONFIG = $config
    python $daemon --name $role.name --id $role.id --skills $role.skills --persona $role.persona 2>&1
  } -ArgumentList $r, $ClusterUrl, $Model, $Daemon, $Config | Out-Null
  Write-Host "waiting worker up: $($r.name) ($($r.id)) [$($r.skills)]"
}

Write-Host "`nPool is parked on $ClusterUrl, waiting for work."
Write-Host "Seed a task:   ./scripts/seed.ps1"
Write-Host "See output:    Get-Job | Receive-Job -Keep"
Write-Host "Stop the pool: Get-Job | Stop-Job; Get-Job | Remove-Job"
