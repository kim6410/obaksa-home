param(
  [string]$OutputDirectory = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$timestamp = Get-Date -Format 'yyyyMMdd_HHmm'
$zipName = "obaksa-home_release_$timestamp.zip"
$zipPath = Join-Path $OutputDirectory $zipName
$tempRoot = Join-Path $env:TEMP ("obaksa-home-release-" + [Guid]::NewGuid().ToString('N'))
$stageRoot = Join-Path $tempRoot 'package'

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

$excludeNames = @(
  '.git',
  '.gitignore',
  '.vscode',
  'node_modules',
  '__MACOSX',
  '.DS_Store'
)

function Should-ExcludePath {
  param([string]$RelativePath)

  $normalized = $RelativePath -replace '\\','/'
  $leaf = Split-Path -Path $RelativePath -Leaf

  if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }
  foreach ($name in $excludeNames) {
    if ($normalized -eq $name) { return $true }
    if ($normalized.StartsWith($name + '/')) { return $true }
    if ($leaf -eq $name) { return $true }
  }

  if ($leaf -like '*.bak' -or $leaf -like '*.tmp' -or $leaf -like '*.log') { return $true }

  return $false
}

Get-ChildItem -LiteralPath $root -Force | ForEach-Object {
  $relative = $_.Name
  if (Should-ExcludePath -RelativePath $relative) { return }

  $destination = Join-Path $stageRoot $relative
  if ($_.PSIsContainer) {
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
  }
  else {
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
  }
}

if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $stageRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item -LiteralPath $tempRoot -Recurse -Force

Write-Host "Created release ZIP: $zipPath"
