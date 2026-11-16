# Changelog

## 0.2.0-preview.3 — 2026-11-16

- Add confirmed updates for installer-owned plugin copies, including partial Clock updates, runtime backups and rollback on activation failure.
- Preserve calendar accounts, events, settings and existing cloud dependencies; document why Git-based plugin updaters cannot update suite copies.
- Theme updates and coordinated removal remain separate.

## 0.2.0-preview.2 — 2026-11-16

- Adds Google browser sign-in with Velunori's shared Desktop OAuth registration in the published installer; users no longer create their own Google Cloud app.
- Fixes zero-duration timed events, Google timestamp interpretation and iCloud calendars hosted on Apple's numbered CalDAV servers. Sync failures retain cached events and no longer appear as stale editor errors.
- Separates calendar management, calendar creation and account connection into bounded views.
- Updates Dusk's boot-unlock asset to the Velunori wordmark.
- Publishes English privacy and terms pages linked from the website and records the calendar's live validation evidence.

Validation: changed component checks, copied/symlinked bundle layouts, installer tests and website browser checks. Real Google/iCloud backend tests passed for timed/all-day create/edit/delete, remote changes, ETag conflict rejection and preservation of unrelated properties. This does not certify live recurrence/DST edge cases, offline recovery, long-term token refresh or a fresh full-suite installation. See [calendar live validation](https://github.com/Velunori/clock/blob/main/docs/live-calendar-validation.md).

## 0.2.0-preview.1 — 2026-11-16

First public preview of the complete Velunori suite.

- Splits the former core plugin into the **Velunori Library** (`lib`, `velunori.lib` API 1), which every component depends on, and the optional **Floating Bars** plugin (`bar`, `velunori.bar`). Every feature plugin also works on the stock Omarchy bar.
- Replaces the source-linked bundle installer with one self-contained shell script, published at `https://velunori.github.io/install.sh`. It installs copied files, resolves the library automatically, supports full or per-component selection and offers `plan`, `check`, `install` and `status`.
- Builds the installer only from clean, pinned submodule commits, with per-file hashes and commit provenance.
- Follows Omarchy 4.5: menu models, the lock service, native bar icon metrics; adds Control Center workspace shortcut targets and a fixed notification badge.

Validation: component checks in copied and symlinked layouts, installer tests with stand-in hosts, and website checks; see [compatibility](docs/compatibility.md). No live installation, session locking, authentication, real system update or theme activation was performed. Live Google/iCloud synchronization remains unverified. Managed upgrades and removal are not implemented yet.

## 0.1.0-rc.1 — 2026-11-15 (not published)

Internal release candidate, superseded by 0.2.0-preview.1 before publication.

- Pins all nine components to exact Git commits.
- Installs the shared design kit, floating bars, calendar, Control Center, notifications, menu, weather, update window, Serene lock screen and Dusk theme.
- Supports keeping the current theme or lock screen and skipping cloud dependencies.
- Adds a read-only prerequisite check before installation, with a separate installation plan.
- Includes source archives containing the component files, a revision manifest and SHA-256 checksums.

Validation: bundle installation and preflight tests use temporary directories and stand-in commands. No live installation, session locking, authentication, real system update, or theme activation was performed for this release. Live Google/iCloud synchronization remains unverified.

Installation may restart the shell and apply the theme. There is no automatic suite-wide rollback; preserve the backups printed by the installers. Python calendar dependencies use the component's existing requirement ranges; their resolved versions are not locked by this source release.
