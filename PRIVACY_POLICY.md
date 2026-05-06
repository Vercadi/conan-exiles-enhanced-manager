# Conan Exiles Enhanced Manager Privacy Policy

Last updated: May 6, 2026

Conan Exiles Enhanced Manager is a Windows desktop application for managing Conan Exiles mods, modlists, local dedicated servers, hosted server file access, backups, and recovery.

## Summary

- The app does not include advertising.
- The app does not include analytics or telemetry.
- The app does not sell user data.
- Most app data is stored locally on your device.

## Data The App Accesses

Depending on how you use it, the app may access:

- Conan Exiles client and dedicated server folders
- Steam appmanifest files and Workshop content folders
- SteamCMD path and SteamCMD-created Workshop folders
- local `.pak` files you select
- `modlist.txt` files
- Conan configuration, save, and log files
- local backups created by the app
- hosted server file locations and credentials that you enter

## Data Stored Locally

When running as a packaged Windows app, Conan Exiles Enhanced Manager stores app data under:

- `%LOCALAPPDATA%/ConanExilesEnhancedManager`

This may include:

- app settings and configured paths
- active mod entries
- Workshop metadata cache
- hosted server profiles
- optional Steam username for SteamCMD retries
- profile records
- backup metadata and backup files
- activity history
- logs

## Hosted Server Profiles

Hosted server profiles may include:

- host or IP
- port
- username
- remote server folder paths
- authentication mode
- private key file path

The app does not store plaintext hosted passwords after saving profiles. Support diagnostics redact hosted secrets and sensitive fields before copying or saving.

## Network Connections

The app may make network connections in these cases:

### Update Checks

Manual or optional startup update checks contact:

- `https://api.github.com/repos/Vercadi/conan-exiles-enhanced-manager/releases/latest`

This is used only to check whether a newer GitHub release exists.

### Hosted Server Connections

If you configure a hosted server profile, the app may connect to that server using:

- SFTP
- FTP

These connections are used only for hosted features you request, such as connection tests, file listing, modlist upload, pak upload, or config backup.

### SteamCMD Workshop Downloads

If you explicitly start a Workshop download or update, the app launches your configured `steamcmd.exe` for Conan Exiles Workshop app id `440900`.

SteamCMD may contact Valve/Steam services. The app uses anonymous login first. If a username is configured for account-based retry, the app passes that username to SteamCMD but does not store or pass a Steam password.

### External Links

If you click links in the app, your browser may open external sites such as:

- GitHub
- Ko-fi
- Patreon

Those sites are governed by their own privacy policies.

## Data Sharing

Conan Exiles Enhanced Manager does not share your data with the developer except through services you explicitly use.

Examples:

- GitHub receives standard request information when update checks are used.
- Your hosted server provider receives the credentials and file operations needed to connect to the hosted server profile you configured.
- External sites you open in your browser handle their own data.

## Data Retention And Deletion

You control the local data stored by the app. You can remove it by deleting:

- `%LOCALAPPDATA%/ConanExilesEnhancedManager`

You can also remove profiles, backups, and app-managed records from inside the app where supported.

## Contact

For support or privacy questions, use GitHub Issues:

- https://github.com/Vercadi/conan-exiles-enhanced-manager/issues
