# Velunori

A complete desktop suite for Omarchy: floating bars, coordinated panels, a Serene lock screen and a graphite, lavender and mint theme.

![Velunori appearance settings and floating bar layouts](docs/preview.png)

## Install the whole suite

Use an **unlocked Omarchy desktop terminal**, as your normal user. You need Omarchy's shell plugin API, Git, Python 3 with `venv`/pip, and the existing Omarchy tools used by the components (`pactl`, `ip`, `hyprctl`, `systemd-run` and `checkupdates`). Components were developed against **Omarchy 4.0.6-1**; compatibility with every newer release is not guaranteed. The lock installer checks that its service matches your installed Omarchy service before activation.

```bash
git clone --recurse-submodules https://github.com/Velunori/velunori.git ~/.local/share/velunori
cd ~/.local/share/velunori
bash scripts/install.sh --check
bash scripts/install.sh --dry-run
bash scripts/install.sh
```

The installer sets up calendar dependencies in `components/clock/.venv`, then installs core, clock, Control Center, notifications, menu, weather, update, the Serene lock screen and the theme. The theme is applied immediately; panels replace their corresponding built-in components and the shell restarts during installation. The update component is installed without running a system update. Installing the lock screen does not lock the desktop or authenticate you.

`--check` is a read-only prerequisite check: it inspects selected source files, required commands, Python environment support, shell configuration, the current desktop session, installation links, active replacement conflicts, and the selected theme/lock prerequisites. It reports multiple failures together, without creating backups, links or virtual environments, downloading packages, restarting the shell, or invoking authentication. It exits with `0` when prerequisites pass and `1` when they fail; invalid options exit with `2`. It does not verify network access, live UI behavior or cloud sign-in. A real installation runs the same checks before making changes.

`--dry-run` only prints the install plan; it does not query the live session or validate runtime prerequisites. Use it separately from `--check`.

The examples use `~/.local/share/velunori` for a new installation; another permanent directory is fine. **Keep this checkout in place.** Plugins link to `components/`; moving or deleting it breaks those links. Each component is a Git submodule pinned to a specific commit, so everyone cloning this revision gets the same source versions. This is a source installation, not a system package, and installs no system packages automatically.

Already cloned without submodules? Run `git submodule update --init --recursive` first. If you already have Velunori linked from another checkout, the installer stops before changing the desktop; keep using the existing component installers or deliberately migrate those links before switching to this bundle.

## Versioned releases

For a pinned release rather than the development branch, follow [release installation and updates](docs/releases.md). See [CHANGELOG.md](CHANGELOG.md) for release scope and validation limits. Release candidates are previews; they do not establish live desktop or cloud compatibility.

## Choose what to install

All components are included by default. You can keep your current theme or lock screen, or skip cloud calendar dependencies:

```bash
bash scripts/install.sh --without-theme --without-lockscreen
bash scripts/install.sh --without-cloud
```

Use the same selection flags with `--check`, `--dry-run` and the actual installation. For example, `bash scripts/install.sh --check --without-theme --without-lockscreen` checks only that selection. `--check` and `--dry-run` are separate modes and cannot be combined. Without cloud dependencies, the clock and editable local calendar still work. To add Google/iCloud support later:

```bash
bash components/clock/scripts/setup-deps.sh
omarchy restart shell
```

Connect accounts explicitly in the calendar panel. Google uses desktop OAuth; iCloud uses an app-specific password. See the [calendar setup and synchronization guide](https://github.com/Velunori/clock/blob/main/docs/calendar-sync.md). Installation does not connect accounts, and live cloud synchronization has not been verified by this bundle's automated checks.

## What's included

| Component | Role |
| --- | --- |
| [core](https://github.com/Velunori/core) | Island and Orbit floating bars, appearance settings and the shared design kit |
| [clock](https://github.com/Velunori/clock) | Clock, editable local calendars and Google/iCloud synchronization |
| [control-center](https://github.com/Velunori/control-center) | Sound, displays, network, capture, reminders and appearance |
| [notifications](https://github.com/Velunori/notifications) | Notification cards and session-only history |
| [menu](https://github.com/Velunori/menu) | Two-pane Omarchy command menu and prompts |
| [weather](https://github.com/Velunori/weather) | Saved cities and a weekly forecast |
| [update](https://github.com/Velunori/update) | A progress window for Omarchy's own system updater |
| [lockscreen](https://github.com/Velunori/lockscreen) | Serene presentation with Omarchy's unchanged lock/PAM service |
| [theme](https://github.com/Velunori/theme) | Coordinated palette, Dusk wallpaper and window styling |

Each repository has its own screenshots, requirements, installation details, checks and limitations. Components can also be installed individually; install core first.

## After installation

Open **Appearance** in Control Center, or run `omarchy-shell velunori settings`. Choose Island or Orbit, an accent and animations. Your existing Omarchy widget order and settings are preserved where supported by the component migrations.

The Serene lock screen has a preview that does not lock or accept passwords: `omarchy-shell lock preview`. Click it to dismiss. Weather requires network access. Notification history lasts only for the current session; calendar data persists.

## Update the suite

```bash
cd ~/.local/share/velunori
git pull --ff-only
git submodule update --init --recursive
bash scripts/install.sh --check
bash scripts/install.sh
```

If you installed in a different directory, use that path instead. Keep existing installations in place: moving the checkout breaks plugin links. Reuse your original install flags if you skipped the theme, lock screen or cloud dependencies. Submodule updates change linked plugin files and can trigger shell reloads; update from a desktop terminal when convenient. Local modifications can prevent an update; preserve your work rather than discarding it. Avoid `git submodule update --remote` unless you deliberately want component revisions outside the bundle's pinned set.

## Recovery

Before running component installers, the bundle prints a backup named `shell.json.before-velunori-suite.*` inside your Omarchy configuration directory. Individual component installers also make backups. If a later component fails, installation stops and earlier completed components remain installed; there is no automatic rollback of the whole suite.

To restore the original shell layout and plugin selection, copy the printed bundle backup over `${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/shell.json`, then run `omarchy restart shell`. Keep the checkout until you have restored or disabled its plugins. This does not remove calendar data, component links or calendar dependencies.

The theme installer prints the previous theme and a separate restore command: `omarchy theme set <previous-theme>`. Restoring `shell.json` does not restore application colors or wallpaper. To return only to the original bar, run `omarchy plugin enable omarchy.bar`; this keeps other Velunori plugins enabled. For individual removal, follow each component's README and restore script.

## Development and limits

```bash
bash -n scripts/install.sh
python3 -m unittest discover -s tests -v
bash scripts/install.sh --dry-run
```

Bundle tests exercise installation order, options and failures with stand-in commands in temporary directories. They do not install the suite, alter the desktop, lock the session or run the real updater. Follow each component's checks for QML/backend validation. Panel placement, scrolling, authentication and complete installation still need verification in a real desktop session. Known host crash investigations are documented in [core's stability notes](https://github.com/Velunori/core/blob/main/docs/stability.md).

Report bundle installation problems in [this repository's issues](https://github.com/Velunori/velunori/issues); component-specific problems belong in that component's repository. Include your Omarchy version and relevant error output, with credentials removed.

## Contributing and support

Read the shared [contribution guidelines](https://github.com/Velunori/.github/blob/main/CONTRIBUTING.md) for repository selection, development setup and validation. Use the [issue forms](https://github.com/Velunori/velunori/issues/new/choose) for bundle bugs, installation problems, suggestions or questions; component issues belong in their respective repositories.

See [support](https://github.com/Velunori/.github/blob/main/SUPPORT.md) and our [Code of Conduct](https://github.com/Velunori/.github/blob/main/CODE_OF_CONDUCT.md). Report suspected vulnerabilities through [private security reporting](https://github.com/Velunori/.github/blob/main/SECURITY.md), rather than public issues.

## License

MIT. See [LICENSE](LICENSE); each component retains its own license and third-party notices.
