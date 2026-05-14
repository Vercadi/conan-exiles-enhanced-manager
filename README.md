# Conan Exiles Enhanced Manager

[![Latest tag](https://img.shields.io/github/v/tag/Vercadi/conan-exiles-enhanced-manager?label=latest%20tag)](https://github.com/Vercadi/conan-exiles-enhanced-manager/tags)
[![License](https://img.shields.io/github/license/Vercadi/conan-exiles-enhanced-manager)](LICENSE)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-support-ff5f5f)](https://ko-fi.com/vercadi)
[![Patreon](https://img.shields.io/badge/Patreon-support-f96854)](https://www.patreon.com/cw/Vercadi)

A Windows desktop manager for **Conan Exiles Enhanced** mods, Steam Workshop modlists, local dedicated servers, hosted FTP/SFTP servers, profiles, backups, and recovery.

## Media

Screenshots will be added with the first public packaged release. No screenshot or banner asset is currently tracked in this repository.

## Download

- Source repository: [GitHub](https://github.com/Vercadi/conan-exiles-enhanced-manager)
- Tags: [GitHub Tags](https://github.com/Vercadi/conan-exiles-enhanced-manager/tags)
- Releases: [GitHub Releases](https://github.com/Vercadi/conan-exiles-enhanced-manager/releases)

No public packaged GitHub release is currently published. Build from source for now, or use a future GitHub Release once it is public.

I did not find a public Nexus Mods page for this project, so no Nexus badge or download link is included here.

## Installation

### Running From Source

Prerequisites:

- Windows 10/11
- Python 3.12+

Setup:

```bash
pip install -r CEMSM/requirements.txt
python CEMSM/app.py
```

### SteamCMD Setup

Workshop downloads require SteamCMD.

1. Download SteamCMD from Valve.
2. Extract it to a stable folder such as `C:\steamcmd`.
3. Launch the manager, open Settings, and set the full path to `steamcmd.exe`.
4. Workshop downloads use anonymous login first.
5. If SteamCMD reports an ownership or login issue, the app can retry with a Steam username. Passwords are never saved by this app.

SteamCMD downloads Workshop files into its own `steamapps/workshop/content/440900` folder. The manager scans both the detected Steam Workshop folder and the configured SteamCMD Workshop folder.

## Update

Public packaged updates will be distributed through GitHub Releases once a release is published. Source users can pull the latest repository changes and reinstall dependencies if requirements change.

## Usage

Conan Exiles Enhanced Manager focuses on explicit, reviewable actions:

- detect the Conan Exiles client, dedicated server, config folders, saves, logs, and Workshop content
- scan Steam Workshop content for app id `440900`
- download and update Workshop items through SteamCMD after explicit user action
- manage local `.pak` files, companion `.ucas`/`.utoc` files, linked external paks, and zip archives
- preserve Active Mods load order with enable/disable, missing-file warnings, and client/server parity checks
- preview and write `modlist.txt` for the client, dedicated server, or both
- copy managed local paks and companion files into target `ConanSandbox/Mods` folders only during explicit apply
- start the local dedicated server only when explicitly requested
- edit dedicated server settings with preview diffs and config backups
- support hosted servers over SFTP or FTP for path detection, modlist upload, optional local pak upload, and config backup
- provide named profiles, restore-to-vanilla workflows, backup snapshots, activity history, Settings, Help, support diagnostics, and GitHub Releases update checks

## Requirements

- Windows 10/11
- Python 3.12+ for source mode
- Conan Exiles installed locally for client workflows
- Conan Exiles Dedicated Server for dedicated server workflows
- SteamCMD for Workshop downloads
- SFTP or FTP file access for hosted server workflows

## Compatibility

Hosted support requires provider file access through SFTP or FTP. FTP/SFTP ports are not Conan game, query, or RCON ports. If your provider only exposes a web file panel and does not offer FTP or SFTP access, use the app's provider-panel fallback instructions.

Hosted profile setup usually needs host or IP, FTP/SFTP port, username, password or private key path, and the remote server folder.

Known limitations:

- Hosted control-panel APIs are not implemented.
- Hosted servers are not restarted automatically.
- Server config editing covers focused dedicated server settings only.
- Windows only.

## Safety Model

- The app never deletes `.pak` files.
- Importing local mods copies files only into app-managed storage, unless you choose external link mode.
- Real Conan client/server folders are changed only by explicit apply, restore, config edit, hosted upload, or server launch actions.
- Existing `modlist.txt` files are backed up before writes.
- Existing target pak files with matching names are backed up before overwrite.
- Config files are backed up before server setting writes.
- Config/save backups are stored in app-managed backup storage.
- Risky write, upload, restore, and vanilla workflows show previews before applying.
- Workshop downloads are started only by explicit user action.
- Hosted uploads do not restart hosted servers.
- Hosted secrets and sensitive fields are redacted from diagnostics.
- The app does not store plaintext hosted passwords or Steam passwords.

## Bug Reports / Support

Use [GitHub Issues](https://github.com/Vercadi/conan-exiles-enhanced-manager/issues) for bugs and support. Include the app version, whether you are running from source or a package, SteamCMD status, target workflow, and redacted diagnostics where relevant.

Support continued work through [Ko-fi](https://ko-fi.com/vercadi) or [Patreon](https://www.patreon.com/cw/Vercadi).

## Privacy

The app has no analytics, advertising, or telemetry. See [PRIVACY_POLICY.md](PRIVACY_POLICY.md).

## Running Tests

```bash
cd CEMSM
python -m pytest -q
```

## Repository Layout

```text
conan-exiles-enhanced-manager/
  CEMSM/
    conan_manager/
      core/
      models/
      ui/
    scripts/
    tests/
  CHANGELOG.md
  LICENSE
  PRIVACY_POLICY.md
```

## Building The Executable

From the repository root:

```powershell
.\CEMSM\scripts\build_release.ps1
```

Or manually:

```bash
cd CEMSM
python -m PyInstaller conan_exiles_enhanced_manager.spec --noconfirm --clean
```

The packaged app stores working data under `%LOCALAPPDATA%/ConanExilesEnhancedManager/`.

Portable smoke test:

1. Build the app.
2. Launch `CEMSM/dist/Conan Exiles Enhanced Manager/Conan Exiles Enhanced Manager.exe`.
3. Confirm Dashboard opens.
4. Open Settings and confirm SteamCMD guidance is visible.
5. Open Workshop and confirm missing SteamCMD guidance is actionable if SteamCMD is not configured.

## License

MIT License. See [LICENSE](LICENSE).
