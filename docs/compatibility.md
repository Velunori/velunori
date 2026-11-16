# Compatibility and validation record

Checked on **2026-11-16**, using the component revisions pinned by **0.2.0-preview.1**. This document records automated coverage; live desktop certification is pending.

## Environment

| Item | Observed version |
| --- | --- |
| Omarchy | 4.5.0-3 |
| Quickshell | 0.3.2.r7.g2b4501a-1 |
| Qt base / declarative | 6.12.0-3 / 6.12.0-2 |
| Python | 3.14.8 |
| Node.js | 26.12.0 |
| Other Omarchy / Qt / Quickshell versions | Unverified |

These versions describe this check environment, not minimum or maximum supported versions.

## Component checks

Every row ran the component's own `bash scripts/check.sh` from this repository's `components/` layout, where the only shared dependency is the sibling `components/lib`. Feature components ran in both the copied and symlinked layouts (`VELUNORI_TEST_LAYOUT=copy|symlink`). All commands exited with 0. Scripts use temporary test state and offscreen UI where applicable.

| Component | Exact revision | Automated result |
| --- | --- | --- |
| lib | `782a49ab89588b95c46b75b57214603cf63afcfb` | Passed |
| bar | `5500d0f2ea134d907866cade279463d948cda073` | Passed |
| clock | `f8d54f0c07abc1a4f2def5956459b3542063f441` | Passed, copied and symlinked |
| control-center | `e5734acf3465912d5cd1af6ad183f32133758e9d` | Passed, copied and symlinked |
| notifications | `37fa89991b8d7f7c36b02eeaacd368bffbd565d2` | Passed, copied and symlinked |
| menu | `618b7b969b99320f682792ba65b12c1df8b3df0f` | Passed, copied and symlinked |
| weather | `15b1fe2cf32ac34ea43c43fd60bb509fead16f2a` | Passed, copied and symlinked |
| update | `7b372c28476fe5add302416427841ae41dd8bae4` | Passed, copied and symlinked |
| lockscreen | `c50e6cbee7309d5d630dc6f907520f61740008be` | Passed, copied and symlinked |
| theme | `0000f0c072aa50d07726992dd80ede6dd896fbe2` | Passed, including the palette cross-check against `lib` |

Additional checks:

| Check | Result | Scope |
| --- | --- | --- |
| Installer tests | Passed | Temporary homes, fixture configuration and stand-in activation; see [installer validation](../installer/VALIDATION.md) |
| Calendar Python tests with cloud libraries | All 17 passed | A private environment with the calendar's cloud dependencies; temporary test data and mocks |
| Website | Passed | Structure, SEO and browser checks of the installer configurator, gallery and responsive layouts |

## Live validation still needed

| Area | Current status | Evidence needed before claiming live verification |
| --- | --- | --- |
| Complete installation | Pending | Unlocked desktop installation through the published script, shell restart, selected components and recovery from the receipt |
| Real panels and bar | Pending | Placement, clipping, scrolling, touchpad/mouse and keyboard behavior on small monitors and scaled displays |
| Google / iCloud | Unverified live | Explicit account connection, event create/edit/delete in both directions, recurrence/time zones, conflicts and failed-sync cache retention |
| Serene | View check passed; live lock/authentication unverified | Service byte comparison and a regular offscreen view passed. No desktop lock or PAM authentication was invoked |
| Dusk theme | Template checks passed; activation unverified | Palette/Lua checks and Omarchy template rendering in a temporary home passed. The live theme was not applied |
| Update window | Stand-in checks passed; real update unverified | Backend stand-in and offscreen view passed. No real system update was run |
| Workspace shortcut targets | Model and UI checks passed | Real pinned-key behavior, monitor unplug/reconnect and Preview/Keep rollback |
| Host crash stability | Not established | Finite passing checks cannot prove a timing-dependent Qt/Quickshell crash fixed; see the bar's [stability notes](https://github.com/Velunori/bar/blob/main/docs/stability.md) |

## Repeating the checks

From a checkout with initialized submodules:

```bash
bash components/lib/scripts/check.sh
bash components/bar/scripts/check.sh
bash components/theme/scripts/check.sh
for c in clock control-center notifications menu weather update lockscreen; do
  VELUNORI_TEST_LAYOUT=copy bash components/$c/scripts/check.sh
  VELUNORI_TEST_LAYOUT=symlink bash components/$c/scripts/check.sh
done
python3 -B -m unittest discover -s installer/tests -v
```

For the dependency-dependent calendar tests, run `bash components/clock/scripts/setup-deps.sh`, then `components/clock/.venv/bin/python -B -m unittest discover -s components/clock/tests -p 'test_*.py'`.

Before installing, run `bash install.sh check` with your intended selection from an unlocked Omarchy desktop terminal. That read-only prerequisite check is machine-specific and does not replace live validation.
