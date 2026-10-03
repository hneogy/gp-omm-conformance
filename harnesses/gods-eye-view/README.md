# gods-eye-view (bilawalsidhu/gods-eye-view)

| | |
|---|---|
| tested at | release v0.2.1, `aa16b7c3b0166a89d8c7a6089e0aff53a22faaee` (2026-10-03), which was also `main` that day; before it, `main` at `ce671ce500a393be27e3cbb2a08799fbca9b6e28` (2026-09-24) |
| licence of the application | MIT (its `LICENSE` file; GitHub's licence detector reports it as unrecognised) |
| what the harness compiles against | the application's satellites layer, imported by its internal module paths, `src/layers/satellites/ingestion.js` and `orbits.js`, and driven through the layer's own `parseTLE`, `twoline2satrec`, `Number(satrec.satnum)` and dedupe path. Since v0.2.0 the reader is `parseTleText()` in `src/sources/tle.js`, which `orbits.js` hands to the layer as `parseTLE`; at `ce671ce` the same code was in `orbits.js` itself, and the harness reaches it the same way at both. satellite.js is the version the application's lockfile resolves, 6.0.2 at both commits. The `cesium` package is replaced by a stand-in for the seven names the layer's update path touches, through a Node loader hook (`register.mjs`, `cesium-hook.mjs`, `cesium-stub.mjs`), and propagation is stubbed so that an old epoch cannot hide a parse result |
| toolchain as run | Node.js 26.5.0, macOS; run on 2026-09-24 at `ce671ce` and on 2026-10-03 at v0.2.1 |
| published result | 6 of 17 cases failed at `ce671ce`, with the runner of 2026-09-24 (corpus D-136), which was the row on the site until 2026-10-03; at `ce671ce` on v0.4.0's eighteen cases, 7 of 18 (corpus D-179); release v0.2.1 on corpus v0.5.0's eighteen cases, 7 of 18, every item as at `ce671ce` (corpus D-221), which is the row on the site since 2026-10-03 |

Best-effort, not installable by pip. This harness runs inside an application, not against a library: it imports
internal modules by their paths in the tree and reproduces the layer state they expect. If the application moves or
renames those modules, changes the state the layer keeps, or touches more of Cesium, the harness may fail to start,
or run and read differently, with nothing to say so. Results hold for the commits above: between them the application
moved its reader into another file, and the same harness files ran at both, unchanged.

What the 7 of 18 rests on. Five of the seven failing cases fail on the mean motion: satellite.js 6.0.2, the
application's dependency, replaces that value with the model's own and does not keep it as printed, so the harness,
which returns what the application holds, cannot return it. That is a property of that version of the library, not a
fault of the application. Three of the five fail on nothing else, and two also on a name-less 2LE file, a form the
application does not read. The other two are the Alpha-5 case, where every Alpha-5 set collapses onto one catalog
entry (the application's issue #751), and the corrupt-input case, which fails on a set with no line 2 and the valid
set after it (issue #906) and on two inputs that satellite.js reads with no error, a line one character short and the
letter O in the epoch field. The first count, 6 of 17, rested on the same value for five of its six (corpus D-224).

`harness.mjs` serves a corpus file as the one CelesTrak group that answers, lets the layer ingest it, and prints the
layer's catalog as JSON records. TLE and 2LE only.

## Set up

The harness expects the application's tree in a folder named `main` next to it, and satellite.js installed in this
folder, from where the application's modules find it:

```bash
git clone https://github.com/bilawalsidhu/gods-eye-view.git main
git -C main checkout aa16b7c3b0166a89d8c7a6089e0aff53a22faaee
npm install satellite.js@6.0.2
```

## Run

Note this folder, then run the corpus runner from the root of a corpus clone (or from anywhere, once `gpconf` is
installed); the command changes into this folder so that the loader hook and the `main` tree resolve:

```bash
H="$PWD"
cd ../..
python3 -m gpconf run --cmd "cd '$H' && node --import ./register.mjs harness.mjs {fmt}"
```
