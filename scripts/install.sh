#!/usr/bin/env bash
# Run by the user in an unlocked Omarchy desktop terminal.
set -Eeuo pipefail
suite_dir=$(cd "$(dirname "$0")/.." && pwd -P)
dry_run=false
theme=true
lockscreen=true
cloud=true
usage() {
  cat <<'EOF'
Usage: bash scripts/install.sh [options]

Installs core, clock, Control Center, notifications, menu, weather, update,
Serene lock screen, the theme, and private calendar dependencies.

  --dry-run             Print the plan without executing installers or pip
  --without-theme       Keep the current Omarchy theme
  --without-lockscreen  Keep the current lock screen
  --without-cloud       Skip calendar dependency setup (local calendar still works)
  --help                Show this help
EOF
}
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true ;;
    --without-theme) theme=false ;;
    --without-lockscreen) lockscreen=false ;;
    --without-cloud) cloud=false ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done
fail() { printf '%s\n' "$*" >&2; exit 1; }
plugins=(core clock control-center notifications menu weather update)
[[ $lockscreen == false ]] || plugins+=(lockscreen)
components=("${plugins[@]}")
[[ $theme == false ]] || components+=(theme)
for component in "${components[@]}"; do
  [[ -f "$suite_dir/components/$component/scripts/install-local.sh" ]] ||
    fail 'Missing components. Run: git submodule update --init --recursive'
done
if [[ $cloud == true ]]; then
  [[ -f "$suite_dir/components/clock/scripts/setup-deps.sh" ]] || fail 'Missing calendar dependency installer.'
fi
run() {
  printf '  '; printf '%q ' "$@"; printf '\n'
  if [[ $dry_run == false ]]; then "$@"; fi
}
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy"
backup=''
if [[ $dry_run == false ]]; then
  (( EUID != 0 )) || fail 'Run as your desktop user, without sudo.'
  for executable in python3 omarchy omarchy-shell pactl ip hyprctl systemd-run checkupdates omarchy-update; do
    command -v "$executable" >/dev/null || fail "Missing required command: $executable"
  done
  [[ -f "$config_dir/shell.json" ]] || fail 'Missing Omarchy shell.json.'
  [[ -n ${XDG_RUNTIME_DIR:-} && -d $XDG_RUNTIME_DIR ]] || fail 'Run inside your Omarchy desktop session (XDG_RUNTIME_DIR is required).'
  [[ $(omarchy-shell shell ping) == ok ]] || fail 'Omarchy shell is not running.'
  for plugin in "${plugins[@]}"; do
    destination="$config_dir/plugins/velunori.$plugin"
    if [[ -e $destination || -L $destination ]]; then
      [[ -L $destination && $(readlink -f "$destination") == "$suite_dir/components/$plugin" ]] ||
        fail "Another installation exists at $destination. Use its checkout or remove it deliberately before switching."
    fi
  done
  if [[ $lockscreen == true ]]; then
    cmp -s "$suite_dir/components/lockscreen/Service.qml" "${OMARCHY_PATH:-/usr/share/omarchy}/shell/plugins/lock/Service.qml" ||
      fail 'Lock service differs from this Omarchy version. See the lockscreen README or use --without-lockscreen.'
    [[ -r /etc/pam.d/omarchy-lock-password ]] || fail 'Omarchy lock PAM configuration is missing.'
    [[ $(omarchy-shell lock isLocked) == false ]] || fail 'Run from an unlocked desktop.'
  fi
  backup=$(mktemp "$config_dir/shell.json.before-velunori-suite.XXXXXXXX")
  cp -p "$config_dir/shell.json" "$backup"
  printf 'Original shell configuration: %s\n' "$backup"
fi
on_failure() {
  printf 'Installation stopped. Previously completed components remain installed.\n' >&2
  if [[ -n $backup ]]; then
    printf 'Restore the original shell configuration from: %s\n' "$backup" >&2
  fi
}
trap on_failure ERR
printf 'Install plan (component scripts may restart the shell):\n'
if [[ $cloud == true ]]; then
  run bash "$suite_dir/components/clock/scripts/setup-deps.sh"
fi
for plugin in "${plugins[@]}"; do
  run bash "$suite_dir/components/$plugin/scripts/install-local.sh"
  if [[ $plugin == clock ]]; then run omarchy restart shell; fi
done
if [[ $theme == true ]]; then run bash "$suite_dir/components/theme/scripts/install-local.sh"; fi
if [[ $dry_run == true ]]; then
  printf 'Dry run only; no installers, downloads, or desktop changes were executed.\n'
else
  printf 'Velunori installed. Keep this checkout: plugins are linked to components/.\n'
  printf 'Open appearance settings: omarchy-shell velunori settings\n'
fi
