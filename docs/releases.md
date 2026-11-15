# Bundle releases

A bundle release pins all nine component commits. Components do not need matching version numbers. The first candidate is `v0.1.0-rc.1`; it remains a prerelease until live validation justifies a stable release.

## Installing a published release

Check that the tag exists on the repository's Releases page before using it. For a new installation, replace `<tag>` with the chosen published tag:

```bash
git clone --branch <tag> --recurse-submodules https://github.com/Velunori/velunori.git ~/.local/share/velunori
cd ~/.local/share/velunori
bash scripts/install.sh --check
bash scripts/install.sh --dry-run
bash scripts/install.sh
```

This produces a detached checkout of the release. Keep the same selection flags throughout. See the README for prerequisites, installation effects and recovery.

## Moving between releases

Preserve local edits first. Use your existing installation directory and replace `<tag>` with the selected published release:

```bash
cd ~/.local/share/velunori
git fetch origin --tags
git switch --detach <tag>
git submodule update --init --recursive
bash scripts/install.sh --check
bash scripts/install.sh
```

Use the same installation flags as before. Switching submodules changes linked files and may reload the shell before installation completes. Returning to an earlier tag restores its source revisions, but does not undo data migrations, Python dependency changes, theme application or configuration edits. Follow the README's recovery instructions when configuration restoration is needed.

The README's `git pull --ff-only` update sequence applies to a branch checkout, not a detached release checkout. Do not use `git submodule update --remote` for a pinned release.

## Preparing a release

1. Update `VERSION` and `CHANGELOG.md`, and review all nine submodule pins.
2. Run `bash -n scripts/install.sh` and `python3 -B -m unittest discover -s tests -v`. Run relevant component checks separately. Record actual results and distinguish automated validation from live checks.
3. Commit the reviewed source and create an annotated tag matching `VERSION`, for example `git tag -a v0.1.0-rc.1 -m 'Velunori 0.1.0 release candidate 1'`. Never tag an older commit while release changes remain uncommitted.
4. Run `python3 scripts/package-release.py v0.1.0-rc.1 --output dist/v0.1.0-rc.1`. Repeat into a separate output directory and compare checksums.
5. Publish the commit and tag, then attach the generated `.tar.gz`, `.json` and `SHA256SUMS` to a GitHub prerelease. Use the changelog entry as release notes, including its validation limits.

The packager reads committed Git objects and the exact gitlink revisions. Untracked files, private virtual environments, caches and user data are excluded. A component's pinned Git object must be present locally. The JSON manifest records the bundle commit and every component commit. Tar and gzip metadata are normalized so the same source produces identical bytes.

GitHub's automatic source archives omit submodule contents. Use the attached complete archive if you need an offline source copy. Check it with `sha256sum -c SHA256SUMS` after downloading all three assets. Checksums detect accidental corruption; they are not a separate publisher signature. Git installation is recommended for updates; extracted archives have no Git history.

Reproducibility covers source files, not the entire runtime: system packages and cloud calendar Python requirements are not locked by this bundle. Passing automated tests does not establish live installation, small-screen placement, cloud authentication/synchronization, session locking or theme compatibility. These must be reported separately before promoting a candidate to stable.
