# dazzlelink_association.ps1

# Path to your Python interpreter and script
$pythonPath = (Get-Command python).Source
$dazzleLinkScript = Join-Path $PWD "dazzlelink.py"

# Create file association in registry
$fileType = ".dazzlelink"
$progId = "DazzleLinkFile"

# Create ProgID
New-Item -Path "HKCU:\Software\Classes\$progId" -Force
Set-ItemProperty -Path "HKCU:\Software\Classes\$progId" -Name "(Default)" -Value "Dazzlelink Symbolic Link"

# Create shell open command
New-Item -Path "HKCU:\Software\Classes\$progId\shell\open\command" -Force
$command = "`"$pythonPath`" `"$dazzleLinkScript`" execute `"%1`""
Set-ItemProperty -Path "HKCU:\Software\Classes\$progId\shell\open\command" -Name "(Default)" -Value $command

# Associate .dazzlelink extension with ProgID
New-Item -Path "HKCU:\Software\Classes\$fileType" -Force
Set-ItemProperty -Path "HKCU:\Software\Classes\$fileType" -Name "(Default)" -Value $progId

Write-Host "Dazzlelink file association created successfully!"