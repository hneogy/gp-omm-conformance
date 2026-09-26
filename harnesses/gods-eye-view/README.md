# gods-eye-view (bilawalsidhu/gods-eye-view)

| | |
|---|---|
| tested at | main `ce671ce500a393be27e3cbb2a08799fbca9b6e28` (2026-09-24) |
| licence of the application | MIT (its `LICENSE` file; GitHub's licence detector reports it as unrecognised) |
| what the harness compiles against | the application's satellites layer, imported by its internal module paths, `src/layers/satellites/ingestion.js` and `orbits.js`, and driven through the layer's own `parseTLE`, `twoline2satrec`, `Number(satrec.satnum)` and dedupe path. satellite.js is the version the application's lockfile resolves, 6.0.2. The `cesium` package is replaced by a stand-in for the seven names the layer's update path touches, through a Node loader hook (`register.mjs`, `cesium-hook.mjs`, `cesium-stub.mjs`), and propagation is stubbed so that an old epoch cannot hide a parse result |
| toolchain as run | Node.js 26.5.0, macOS; run on 2026-09-24 |
| published result | 6 of 17 cases failed, with the runner of 2026-09-24 (corpus D-136) |

Best-effort, not installable by pip. This harness runs inside an application, not against a library: it imports
internal modules by their paths in the tree and reproduces the layer state they expect. If the application moves or
renames those modules, changes the state the layer keeps, or touches more of Cesium, the harness may fail to start,
or run and read differently, with nothing to say so. Results hold for the commit above.

`harness.mjs` serves a corpus file as the one CelesTrak group that answers, lets the layer ingest it, and prints the
layer's catalog as JSON records. TLE and 2LE only.

## Set up

The harness expects the application's tree in a folder named `main` next to it, and satellite.js installed in this
folder, from where the application's modules find it:

```bash
git clone https://github.com/bilawalsidhu/gods-eye-view.git main
git -C main checkout ce671ce500a393be27e3cbb2a08799fbca9b6e28
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
