# Velunori shell installer

One downloadable `.sh` script with a complete runtime source snapshot, selectable components and automatic library resolution. The website uses the Guided selection design; the script independently validates the same choices. It is not an Omarchy plugin, installer window, tray icon or bar widget.

Checked on Omarchy 4.5.0-3 with temporary homes and stand-in activation; a real desktop installation still needs live verification. See the [compatibility record](../docs/compatibility.md).

## Commands

After downloading the script:

```bash
bash velunori-install.sh plan --components control-center
bash velunori-install.sh check --components control-center
bash velunori-install.sh install --components control-center
bash velunori-install.sh status
```

Use `--all` for all nine components, or `--components bar,clock,control-center,...`. The names are in `catalog.json`. `lib` is not a selectable bar/plugin; it is included automatically for every component except the standalone theme. `--cloud` explicitly downloads clock dependencies into its private environment and requires clock selection. Accounts are connected separately from the calendar.

The website command for the full package is:

```bash
curl -fsSL https://velunori.github.io/install.sh | bash -s -- --all
```

Omit the flags to choose components interactively:

```bash
curl -fsSL https://velunori.github.io/install.sh | bash
```

Both piped and downloaded-file execution are supported. With no selection flags, installation asks for full/custom selection; `--all` skips the selection menu. It still shows the plan, checks prerequisites and requires the exact confirmation `INSTALL`. For a piped script, questions are read from the controlling terminal (`/dev/tty`) instead of consuming script bytes from stdin. There is no implicit `--yes`. Without a terminal, explicit `plan --all` works, but an installation needing unanswered interactive input stops clearly. `plan` computes changes without desktop queries; `check` performs bounded read-only prerequisite queries. Both unpack into a temporary private directory, but create no permanent installation/configuration state.

The script has Bash/Python 3 bootstrap requirements and needs the relevant existing Omarchy commands for the selected components. It never installs system packages. No repository cloning or external build service is needed: sources and licenses are embedded. Downloaded cloud libraries are an explicit exception to offline installation; weather/provider use also requires network access during ordinary operation.

## Copied installation and ownership

Plugins are staged and natively manifest-validated before activation. The installer places ordinary directories under `${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/<plugin-id>` and the shared library under `plugins/lib`. There are no source symlinks, workspace shortcuts or mandatory Floating Bars dependency. A compatible existing library is retained; existing plugin paths, redirected plugin directories and occupied receipt directories are refused.

The selected bar is preserved unless `bar` is selected. Known replacement widget slots/settings are retained where applicable; Control Center replaces legacy device controls, while unrelated widgets remain in place. Genuine clone replacements record source-disable/restoration state. The clock replaces its slot without claiming a clone identity it does not declare. The exact selections are shown before confirmation. Dusk applies colors/wallpaper immediately; Serene requires a byte-identical installed lock service and readable existing PAM configuration. Installation does not lock or authenticate.

The default receipt directory is `${XDG_DATA_HOME:-$HOME/.local/share}/velunori/installation`, separate from component data such as the calendar in `velunori/clock`. Override it with `--prefix /permanent/path` and use that same flag for later status checks. The private directory holds:

- `installation.json`: version, build, selection, ownership, phase and any recovery error.
- `backups/shell.before.json`: the exact pre-install shell configuration.
- `installer.sh`: the retained self-contained script when installed through the `.sh` bootstrap.
- `recovery/`: new files moved aside after a recoverable failed installation.

A successful receipt records `installed`. It is not proof of live panel placement, account interoperability or the absence of a native host crash.

## Failure and recovery

Activation failure attempts to restore the saved configuration if it still matches the installer’s expected bytes. A successful restoration moves owned new files into `recovery/`, preserving them rather than deleting them. Concurrent configuration changes or a failed restoration leave files in place and record `needs-recovery`. The script never overwrites another user edit to force rollback.

Review the receipt and printed error before retrying. It deliberately refuses an occupied receipt directory instead of discarding recovery information. For manual recovery, back up the current configuration, review `shell.before.json`, and restore it only when replacing later shell changes is intended. Restart the shell afterward from an unlocked desktop. Theme restoration is separate; the receipt and native theme installer output record the prior theme and any theme-file backup. Calendar data and account credentials are not deleted. Failed private cloud-environment setup is retained with the copied clock files.

Managed in-place upgrades and selection-aware removal are **not implemented yet**. For an ordinary copied feature, use Omarchy's disable/removal commands and its component recovery instructions. Switch to the stock bar before removing Floating Bars. The clock's built-in replacement can be re-enabled explicitly if required. Keep the shared library while another plugin needs it. Existing development links or older source-linked installations require a deliberate migration; this script does not silently replace them.

## Build

From this repository's root, with submodules initialized:

```bash
python3 installer/build.py --output /tmp/velunori-install.sh
python3 installer/build.py --site-dir ../velunori.github.io
```

`--site-dir` stages the versioned download, the root `install.sh` copy and their checksums into a local checkout of the website, and updates the download links in its pages. It never publishes.

The builder packages `lib` and every catalogue component from `components/`, and refuses a submodule with uncommitted or untracked changes. Each file's provenance records the submodule commit. It excludes Git metadata, tests/docs, caches, virtual environments, hidden files and unrelated runtime file types. The artifact includes runtime code, licenses, catalogue and integrity/provenance metadata. The same pins produce identical artifact bytes.

Payload and per-file SHA-256 checks detect corruption. They are not an independent publisher signature: users must trust the official distribution origin and review the source. The bootstrap rejects archive links, unsafe paths and duplicate entries. The same input snapshot produces identical artifact bytes in the checked environment.

## Validate

```bash
python3 -B -m unittest discover -s installer/tests -v
```

Tests use temporary homes, fixture configuration and stand-in commands. The complete generated script is exercised with the real packaged Clock/Control Center sources and native manifest validation, while shell activation is simulated. They verify that only selected directories and the dependency are copied, the stock bar is preserved, stdin confirmation works, and the retained script can report status. No real theme is applied, lock/authentication invoked, accounts connected or system update performed. Native desktop installation and recovery remain pending.
