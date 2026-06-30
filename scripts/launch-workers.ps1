<#
Launch REAL opencode instances as cluster workers.

Each worker is a plain `opencode run` driving the cluster's MCP tools — no coded
harness. Workers run concurrently (one PowerShell job each) and sweep the cluster
several times so delegated child tasks get picked up.

  ./scripts/launch-workers.ps1                 # 3 default workers, 3 sweeps each
  ./scripts/launch-workers.ps1 -Rounds 5
  ./scripts/launch-workers.ps1 -ClusterUrl http://localhost:8080

Prereqs: cluster running (docker compose up -d), opencode logged into
minimax-coding-plan, MCP url in workers/opencode/opencode.jsonc reachable.
#>
param(
  [int]$Rounds = 3,
  [string]$ClusterUrl = "http://localhost:8080",
  [string]$Model = "minimax-coding-plan/MiniMax-M3"
)

$WorkerDir = Join-Path $PSScriptRoot "..\workers\opencode" | Resolve-Path
$ConfigPath = Join-Path $WorkerDir "opencode.jsonc"

# role -> stable id, skills, personality
$roles = @(
  @{ id="wkr-architect"; name="Architect"; skills="architecture,reasoning,review";
     persona="a pragmatic senior architect who plans before building and delegates implementation" },
  @{ id="wkr-coder";     name="Coder";     skills="coding,debugging,refactoring";
     persona="a fast, concrete implementer who writes the actual code" },
  @{ id="wkr-muse";      name="Muse";      skills="brainstorming,writing,naming";
     persona="a creative thinker who names things and pitches ideas" }
)

$jobs = @()
foreach ($r in $roles) {
  $jobs += Start-Job -Name $r.name -ScriptBlock {
    param($role, $rounds, $model, $workerDir, $configPath)
    $env:OPENCODE_CONFIG = $configPath
    Set-Location $workerDir
    $prompt = @"
You are '$($role.name)', a worker in a distributed AI cluster.
Your skills: $($role.skills). Personality: $($role.persona).
Follow the protocol in AGENTS.md exactly. When you call register_worker, pass
worker_id='$($role.id)', name='$($role.name)', skills as a list of your skills,
and your personality. Then run the loop: claim and complete every open task that
matches your skills, delegating sub-tasks to other skills when needed. Stop when
no open task matches your skills.
"@
    for ($i = 1; $i -le $rounds; $i++) {
      Write-Output "=== $($role.name) sweep $i/$rounds ==="
      opencode run -m $model --dangerously-skip-permissions $prompt 2>&1
    }
  } -ArgumentList $r, $Rounds, $Model, $WorkerDir.Path, $ConfigPath.Path
  Write-Host "launched $($r.name) ($($r.id))"
}

Write-Host "`nWorkers running as jobs. Stream output with:  Receive-Job -Name Architect -Wait"
Write-Host "Watch the cluster:  curl $ClusterUrl/events  |  curl $ClusterUrl/tasks"
Write-Host "Waiting for all workers to finish...`n"
$jobs | Wait-Job | Out-Null
foreach ($j in $jobs) { Write-Host "----- $($j.Name) -----"; Receive-Job $j }
$jobs | Remove-Job
