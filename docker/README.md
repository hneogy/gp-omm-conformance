# The gpconf image (not built)

`Dockerfile` builds gpconf from the released wheel on PyPI, with the libraries its presets were tested with:
python-sgp4 2.27 and PyEphem 4.2.1, and satellite.js 7.1.0 and tle.js 5.0.3 under Node. It has not been built
[untested]: building it installs packages, which waits for the release and the owner's word, and the image's name and
registry (`ghcr.io/hneogy/gpconf`, the owner's ruling, D-378) and its publication are the owner's.

The plan's bar for it (item c5): the image's hash and the wheel inside it match the release, and an offline run
passes. Neither is measured yet.
