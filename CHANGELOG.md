# Changelog

## 0.1.0-rc.1 — 2026-11-15

First release candidate of the complete Velunori suite. This is a preview release, not a declaration of verified desktop compatibility.

- Pins all nine components to exact Git commits.
- Installs the shared design kit, floating bars, calendar, Control Center, notifications, menu, weather, update window, Serene lock screen and Dusk theme.
- Supports keeping the current theme or lock screen and skipping cloud dependencies.
- Adds a read-only prerequisite check before installation, with a separate installation plan.
- Includes source archives containing the component files, a revision manifest and SHA-256 checksums.

Validation: bundle installation and preflight tests use temporary directories and stand-in commands. No live installation, session locking, authentication, real system update, or theme activation was performed for this release. Live Google/iCloud synchronization remains unverified. See [release instructions](docs/releases.md) for the validation scope and packaging procedure.

Installation may restart the shell and apply the theme. There is no automatic suite-wide rollback; preserve the backups printed by the installers. Python calendar dependencies use the component's existing requirement ranges; their resolved versions are not locked by this source release.
