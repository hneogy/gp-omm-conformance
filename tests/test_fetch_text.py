"""D-230: what the corpus says about its own fetch is what the fetch does, and nothing is credited to CelesTrak that
CelesTrak did not ask for.

The README's "Fetching responsibly" used to open "`tools/fetch.py` follows CelesTrak's published usage policy" and
list "2 s between requests" under it. CelesTrak publishes no interval between requests: the pause is the corpus's
own choice. The section now says what CelesTrak asks, what the fetch does about each, and then what is the corpus's
own. The figures it states are held to the fetch list and the manifest here, so they cannot drift from them.

Run: python -m unittest tests.test_fetch_text"""
import contextlib
import io
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import fetch  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def flat(text):
    return " ".join(text.split())


def section(text, title):
    """The text of one '### title' section of a Markdown file, up to the next heading."""
    start = text.index(f"### {title}\n")
    nxt = re.search(r"(?m)^#{1,3} ", text[start + 4:])
    return text[start:start + 4 + nxt.start()] if nxt else text[start:]


def users_run():
    """What a user's fetch requests -> (entries, bytes, expected 404s), from the fetch list and the manifest."""
    entries = [e for e in json.loads(read("tools/fetchlist.json")) if not e.get("recapture_of") and not e.get("launch_window") and not e.get("opt_in")]
    recorded = {}
    for c in json.loads(read("manifest.json"))["cases"]:
        for s in c.get("sources", []):
            recorded.setdefault(s["path"], s)
    size = sum(recorded[f"fixtures/{e['case']}/raw/{e['file']}"]["bytes"] for e in entries)
    return entries, size, [e for e in entries if e.get("expect_status") == 404]


WORDS = {4: "four", 5: "five", 6: "six"}


class FetchingResponsibly(unittest.TestCase):
    def setUp(self):
        self.readme = read("README.md")
        self.section = flat(section(self.readme, "Fetching responsibly"))

    def test_the_pause_is_stated_as_the_corpus_s_own_choice(self):
        self.assertNotIn("follows CelesTrak's published usage policy", self.readme)
        own = "The rest is the corpus's own choice and not something CelesTrak asks for"
        self.assertIn(own, self.section)
        asked, chosen = self.section.split(own)
        self.assertIn("two-second pause", chosen)
        for phrase in ("two-second", "2 s ", "2 seconds", "pause"):
            self.assertNotIn(phrase, asked, phrase)                    # nothing about an interval among what CelesTrak asks

    def test_what_celestrak_asks_is_each_followed_by_what_the_fetch_does(self):
        for ask in ("Download data once per update", "Stop on any response that is not an HTTP 200",
                    "Stay under 50 errors in two hours and 100 MB a day", "Only download the data you need"):
            self.assertIn(f"**{ask}", self.section)
        self.assertIn("https://celestrak.org/usage-policy.php", self.section)
        self.assertIn("https://celestrak.org/NORAD/documentation/gp-data-formats.php", self.section)

    def test_the_figures_are_the_fetch_lists(self):
        entries, size, known = users_run()
        mb = f"{size / 1e6:.1f} MB"
        self.assertIn(f"One run is {len(entries)} requests, {mb} and those {WORDS[len(known)]} 404s.", self.section)
        self.assertIn(f"with {WORDS[len(known)]} exceptions it knows in advance: {WORDS[len(known)]} TLE requests for objects numbered above 99999", self.section)
        for line in self.readme.splitlines():
            if line.startswith(("gpconf fetch ", "python3 tools/fetch.py ")) and "#" in line:
                self.assertIn(f"{len(entries)} requests, {mb}", line, line)
                self.assertNotIn("2 s apart", line)
        self.assertIn(f"That is {len(entries)} requests to CelesTrak, one at a time", flat(read("docs/ADAPTERS.md")))

    def test_the_known_404s_are_tle_requests_for_objects_above_99999(self):
        _, _, known = users_run()
        for e in known:
            self.assertRegex(e["url"], r"FORMAT=TLE$")
            self.assertRegex(e["url"], r"CATNR=(100000|270449)&|GROUP=last-30-days&")   # the group holds six-digit objects only

    def test_the_old_advice_for_leaving_out_the_satcat_is_gone(self):
        """`--skip-case satcat-70000-cutoff` also drops two first-record files filed under that case, which other
        cases read. Since D-231 the fetch leaves the legacy file out by itself, and a flag brings it."""
        self.assertNotIn("--skip-case satcat-70000-cutoff", self.section)
        self.assertIn("The fetch leaves it out unless you pass `--include-satcat`", self.section)
        under_the_case = {e["file"] for e in json.loads(read("tools/fetchlist.json")) if e["case"] == "satcat-70000-cutoff"}
        self.assertLessEqual({"gp-69999-first.tle", "gp-69999-first.csv"}, under_the_case)
        readers = {c["id"] for c in json.loads(read("manifest.json"))["cases"]
                   if c["id"] != "satcat-70000-cutoff" and any(s["path"].endswith("/gp-69999-first.csv") for s in c.get("sources", []))}
        self.assertGreaterEqual(len(readers), 3)

    def test_the_csv_default_is_said_of_the_queries_it_belongs_to(self):
        self.assertNotIn("CelesTrak's default format has been CSV", self.readme)
        self.assertIn("For GP and SupGP queries CelesTrak's default `FORMAT` has been CSV since 2026-05-09.", flat(self.readme))


class TheHelpText(unittest.TestCase):
    def test_the_fetch_s_help_separates_what_is_asked_from_what_is_chosen(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            fetch.run(["--help"], prog="gpconf fetch")
        text = out.getvalue()
        self.assertNotIn("Rules (CelesTrak usage policy", text)
        asked, chosen = text.split("The fetch's own choices, which CelesTrak does not ask for")
        self.assertIn("What CelesTrak asks of software that downloads from it", asked)
        self.assertNotIn("pause", asked)
        self.assertIn("a fixed pause between them", chosen)


if __name__ == "__main__":
    unittest.main()
