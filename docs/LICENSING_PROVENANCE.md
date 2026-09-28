# Licensing and Provenance Status

## Current status

The current `io_scene_bz2msh` fork contains code derived from the public
`frute94/io_scene_bz2msh` repository.

A review of the visible upstream Git history, from the initial 2021 commit through
the current upstream tree, found no standalone license file and no explicit
open-source license grant in the README or repository tree.

GitHub's Terms of Service permit public repositories to be viewed and forked
through GitHub's service. That permission is not equivalent to a general
open-source license granting redistribution, derivative-work, or relicensing
rights outside those service functions.

## Historical manifest declaration

This fork has historically declared `SPDX:MIT` in `blender_manifest.toml`.
That declaration is retained temporarily so the Blender Extension development
package can be validated and built, but it is **not treated as proof that the
inherited upstream implementation was released under MIT**.

No new claim is being made here that frute94 or ZerothDivision granted MIT,
GPL, or another open-source license.

## Release status

v1.3.0 is prepared as a **draft GitHub release** while provenance remains
unresolved. It should not be submitted to Blender's official Extensions Platform
in this state.

## Planned resolution

The intended clean resolution is to replace the remaining inherited
implementation with a provenance-documented implementation based on:

- independently documented MSH file-format behavior;
- observed input/output behavior and game/exporter behavior;
- public Blender Python API documentation;
- independently developed tests and validation corpora;
- factual constants, structures, and compatibility requirements.

The rewrite should avoid copying implementation expression from the unlicensed
upstream source.

Once inherited implementation has been removed or otherwise properly licensed,
the project can add an explicit project license and update the Blender manifest
accordingly.

For official publication on Blender's Extensions Platform, the target license
for the rewritten add-on is `GPL-3.0-or-later`.

## Historical credit

The provenance rewrite does not erase project history. The README should
continue to credit frute94 as the original plugin author and ZerothDivision for
the earlier fixes attributed by the upstream project.
