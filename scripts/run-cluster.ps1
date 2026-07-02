<#
Run the cluster WITHOUT Docker.

It's a single Python process (~30 MB RAM, SQLite file on disk) — on Windows this
avoids Docker Desktop's WSL2 VM, which reserves ~2 GB of system memory no matter
how small the container is. Use this for day-to-day; use `docker compose up` only
if you specifically want it isolated in a container.

  ./scripts/run-cluster.ps1            # http://localhost:8080  (Ctrl+C to stop)
#>
param([int]$Port = 8080)
$Root = (Join-Path $PSScriptRoot ".." | Resolve-Path).Path
python -m pip install -q -r (Join-Path $Root "cluster/requirements.txt")
Push-Location $Root
try { python -m uvicorn cluster.app:app --host 0.0.0.0 --port $Port }
finally { Pop-Location }
