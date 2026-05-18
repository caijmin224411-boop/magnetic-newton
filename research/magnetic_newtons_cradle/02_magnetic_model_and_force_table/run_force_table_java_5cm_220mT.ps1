$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Java = "D:\COMSOL63\Multiphysics\java\win64\jre\bin\java.exe"
$Source = Join-Path $Here "DiskMagnetForceTable.java"
$Out = Join-Path $Here "force_table_5cm_220mT_disk_2d.csv"

& $Java $Source `
  0.0150 `
  0.0250 `
  0.5131237667 `
  0.0005 `
  0.0700 `
  76 `
  0.0600 `
  31 `
  9 `
  48 `
  $Out

Write-Host "Force table written to $Out"
