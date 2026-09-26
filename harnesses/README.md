# Recipes for the libraries that cannot be presets

In September 2026 the corpus ran eight libraries by hand (decisions D-128 and D-132 to D-141). Three of them,
PyEphem, satellite.js and tle.js, now run as presets of the runner: `gpconf run --preset pyephem`, for example. The
other five cannot. Each compiles against another project's source, or runs inside an application, so it needs that
project's checkout and a toolchain. They are here as recipes.

A recipe is the harness source, the commit it was tested at, the build commands, and the command that runs it
through the corpus runner. The harness files are the corpus's own code, under this repository's licence. The
project's source is cloned by you, at the pinned commit, and nothing of it is copied here.

**Best-effort.** These recipes are not part of the `gpconf` package, and `pip install gpconf` does not install them.
Nothing in the corpus's CI builds them. They were built and run once, on the date given in each folder.

**They break silently.** Four of the five compile against the project's internals: source files, internal functions
and module paths that are not a published interface. When the project moves on, a harness may stop building, which
is the good case, or it may build and test something other than what the project's users run, with nothing to say
so. A result means something only at the pinned commit. At any other commit, read the harness against the project's
code before trusting a count.

| recipe | tested at | project licence | what the harness compiles against | toolchain |
|---|---|---|---|---|
| [libsgp4](libsgp4/) | master 661e057, and PR #42 at 2b8d141 | Apache-2.0 | the library's own classes (`Tle`, `DateTime`) and every `.cc` file of `libsgp4/` | a C++17 compiler (Apple clang 21 as run) |
| [gpredict](gpredict/) | tag v2.6, c9fa018 | GPL-2.0 | the internal SGP4 module `src/sgpsdp/` of the application, compiled on its own, with a stand-in for its one GLib call | a C compiler (Apple clang 21 as run) |
| [satdump](satdump/) | master f3d82ad, and release 1.2.2 at 7aef0fe | GPL-3.0 | internal source files of `src-core/` and its bundled predict fork | a C++17 compiler (Apple clang 21 as run), libcurl |
| [astroz](astroz/) | main d558933 | GPL-3.0 | the library's `src/Tle.zig`, used directly as a module | Zig 0.16.0 (as run; the harness uses interfaces new in 0.16) |
| [gods-eye-view](gods-eye-view/) | main ce671ce | MIT | the application's satellites layer, by its internal module paths, with Cesium stood in | Node.js (26.5.0 as run) |

The counts each run produced are in the hand-run table on the site's library page
(https://gpconf.neogy.dev/library/), recorded with the runner of 2026-09-24 (gpconf 0.2.1). Later runners add checks,
such as the provider's empty answers (D-143), so a run today can differ in its pass and skip counts. These five were
not run again when they moved here.

Each folder's README gives the pinned commit in full, the licence, what the harness compiles against, the build
commands as they were run, and the run command. Build in the recipe's folder; the commands clone the project into a
subfolder there.
