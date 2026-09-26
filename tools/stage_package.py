#!/usr/bin/env python3
"""
tools/stage_package.py -- assemble the gpconf package from a public export, build it, and audit what was built.

    python3 tools/stage_package.py --export EXPORT --out STAGE [--build DIST]
    python3 tools/stage_package.py --export EXPORT --audit ARCHIVE [ARCHIVE ...]

The only input is a public export folder, the output of tools/export_public.py (D-153, D-156). The package is built
from it and never from the private repository, whose expected.json files still hold the SupGP values the export
scrubs. The script refuses a folder that lacks EXPORT-MANIFEST.txt, holds any provider file (fixtures/<case>/raw/),
or holds docs/handoff/, which only the private repository has.

Staging (--out, an empty or absent folder) copies pyproject.toml, README.md and LICENSE; the whole gpconf package,
walked recursively so that no subfolder can be missed (the fault D-151 and D-153 found in two patterns written for a
flat package); and the shipped corpus files into gpconf/corpus/: manifest.json, tools/fetchlist.json, every
fixtures/<case>/expected.json and case.md, derived/ and vectors/. Every staged file must match the export manifest's
SHA-256, so an export changed after it was made is refused.

README.md is staged as the PyPI description, with every relative link and image made absolute (D-159): PyPI shows the
README as the project page, where a link to a file in the repository does not resolve. The repository's README keeps its
relative links, which resolve on GitHub, in a clone, in a fork and at any tag; only the staged copy is rewritten, to
https://github.com/hneogy/gp-omm-conformance/blob/v<version>/<path> (tree/ for a folder, raw.githubusercontent.com for an
image), the tag of the version being built, so the page links to the files of the version a user installed. A relative
link to a path the export does not hold is refused, since the page would carry a dead link. Code is left alone.

Building (--build, with the `build` frontend and setuptools installed) runs `python -m build --no-isolation` on the
staged tree, which makes the sdist and then the wheel from it, and audits both.

Auditing (--audit, or after --build) opens a wheel or an sdist and checks every file under gpconf/ against the export
manifest: a corpus file under gpconf/corpus/X must hash to the manifest's entry for X, a package file to its own
entry. It fails on a hash mismatch, a file the manifest does not list, a provider file, any other unexpected member,
or a staged file that is missing from the archive; README.md must be the staged PyPI copy, and the long description in
the archive's metadata (PKG-INFO, or the wheel's METADATA), which is what PyPI shows, must hold no relative link.

Standard library only.
"""
import argparse
import glob
import hashlib
import os
import posixpath
import re
import subprocess
import sys
import tarfile
import zipfile

MANIFEST = "EXPORT-MANIFEST.txt"
TOP = ["pyproject.toml", "README.md", "LICENSE"]
CORPUS = ["manifest.json", "tools/fetchlist.json", "fixtures/*/expected.json", "fixtures/*/case.md", "derived/**/*", "vectors/**/*"]
BUNDLED = "gpconf/corpus"
RAW = re.compile(r"(^|/)fixtures/[^/]+/raw(/|$)")
SDIST_OTHER = re.compile(r"^(PKG-INFO|setup\.cfg|pyproject\.toml|README\.md|LICENSE|gpconf\.egg-info/.+)$")
WHEEL_OTHER = re.compile(r"^gpconf-[^/]+\.dist-info/.+$")
REPO_URL = "https://github.com/hneogy/gp-omm-conformance"
RAW_URL = "https://raw.githubusercontent.com/hneogy/gp-omm-conformance"


class Refused(Exception):
    """The input is not a public export, or the staged or built files do not match it."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_manifest(export):
    """EXPORT-MANIFEST.txt -> {path: sha256}. Lines are 'path<TAB>bytes<TAB>sha256'; '#' lines are comments."""
    path = os.path.join(export, MANIFEST)
    if not os.path.isfile(path):
        raise Refused(f"{export} has no {MANIFEST}: not a public export (make one with tools/export_public.py)")
    out = {}
    for line in open(path, encoding="utf-8"):
        if not line.strip() or line.startswith("#"):
            continue
        rel, _size, sha = line.rstrip("\n").split("\t")
        out[rel] = sha
    return out


def check_export(export):
    """Refuse anything that is not a clean public export; return its manifest."""
    manifest = read_manifest(export)
    if os.path.isdir(os.path.join(export, "docs", "handoff")):
        raise Refused(f"{export} holds docs/handoff/: that is the private repository, not a public export")
    for base, dirs, files in os.walk(export):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), export).replace(os.sep, "/")
            if RAW.search(rel):
                raise Refused(f"{export} holds a provider file, {rel}: provider data is never packaged (D-019)")
    return manifest


def plan(export):
    """-> [(source relative to the export, destination relative to the staged tree)]."""
    pairs = [(t, t) for t in TOP]
    for base, dirs, files in os.walk(os.path.join(export, "gpconf")):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith("."))
        for f in sorted(files):
            if f.startswith(".") or f.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(base, f), export).replace(os.sep, "/")
            if rel.startswith(BUNDLED + "/"):
                raise Refused(f"{export} already holds {rel}: the corpus is copied into gpconf/corpus/ only when staging")
            pairs.append((rel, rel))
    corpus = set()
    for pattern in CORPUS:
        for m in glob.glob(os.path.join(export, pattern), recursive=True):  # glob skips dotfiles
            if os.path.isfile(m):
                corpus.add(os.path.relpath(m, export).replace(os.sep, "/"))
    pairs += [(rel, f"{BUNDLED}/{rel}") for rel in sorted(corpus)]
    return pairs


def stage(export, out):
    """Copy the planned files into out and check each against the export manifest -> the plan."""
    manifest = check_export(export)
    if os.path.exists(out) and os.listdir(out):
        raise Refused(f"{out} is not empty")
    pairs = plan(export)
    for src, dest in pairs:
        data = open(os.path.join(export, src), "rb").read()
        if manifest.get(src) != sha256_bytes(data):
            raise Refused(f"{src} does not match {MANIFEST}: the export was changed after it was made")
        if src == "README.md":  # the PyPI description, relative links made absolute (D-159)
            data = staged_readme(export)[0]
        target = os.path.join(out, dest)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    return pairs


# --------------------------------------------------------------------------- the README as the PyPI description (D-159)
SCHEME = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
INLINE = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*(<[^>]*>|[^()\s]+(?:\([^()\s]*\)[^()\s]*)*)(\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REFDEF = re.compile(r"(?m)^( {0,3}\[[^\]]+\]:[ \t]*)(<[^>]*>|\S+)")
HTML_ATTR = re.compile(r"""((?:href|src)\s*=\s*)(["'])([^"']*)(\2)""", re.I)


def version_of(export):
    """The version in the export's pyproject.toml; the tag is v<version>."""
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', open(os.path.join(export, "pyproject.toml"), encoding="utf-8").read())
    if not m:
        raise Refused(f"no version in {export}/pyproject.toml")
    return m.group(1)


def _absolute(target, tag, kind_of, image):
    """One link target -> its absolute form, or None when it is absolute already."""
    bare = target[1:-1] if target.startswith("<") and target.endswith(">") else target
    if not bare or SCHEME.match(bare):
        return None
    if bare.startswith("#"):  # an in-page anchor: GitHub's heading ids are not certain on PyPI [inferred]; point at GitHub
        return f"{REPO_URL}/blob/{tag}/README.md{bare}"
    m = re.match(r"^([^#?]*)(.*)$", bare)
    path, suffix = posixpath.normpath(m.group(1)), m.group(2)  # suffix: the fragment or query, kept as written
    path = path.lstrip("/")  # GitHub resolves /path from the repository root
    if path.startswith("../") or path == "..":
        raise Refused(f"README.md links to {bare}, outside the repository: the PyPI page would carry a dead link")
    kind = kind_of(path)
    if kind is None:
        raise Refused(f"README.md links to {bare}, which the export does not hold: the PyPI page would carry a dead link")
    if image:
        url = f"{RAW_URL}/{tag}/{path}"
    else:
        url = f"{REPO_URL}/{'tree' if kind == 'dir' else 'blob'}/{tag}/{path}"
    return url + suffix


def relative_links(text):
    """-> the relative link and image targets outside code, in order: what PyPI could not resolve."""
    found = []
    pypi_readme(text, "v0", lambda p: "file", found=found)
    return found


def pypi_readme(text, tag, kind_of, found=None):
    """README text -> the PyPI description: relative links, images, reference definitions and HTML href/src made
    absolute and pinned to `tag`. Fenced code blocks and code spans are left as they are. kind_of(path) -> 'file',
    'dir' or None (absent: refused). `found`, if given, collects the relative targets rewritten."""
    def fix(target, image):
        new = _absolute(target, tag, kind_of, image)
        if new is not None and found is not None:
            found.append(target)
        return new

    def inline(m):
        bang, label, target, title = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        label = INLINE.sub(inline, label)  # an image inside a link's text
        new = fix(target, bool(bang))
        return f"{bang}[{label}]({new if new is not None else target}{title})"

    def prose(s):
        spans = []
        s = CODE_SPAN.sub(lambda m: spans.append(m.group(0)) or f"\x00{len(spans) - 1}\x00", s)
        s = INLINE.sub(inline, s)
        s = REFDEF.sub(lambda m: m.group(1) + (fix(m.group(2), False) or m.group(2)), s)
        s = HTML_ATTR.sub(lambda m: m.group(1) + m.group(2) + (fix(m.group(3), m.group(1).lower().startswith("src")) or m.group(3)) + m.group(4), s)
        return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], s)

    out, block, fence = [], [], None
    for line in text.splitlines(keepends=True):
        opener = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and opener:
            out.append(prose("".join(block)))
            block, fence = [line], opener.group(1)
        elif fence is not None:
            block.append(line)
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                out.append("".join(block))
                block, fence = [], None
        else:
            block.append(line)
    out.append("".join(block) if fence is not None else prose("".join(block)))
    return "".join(out)


def staged_readme(export):
    """-> (the export's README.md as the PyPI description, the relative targets made absolute)."""
    def kind_of(path):
        full = os.path.join(export, *path.split("/"))
        return "dir" if os.path.isdir(full) else "file" if os.path.isfile(full) else None
    found = []
    text = pypi_readme(open(os.path.join(export, "README.md"), encoding="utf-8").read(), "v" + version_of(export), kind_of, found)
    return text.encode("utf-8"), found


def expected_top(export, manifest):
    """-> {top-level file: SHA-256 as staged}: the export's own for pyproject.toml and LICENSE, the PyPI copy for README.md."""
    top = {name: manifest.get(name) for name in TOP}
    top["README.md"] = sha256_bytes(staged_readme(export)[0])
    return top


def long_description(name, data):
    """The long description in an sdist's PKG-INFO or a wheel's METADATA: the body after the header block."""
    if not (name == "PKG-INFO" or name.endswith(".dist-info/METADATA")):
        return None
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    return text.split("\n\n", 1)[1] if "\n\n" in text else ""


def members(archive):
    """-> {path inside the package tree: bytes}, with an sdist's top folder removed."""
    out = {}
    if archive.endswith(".whl"):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if not n.endswith("/"):
                    out[n] = z.read(n)
        return out
    with tarfile.open(archive, "r:gz") as t:
        for m in t.getmembers():
            if m.isfile():
                name = m.name.split("/", 1)[1] if "/" in m.name else m.name
                out[name] = t.extractfile(m).read()
    return out


def audit(archive, manifest, pairs, top=None):
    """-> (report lines, problems). Every file under gpconf/ is checked against the export manifest; the top-level
    files against `top` (expected_top(): README.md as staged for PyPI), and the long description for relative links."""
    top = top or {name: manifest.get(name) for name in TOP}
    got = members(archive)
    kind = "wheel" if archive.endswith(".whl") else "sdist"
    other = WHEEL_OTHER if kind == "wheel" else SDIST_OTHER
    problems, corpus_ok, package_ok, extra = [], 0, 0, []
    for name, data in sorted(got.items()):
        if RAW.search(name):
            problems.append(f"provider file in the {kind}: {name}")
            continue
        if name.startswith(BUNDLED + "/"):
            key, bucket = name[len(BUNDLED) + 1:], "corpus"
        elif name.startswith("gpconf/"):
            key, bucket = name, "package"
        elif other.match(name):
            extra.append(name)
            if name in TOP and top.get(name) != sha256_bytes(data):
                problems.append(f"{name} in the {kind} does not match {MANIFEST}" + (" as staged for PyPI" if name == "README.md" else ""))
            description = long_description(name, data)
            if description is not None:
                problems += [f"relative link in the long description ({name}), which PyPI cannot resolve: {r}" for r in relative_links(description)]
            continue
        else:
            problems.append(f"unexpected file in the {kind}: {name}")
            continue
        want = manifest.get(key)
        if want is None:
            problems.append(f"{name} in the {kind} is not listed in {MANIFEST} (as {key})")
        elif want != sha256_bytes(data):
            problems.append(f"{name} in the {kind} differs from the export ({key}: SHA-256 mismatch)")
        elif bucket == "corpus":
            corpus_ok += 1
        else:
            package_ok += 1
    staged = {dest for _, dest in pairs if dest.startswith("gpconf/")}
    missing = sorted(staged - set(got))
    problems += [f"staged file missing from the {kind}: {m}" for m in missing]
    report = [f"{os.path.basename(archive)}: {len(got)} files; {corpus_ok} corpus files and {package_ok} package files "
              f"match {MANIFEST}; {len(extra)} {'metadata' if kind == 'wheel' else 'build'} files; "
              f"{len(problems)} problem(s)"]
    return report, problems


def build(staged, dist):
    try:
        import build  # noqa: F401  (the frontend; setuptools is its backend here)
        import setuptools  # noqa: F401
    except ImportError as e:
        raise Refused(f"building needs the `build` frontend and setuptools in this interpreter ({e}); install them into "
                      "a separate environment, never into the runner's") from e
    os.makedirs(dist, exist_ok=True)
    p = subprocess.run([sys.executable, "-m", "build", "--no-isolation", "--outdir", dist, staged], capture_output=True, text=True)
    if p.returncode != 0:
        raise Refused(f"the build failed (exit {p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return sorted(os.path.join(dist, f) for f in os.listdir(dist) if f.endswith((".whl", ".tar.gz")))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, help="a public export folder (tools/export_public.py --dest)")
    ap.add_argument("--out", help="the staging folder, empty or absent")
    ap.add_argument("--build", metavar="DIST", help="build the sdist and the wheel into DIST and audit both")
    ap.add_argument("--audit", nargs="+", metavar="ARCHIVE", help="audit wheels or sdists already built")
    a = ap.parse_args(argv)
    try:
        manifest = check_export(a.export)
        pairs = plan(a.export)
        top = expected_top(a.export, manifest)
        archives = list(a.audit or [])
        if a.out:
            stage(a.export, a.out)
            links = staged_readme(a.export)[1]
            print(f"staged {len(pairs)} files into {a.out}: {sum(1 for _, d in pairs if d.startswith(BUNDLED + '/'))} corpus files, "
                  f"{sum(1 for _, d in pairs if d.startswith('gpconf/') and not d.startswith(BUNDLED + '/'))} package files, "
                  f"{len(TOP)} top-level files; every one matches {MANIFEST}; README.md staged as the PyPI description with "
                  f"{len(links)} relative link(s) made absolute at v{version_of(a.export)}: {', '.join(links) or 'none'}")
            if a.build:
                archives += build(a.out, a.build)
        elif a.build:
            ap.error("--build needs --out")
        failed = False
        for archive in archives:
            report, problems = audit(archive, manifest, pairs, top)
            print("\n".join(report))
            for p in problems:
                print(f"  PROBLEM: {p}")
            failed = failed or bool(problems)
        return 1 if failed else 0
    except Refused as e:
        print(f"stage_package: refused: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
