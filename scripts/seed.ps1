<# Drop a seed task into the cluster to kick off collaboration. #>
param(
  [string]$ClusterUrl = "http://localhost:8080",
  [string]$Title = "Design a URL shortener service",
  [string]$Description = "Propose the architecture for a small URL shortener (API endpoints, data model, how short codes are generated). Then get it implemented and give it a catchy name.",
  [string]$Skill = "architecture"
)
$body = @{ title=$Title; description=$Description; required_skill=$Skill } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "$ClusterUrl/tasks" -ContentType "application/json" -Body $body
Write-Host "seeded task $($r.id) (conversation $($r.conversation_id)) requiring skill '$Skill'"
