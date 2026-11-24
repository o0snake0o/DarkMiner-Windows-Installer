# DarkMiner for Windows

DarkMiner is an opt-in desktop controller for XMRig.

## Windows installation
Run DarkMiner-Setup-0.3.exe, complete the installation,
then open DarkMiner from the Start Menu.

Enter your own public Monero receiving address, mining pool,
and desired CPU thread count. Mining starts only when you
select START MINING.

## Build
Run build-win.ps1 on Windows with Python 3.12 and Inno
Setup 6, or use the included GitHub Actions workflow.

The build downloads XMRig from the official GitHub release,
verifies its SHA256 hash against the published SHA256SUMS,
and bundles it with the application.

## Safety
No automatic startup, hidden mining, service installation,
or unattended CPU mining is configured.

Use only hardware that you own or are authorized to use.
Never enter a wallet seed phrase or private key.
