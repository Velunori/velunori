# Installer validation

Checked on 2026-11-16 on Omarchy 4.5.0-3, Quickshell 0.3.2.r7.g2b4501a-1 and Qt 6.12.0, using the submodule pins of `0.2.0-preview.1`.

- **Installer tests passed.** They cover dependency selection, stock-bar preservation, conflict protection, source integrity, confirmation, receipts, partial-failure recovery and concurrent-edit protection. The generated script is exercised with real packaged Clock/Control Center sources, native manifest validation and a stand-in activation host.
- **Piped interactive execution passed in a pseudo-terminal.** With no flags, it asks for full/custom selection, accepts an individual component and reads the final confirmation from the terminal rather than the script pipe. A piped `plan --all` also passes without a terminal. A retained downloaded script reports status correctly.
- **Reproducible build.** Building twice from the same pins produces identical bytes; the builder refuses dirty submodules.

No real theme activation, desktop lock/authentication, cloud sign-in or system update was performed. Real desktop installation and recovery, managed in-place upgrades and selection-aware removal remain open. Component checks are recorded in the [compatibility record](../docs/compatibility.md).
