"""Where the corpus's own files are, and where the fetched provider data is (D-150).

Two roots. The corpus root holds what ships with the corpus: manifest.json, every fixtures/<case>/expected.json and
case.md, derived/, vectors/ and tools/fetchlist.json. It is read-only. The data root holds what the user's machine
fetched: fixtures/<case>/raw/<file> and its .meta.json, the same layout as in a clone. Provider data is never
shipped (D-019), so an installed runner keeps it in a folder of the user's.

Corpus root, first match wins:
  1. --root DIR;
  2. a clone: the folder above this package holds manifest.json and fixtures/;
  3. an installed copy: the corpus bundled as package data in gpconf/corpus/.

Data root, first match wins:
  1. --data DIR;
  2. the GPCONF_DATA environment variable;
  3. the corpus root itself, when that is a clone or was given with --root (the layout every clone has used);
  4. a per-user cache folder, one per corpus version:
     Linux and others  $XDG_CACHE_HOME/gpconf/<version>, or ~/.cache/gpconf/<version>
     macOS             ~/Library/Caches/gpconf/<version>
     Windows           %LOCALAPPDATA%\\gpconf\\Cache\\<version>

Standard library only.
"""
import json
import os
import sys

BUNDLED = "corpus"                 # gpconf/corpus/ in an installed copy
DATA_ENV = "GPCONF_DATA"


class CorpusNotFound(Exception):
    """No corpus at the given root, beside the package, or bundled with it."""


def package_dir():
    return os.path.dirname(os.path.abspath(__file__))


def is_corpus(path):
    return os.path.isfile(os.path.join(path, "manifest.json")) and os.path.isdir(os.path.join(path, "fixtures"))


def bundled_root():
    """gpconf/corpus/ as a real folder. importlib.resources is asked first, so that an unusual installer is caught:
    a package imported from a zip archive has no folder the runner could open, and is refused with a reason."""
    try:
        from importlib.resources import files
        res = files(__package__ or "gpconf") / BUNDLED
    except Exception:  # noqa: BLE001 -- any failure falls back to the package folder, which is what pip installs
        res = None
    if res is not None and not isinstance(res, os.PathLike):
        raise CorpusNotFound("gpconf is being imported from an archive, where its bundled corpus has no folder on disk; "
                             "install it as ordinary files (pip does) or pass --root")
    return os.fspath(res) if res is not None else os.path.join(package_dir(), BUNDLED)


def corpus_root(explicit=None):
    """-> (path, how), how in '--root' | 'clone' | 'installed'."""
    if explicit:
        path = os.path.abspath(os.path.expanduser(explicit))
        if not is_corpus(path):
            raise CorpusNotFound(f"--root {explicit}: no manifest.json and fixtures/ there")
        return path, "--root"
    clone = os.path.dirname(package_dir())
    if is_corpus(clone):
        return clone, "clone"
    bundled = bundled_root()
    if is_corpus(bundled):
        return bundled, "installed"
    raise CorpusNotFound(f"no corpus found: not a clone ({clone} has no manifest.json and fixtures/) and none bundled "
                         f"with the package ({bundled}); pass --root to a copy of the corpus")


def corpus_version(root):
    with open(os.path.join(root, "manifest.json")) as f:
        return json.load(f)["corpus_version"]


def user_cache_dir(version, env=None, platform=None, home=None):
    """The per-user cache folder for one corpus version, from the platform's usual place (standard library only)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    home = os.path.expanduser("~") if home is None else home
    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, "gpconf", "Cache", version)
    if platform == "darwin":
        return os.path.join(home, "Library", "Caches", "gpconf", version)
    xdg = env.get("XDG_CACHE_HOME")
    base = xdg if xdg and os.path.isabs(xdg) else os.path.join(home, ".cache")  # the XDG spec ignores a relative value
    return os.path.join(base, "gpconf", version)


def data_root(corpus, how, explicit=None, env=None):
    """-> (path, why), why in '--data' | 'GPCONF_DATA' | 'clone' | '--root' | 'per-user cache'."""
    env = os.environ if env is None else env
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit)), "--data"
    if env.get(DATA_ENV):
        return os.path.abspath(os.path.expanduser(env[DATA_ENV])), DATA_ENV
    if how in ("clone", "--root"):
        return corpus, how
    return user_cache_dir(corpus_version(corpus), env=env), "per-user cache"


def resolve(root=None, data=None, env=None):
    """-> {'corpus', 'corpus_how', 'data', 'data_why'} for the command line and the runner."""
    corpus, how = corpus_root(root)
    d, why = data_root(corpus, how, data, env)
    return {"corpus": corpus, "corpus_how": how, "data": d, "data_why": why}
