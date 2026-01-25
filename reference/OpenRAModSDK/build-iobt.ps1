$env:PATH = "C:\Program Files\dotnet;" + $env:PATH
Set-Location $PSScriptRoot
& .\make.ps1 all
