
from pathlib import Path

root = Path(__file__).resolve().parent

# 1. Connect the account interface to DarkMiner.
app = root / "darkminer.py"
code = app.read_text()

anchor = 'if __name__ == "__main__":'

if "class LicensedDarkMiner(" not in code:
    if anchor not in code:
        raise SystemExit("Main entry point not found")

    addition = '''
from licensing_ui import LicensedMinerMixin

class LicensedDarkMiner(LicensedMinerMixin, DarkMiner):
    pass


'''
    code = code.replace(anchor, addition + anchor)

if "window = DarkMiner()" in code:
    code = code.replace(
        "window = DarkMiner()",
        "window = LicensedDarkMiner()"
    )
elif "window = LicensedDarkMiner()" not in code:
    raise SystemExit("Window creation not recognized")

app.write_text(code)

# 2. Configure the license API at build time.
build = root / "build-win.ps1"
code = build.read_text()

marker = '$PyInstallerArgs = @('

config = r'''
# Public customer API URL, configured in GitHub Actions.
$LicenseURL = $env:DARKMINER_LICENSE_URL

if (!$LicenseURL -or
    !$LicenseURL.StartsWith("https://")) {
    throw "Set DARKMINER_LICENSE_URL to a public HTTPS URL"
}

$Config = @{
    api_url = $LicenseURL.TrimEnd('/')
} | ConvertTo-Json

Set-Content -Path "license_config.json" `
    -Value $Config -Encoding utf8

'''

if 'Set-Content -Path "license_config.json"' not in code:
    if marker not in code:
        raise SystemExit("PyInstaller arguments not found")
    code = code.replace(marker, config + marker)

if '"--add-data=license_config.json;."' not in code:
    code = code.replace(
        '"--add-data=engine;engine"',
        '"--add-data=engine;engine"\n'
        '    "--add-data=license_config.json;."'
    )

build.write_text(code)

# 3. Change the installer version.
iss = root / "installer.iss"
code = iss.read_text()
code = code.replace(
    '#define AppVersion "0.3"',
    '#define AppVersion "0.4"'
)
code = code.replace(
    'DarkMiner-Setup-0.3',
    'DarkMiner-Setup-0.4'
)
iss.write_text(code)

# 4. Pass the public API URL from GitHub Actions.
workflow = root / ".github/workflows/windows.yml"
code = workflow.read_text()

old = "        run: ./build-win.ps1"
new = """        env:
          DARKMINER_LICENSE_URL: ${{ vars.DARKMINER_LICENSE_URL }}
        run: ./build-win.ps1"""

if "vars.DARKMINER_LICENSE_URL" not in code:
    if old not in code:
        raise SystemExit("Build workflow step not found")
    code = code.replace(old, new)

workflow.write_text(code)

# 5. Check source syntax without requiring PySide6.
compile(
    app.read_text(), str(app), "exec"
)
compile(
    (root / "licensing_ui.py").read_text(),
    str(root / "licensing_ui.py"), "exec"
)

print("DarkMiner v0.4 source upgrade completed")
print("Account interface: added")
print("License configuration: added")
print("Installer version: 0.4")
print("GitHub workflow: updated")
