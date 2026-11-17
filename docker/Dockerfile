# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
#
# gpconf and its Node presets in one image (0.9.0 item c5, D-435), built from the released wheel on PyPI.
# NOT BUILT: written 2026-11-10; the image, its name (ghcr.io/hneogy/gpconf, the owner's ruling, D-378) and its
# publication are the owner's, on the release. Build from this folder:
#
#     docker build --build-arg GPCONF_VERSION=0.10.0 -t gpconf:0.10.0 docker/
#     docker run --rm -v "$PWD:/work" -w /work gpconf:0.10.0 run --preset sgp4
#
# The Node presets resolve their libraries from the working directory (gpconf/presets.py), so the image keeps them in
# /opt/gpconf-node and passes --module for each: `run --preset satellite.js --module /opt/gpconf-node/node_modules/satellite.js/dist/index.js`
# [untested: the entry file's path inside the package]. The provider files are fetched by the user, never baked in:
# mount a corpus checkout or a fetched data folder at /work.
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ARG GPCONF_VERSION
ARG SGP4_VERSION=2.27
ARG EPHEM_VERSION=4.2.1
ARG SATELLITEJS_VERSION=7.1.0
ARG TLEJS_VERSION=5.0.3

# Node for the satellite.js and tle.js presets, from Debian's packages
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm \
 && rm -rf /var/lib/apt/lists/*

# gpconf from PyPI at the released version, with the libraries its Python presets were tested with
RUN test -n "${GPCONF_VERSION}" \
 && pip install --no-cache-dir "gpconf==${GPCONF_VERSION}" "sgp4==${SGP4_VERSION}" "ephem==${EPHEM_VERSION}"

# the Node presets' libraries, pinned to the versions the presets were tested with
WORKDIR /opt/gpconf-node
RUN npm init -y >/dev/null \
 && npm install --no-audit --no-fund "satellite.js@${SATELLITEJS_VERSION}" "tle.js@${TLEJS_VERSION}"

# no network is needed to grade: the corpus's own files ship in the wheel; `gpconf fetch` is the one command that
# makes requests, and only when run
RUN useradd --create-home gpconf
USER gpconf
WORKDIR /work
ENTRYPOINT ["gpconf"]
CMD ["presets"]
