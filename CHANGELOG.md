# Changelog

## v1.4.3 - Workshop Metadata, Position Actions, And Notes

- Added public Steam Workshop metadata fetching for real Workshop titles, remote file size, update time, tags, and preview metadata.
- Added Library `Inactive / Not Active` filtering for mods not currently in Active Load Order.
- Added right-click `Add to Position...` and `Move to Position...` load-order actions.
- Added a persistent Notes tab for per-mod notes that survive removing and re-adding mods.
- Added pak, companion, archive, Workshop local, and Workshop remote size details where available.
- Removed the duplicate Steam Workshop Settings card; Workshop path remains under Local Paths.
- Hid background helper subprocess windows used for dedicated-server process detection, preventing black command-window flashes during status refreshes.
- Kept Workshop metadata lookup credential-free and non-destructive; no subscribe/unsubscribe or Workshop file deletion.

## v1.4.2 - First-Run, Paths, And Active Mods Feedback Patch

- Added first-run setup for client, optional dedicated server, Workshop, and SteamCMD paths.
- Added editable client, dedicated server, Workshop, and SteamCMD path controls in Settings.
- Added a dedicated-server feature toggle so client-only users can suppress dedicated-server warnings and default profile coverage.
- Added Workshop cache cleanup actions for selected, missing, and all cached entries without deleting Workshop or pak files.
- Added profile coverage editing after profile creation.
- Fixed Active Load Order refresh after profile load, removal, dedupe, and Workshop cache cleanup.
- Improved Active Mods readability with inactive filtering, clearer status text, first-letter navigation, and Workshop ID linking.
- Added copy-vs-source-path apply mode for local client/dedicated targets.

## v1.4.1 - Workshop Path Hotfix

- Added a Settings field for the Conan Workshop content folder.
- Preserved manually configured Workshop paths across discovery refreshes.
- Treated accidental `"null"` path strings as empty settings instead of literal folders.

## v1.4.0 - Nexus Release UX Polish

- Added a global quick-action bar for Start Game, Start Server, common folders, logs, and backups.
- Simplified Dashboard Home so it no longer duplicates tab navigation.
- Changed profile switching to a one-click Load Profile action and double-click profile loading.
- Centered modal/preview windows over the app instead of letting them open off-screen.
- Normalized local/archive mod display names and collapsed single-mod zip imports to one Library row.
- Styled Library and Active Load Order scrollbars to match the Conan UI.
- Kept Settings save controls visible outside the scrolling content.
- Added Workshop cache refresh/forget actions and safe Library record removal without deleting files.
- Prevented duplicate Workshop IDs from being added to Active Load Order and added a clean-duplicates action.
- Made client/server modlist imports block empty imports from accidentally clearing Active Load Order.
- Added Save Profile directly from Active Mods for saving load orders.
- Shortened crowded Active Mods button labels and renamed save/import actions around mod load orders.
- Added drag-and-drop support for Library imports, Library-to-Active activation, and Active Load Order reordering.
- Added Conan-specific app/window/release icon assets.

## v1.3.0 - Target Actions, Bulk Selection, And Safe Uninstall

- Added multi-select workflows for Library and Active Load Order.
- Added right-click actions for local, archive, Workshop, and active mods.
- Added selected install/sync planning for Client, Dedicated Server, and Both targets.
- Added safe selected uninstall with `modlist.txt` backup and current/proposed diffs.
- Added optional quarantine for manager-owned target copies without deleting original imports or Steam Workshop cache files.
- Exposed Restore Vanilla from Active Mods.

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
