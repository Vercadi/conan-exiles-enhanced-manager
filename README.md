# Conan Exiles Enhanced Manager

A Windows desktop manager for **Conan Exiles Enhanced** mods, Steam Workshop modlists, local dedicated servers, hosted FTP/SFTP servers, profiles, backups, and recovery.

**GitHub:** https://github.com/Vercadi/conan-exiles-enhanced-manager<br>
**Nexus Mods:** available on Nexus Mods<br>
**Support:** https://ko-fi.com/vercadi | https://www.patreon.com/cw/Vercadi

## Features

- Detects the Conan Exiles client, Conan Exiles Dedicated Server, Steam build IDs, config folders, saves, logs, and Workshop content.
- Scans Steam Workshop content for app id `440900`.
- Fetches public Steam Workshop metadata for real mod titles, remote size, update time, tags, and preview metadata.
- Downloads and updates Workshop items through SteamCMD after explicit user action.
- Manages a local mod library for raw `.pak` files, companion `.ucas`/`.utoc` files, linked external paks, and zip archives.
- Preserves Active Mods load order with enable/disable, position actions, missing-file warnings, and client/server parity checks.
- Stores persistent per-mod notes for Workshop, local, archive, and active load-order entries.
- Safely previews and writes `modlist.txt` for the client, dedicated server, or both.
- Copies managed local paks and companion files into target `ConanSandbox/Mods` folders only during explicit apply.
- Starts the local dedicated server only when explicitly requested.
- Edits core dedicated server settings with preview diffs and config backups.
- Supports hosted servers over SFTP or FTP for path detection, modlist upload, optional local pak upload, and config backup.
- Provides named mod profiles, restore-to-vanilla workflows, backup snapshots, activity history, Settings, Help, support diagnostics, and GitHub Releases update checks.

## Screenshots

Screenshots are available on the Nexus Mods page.

- Dashboard
- Workshop
- Active Mods
- Server
- Hosted

## Download

Use the latest release from:

https://github.com/Vercadi/conan-exiles-enhanced-manager/releases

## SteamCMD Setup

Workshop downloads require SteamCMD.

1. Download SteamCMD from Valve.
2. Extract it to a stable folder such as `C:\steamcmd`.
3. Launch the manager, open `Settings`, and set the full path to `steamcmd.exe`.
4. Workshop downloads use anonymous login first.
5. If SteamCMD reports an ownership or login issue, the app can retry with a Steam username. Passwords are never saved by this app.

SteamCMD downloads Workshop files into its own `steamapps/workshop/content/440900` folder. The manager scans both the detected Steam Workshop folder and the configured SteamCMD Workshop folder.

## Running From Source

### Prerequisites

- Windows 10/11
- Python 3.12+

### Setup

```bash
pip install -r CEMSM/requirements.txt
python CEMSM/app.py
```

### Run Tests

```bash
cd CEMSM
python -m pytest -q
```

## Building The Executable

From the repository root:

```powershell
.\CEMSM\scripts\build_release.ps1
```

For a Nexus-friendly upload zip containing a single executable:

```powershell
.\CEMSM\scripts\build_nexus_release.ps1
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

## Hosted Server Notes

Hosted support requires provider file access through SFTP or FTP.

You usually need:

- host or IP
- FTP/SFTP port
- username
- password or private key path
- remote server folder

FTP/SFTP ports are not Conan game, query, or RCON ports. If your provider only exposes a web file panel and does not offer FTP or SFTP access, use the app's provider-panel fallback instructions.

## Privacy

The app has no analytics, advertising, or telemetry. See [PRIVACY_POLICY.md](PRIVACY_POLICY.md).

## Known Limitations

- Hosted control-panel APIs are not implemented.
- Hosted servers are not restarted automatically.
- Server config editing covers focused dedicated server settings only.
- Windows only.

## License

MIT License. See [LICENSE](LICENSE).
