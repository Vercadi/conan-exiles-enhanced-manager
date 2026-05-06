# Changelog

## v1.1.0 - Release Candidate Hardening

- Updated release documentation, SteamCMD setup guidance, safety notes, and packaging instructions.
- Added first-run guidance for missing Conan installs, missing dedicated server installs, and missing SteamCMD.
- Expanded support diagnostics with app version, feature flags, SteamCMD status, Workshop counts, and Active Mods counts.
- Added release hardening tests for docs, packaging, diagnostics, and public export exclusions.

## v1.0.0 - SteamCMD Workshop Support

- Added SteamCMD path detection and Settings configuration.
- Added explicit Workshop actions for Download Missing, Update Selected, Update Downloaded, and Cancel SteamCMD.
- Added anonymous-first SteamCMD Workshop downloads for Conan app id `440900`.
- Added optional username retry for SteamCMD login or ownership failures. Passwords are never stored.
- Rescans Workshop cache after successful SteamCMD downloads or updates.

## v0.10.0 - Active Mods UX and Local Mod Library

- Added managed local mod library for raw `.pak` files, companion files, external links, and zip archives.
- Reworked Active Mods into Library and Active Load Order panels.
- Added target copy previews, companion file sync, and target-file backups before overwrite.

## v0.9.0 - Server Config Editor

- Added focused dedicated server config editing with preview diffs, backups, and restart-required markers.

## v0.1.0-v0.8.0

- Built the Conan-specific desktop app foundation, discovery, modlist MVP, Workshop scanning, dedicated server operations, hosted FTP/SFTP support, profiles/recovery, UI polish, release links, Settings, and Help.
