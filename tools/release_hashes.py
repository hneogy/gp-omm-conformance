#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/release_hashes.py -- the maintainer's SHA-256 of a release's two files, carried in the annotated tag's message,
and the check that another build of the tag matches them (D-361).

    python3 tools/release_hashes.py message --dist DIST --pyproject PYPROJECT [--epoch SECONDS]
    python3 tools/release_hashes.py check --dist DIST --pyproject PYPROJECT --tag TAG --message FILE
                                          [--github-output FILE] [--summary FILE]

A release's wheel and sdist are built twice, the same way: by the maintainer, from an archive of the commit to be
tagged, with tools/stage_package.py and that commit's time as SOURCE_DATE_EPOCH (D-203); and by
.github/workflows/publish.yml, from the pushed tag, on a GitHub runner. The runner's files are published only when they
are byte for byte the maintainer's. The maintainer's hashes travel in the annotated tag's message, not in a file of the
tree: the tree is what is built, and the epoch is the tagged commit's own time, so a hash file in that commit would
have to exist before the build that gives its contents.

`message` prints the tag message for the two files in DIST: the subject "gp-omm-conformance <version>", a sentence,
and one line per file in the format `sha256sum` and `shasum -a 256` print, "<64 lowercase hex>  <file name>".

`check` passes only when the tag is v<version>; DIST holds the two files the version names,
gpconf-<version>-py3-none-any.whl and gpconf-<version>.tar.gz, and nothing else; the message holds exactly one hash
line for each and no other line with a SHA-256 in it; and each file hashes to its line. Lines without a SHA-256 (the
subject, the sentence, a signature) are not read. With --github-output, a passing check writes the version, the two
file names and their hashes there, for the job that publishes them.

Exit 0: both files match. Exit 1: a file differs from the maintainer's. Exit 2: refused, the input is not a release
(a missing or extra file, a missing, repeated or malformed hash line, a tag that does not name the version).

Standard library only; Python 3.9 and later.
"""
import argparse
import hashlib
import os
import re
import sys

SUBJECT = "gp-omm-conformance {version}"
SENTENCE = ("SHA-256 of the maintainer's build of this tag (tools/stage_package.py, SOURCE_DATE_EPOCH {epoch}). "
            ".github/workflows/publish.yml builds the tag again and publishes nothing unless its files have these hashes.")
HASH_RUN = re.compile(r"[0-9A-Fa-f]{64}")
HASH_LINE = re.compile(r"^([0-9a-f]{64})  ([^\s/\\]+)$")
# A version as setuptools writes it into the file names, so that the names below are the ones the build makes; and
# nothing that could carry a line break or a path into the outputs.
VERSION = re.compile(r"^[0-9]+(\.[0-9]+)*((a|b|rc)[0-9]+)?(\.post[0-9]+)?(\.dev[0-9]+)?$")


class Refused(Exception):
    """The input is not a release: the check is not made."""


def version_by_pattern(text):
    """[project].version read without a TOML parser (Python 3.9 and 3.10, which have no tomllib): the first
    `version = "..."` or `version = '...'` line of the [project] table, a comment after it allowed; None if there is
    none."""
    table = re.search(r"(?ms)^\[project\][ \t]*(?:#[^\n]*)?$(.*?)(?=^[ \t]*\[|\Z)", text)
    m = table and re.search(r"""(?m)^[ \t]*version[ \t]*=[ \t]*(?:"([^"\n\\]*)"|'([^'\n]*)')[ \t]*(?:#[^\n]*)?$""", table.group(1))
    return (m.group(1) if m.group(1) is not None else m.group(2)) if m else None


def version_of(pyproject):
    """The version in pyproject.toml's [project] table, which names the tag and the two files: read with tomllib where
    Python has it (3.11 and later), as the build reads it, and by version_by_pattern() before that."""
    try:
        with open(pyproject, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise Refused(f"cannot read {pyproject}: {e}") from None
    try:
        import tomllib
    except ImportError:
        version = version_by_pattern(text)
    else:
        try:
            project = tomllib.loads(text).get("project")
        except tomllib.TOMLDecodeError as e:
            raise Refused(f"{pyproject} is not TOML: {e}") from None
        version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str):
        raise Refused(f"no [project] version in {pyproject}")
    if not VERSION.fullmatch(version):
        raise Refused(f"the version in {pyproject}, {version!r}, is not one this check knows the file names of")
    return version


def release_files(version):
    """-> (the wheel's name, the sdist's name) for a version."""
    return f"gpconf-{version}-py3-none-any.whl", f"gpconf-{version}.tar.gz"


def dist_files(dist, version):
    """Refuse a DIST that holds anything but the release's two files, each a plain file -> their names."""
    names = release_files(version)
    if not os.path.isdir(dist):
        raise Refused(f"{dist} is not a folder")
    present = sorted(os.listdir(dist))
    if present != sorted(names):
        raise Refused(f"{dist} must hold exactly {names[0]} and {names[1]}, and holds: {', '.join(present) or 'nothing'}")
    for name in names:
        path = os.path.join(dist, name)
        if os.path.islink(path) or not os.path.isfile(path):
            raise Refused(f"{path} is not a plain file")
    return names


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def message(dist, version, epoch=None):
    """-> the annotated tag's message for the two files in dist."""
    names = dist_files(dist, version)
    lines = [SUBJECT.format(version=version), "", SENTENCE.format(epoch=epoch if epoch is not None else "as recorded")]
    lines += [f"{sha256_file(os.path.join(dist, n))}  {n}" for n in names]
    return "\n".join(lines) + "\n"


def parse_message(text, version):
    """A tag message -> {file name: SHA-256}, refusing anything but one well-formed line for each of the two files."""
    names = release_files(version)
    found = {}
    for number, line in enumerate(text.split("\n"), 1):
        if not HASH_RUN.search(line):
            continue
        m = HASH_LINE.match(line)
        if not m:
            raise Refused(f"line {number} of the tag message holds a SHA-256 but is not '<64 lowercase hex>  <file name>': {line!r}")
        digest, name = m.groups()
        if name not in names:
            raise Refused(f"line {number} of the tag message names {name}, which is not one of this release's files, "
                          f"{names[0]} and {names[1]}")
        if name in found:
            raise Refused(f"the tag message gives a SHA-256 for {name} twice")
        found[name] = digest
    missing = [n for n in names if n not in found]
    if missing:
        raise Refused(f"the tag message gives no SHA-256 for {' or '.join(missing)}")
    return found


def check(dist, version, tag, text):
    """-> (names, {name: built SHA-256}, {name: the message's SHA-256}); refused when the input is not a release."""
    if tag != "v" + version:
        raise Refused(f"the tag is {tag!r}, and this tree's version, {version}, is tagged v{version}")
    want = parse_message(text, version)
    names = dist_files(dist, version)
    got = {n: sha256_file(os.path.join(dist, n)) for n in names}
    return names, got, want


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    m = sub.add_parser("message", help="print the tag message for the two files in DIST")
    m.add_argument("--dist", required=True)
    m.add_argument("--pyproject", required=True)
    m.add_argument("--epoch", type=int, help="the SOURCE_DATE_EPOCH of the build, named in the message")
    c = sub.add_parser("check", help="check the two files in DIST against a tag message")
    c.add_argument("--dist", required=True)
    c.add_argument("--pyproject", required=True)
    c.add_argument("--tag", required=True)
    c.add_argument("--message", required=True, metavar="FILE", help="the annotated tag's message")
    c.add_argument("--github-output", metavar="FILE", help="on a match, append the names and hashes here")
    c.add_argument("--summary", metavar="FILE", help="append a summary of the check here (Markdown)")
    a = ap.parse_args(argv)
    try:
        version = version_of(a.pyproject)
        if a.command == "message":
            sys.stdout.write(message(a.dist, version, a.epoch))
            return 0
        try:
            with open(a.message, encoding="utf-8", newline="") as f:   # a CR stays a CR, and fails the line it is on
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise Refused(f"cannot read the tag message {a.message}: {e}") from None
        names, got, want = check(a.dist, version, a.tag, text)
    except Refused as e:
        print(f"release_hashes: refused: {e}", file=sys.stderr)
        return 2
    differ = [n for n in names if got[n] != want[n]]
    report = []
    for n in names:
        report.append(f"{n}: {'MATCH' if n not in differ else 'DIFFERS'}")
        report.append(f"  built      {got[n]}")
        report.append(f"  maintainer {want[n]}")
    print("\n".join(report))
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(f"### {a.tag}: the build against the maintainer's hashes\n\n")
            for n in names:
                f.write(f"- `{n}`: **{'MATCH' if n not in differ else 'DIFFERS'}**, built `{got[n]}`, maintainer `{want[n]}`\n")
            f.write("\n")
    if differ:
        print(f"release_hashes: {' and '.join(differ)} differ{'s' if len(differ) == 1 else ''} from the maintainer's build: "
              "nothing is published", file=sys.stderr)
        return 1
    if a.github_output:
        wheel, sdist = names
        with open(a.github_output, "a", encoding="utf-8") as f:
            f.write(f"version={version}\nwheel={wheel}\nwheel-sha256={got[wheel]}\nsdist={sdist}\nsdist-sha256={got[sdist]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
