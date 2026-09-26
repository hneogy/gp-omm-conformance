"""D-161: docs/ADAPTERS.md, the adapter guide, stays true to the repository it describes.

Every code block it presents as taken from a shipped file is that file's text at the lines it names, so an adapter
that changes fails here until the guide is updated; every path it names exists; every section it links to, its own or
the README's, exists; and the README's adapter section stays a short summary that links to the guide, so that the
protocol is not written out twice again."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = "docs/ADAPTERS.md"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def slug(heading):
    """GitHub's anchor for a heading: lower case, punctuation other than hyphens dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(text):
    return {slug(h) for h in re.findall(r"(?m)^#{1,6} (.+)$", text)}


class AdapterGuide(unittest.TestCase):
    def setUp(self):
        self.text = read(GUIDE)

    def test_every_excerpt_is_the_shipped_file_at_the_lines_named(self):
        excerpts = re.findall(r"From\s+\[`([^`]+)`\]\([^)]+\), lines (\d+) to (\d+):\n\n```\w+\n(.*?)\n```", self.text, re.S)
        self.assertEqual(len(excerpts), self.text.count("```python\n") + self.text.count("```javascript\n") - 1)  # all but the one-line quotation
        for path, a, b, body in excerpts:
            with self.subTest(path=path, lines=f"{a}-{b}"):
                lines = read(path).split("\n")
                self.assertEqual(body, "\n".join(lines[int(a) - 1:int(b)]))

    def test_the_one_line_quotation_is_in_its_file(self):
        m = re.search(r"from `([^`]+)` \(line (\d+)\):\n\n```python\n(.*?)\n```", self.text)
        self.assertIsNotNone(m)
        self.assertIn(m.group(3).strip(), read(m.group(1)).split("\n")[int(m.group(2)) - 1])  # the entry, as written on that line

    def test_every_path_it_names_exists(self):
        named = set(re.findall(r"`((?:gpconf|tools|tests|fixtures|derived|vectors|docs|harnesses)/[\w./-]*|[\w-]+\.(?:py|mjs))`", self.text))
        linked = {t.split("#")[0] for t in re.findall(r"\]\(([^)\s]+)\)", self.text) if not re.match(r"^[a-z]+:", t) and not t.startswith("#")}
        self.assertGreaterEqual(len(named) + len(linked), 10)
        for p in sorted(named):
            with self.subTest(named=p):
                where = p if "/" in p else os.path.join("gpconf", "adapters", p)  # a bare file name is a shipped adapter
                self.assertTrue(os.path.exists(os.path.join(ROOT, where.rstrip("/"))), p)
        for t in sorted(linked):
            with self.subTest(linked=t):
                self.assertTrue(os.path.exists(os.path.normpath(os.path.join(ROOT, "docs", t))), t)

    def test_every_section_it_links_to_exists(self):
        own = anchors(self.text)
        readme = anchors(read("README.md"))
        for target in re.findall(r"\]\((#[^)]+)\)", self.text):
            with self.subTest(link=target):
                self.assertIn(target[1:], own)
        for target in re.findall(r"\]\(\.\./README\.md#([^)]+)\)", self.text):
            with self.subTest(readme=target):
                self.assertIn(target, readme)

    def test_the_readme_keeps_a_short_section_that_links_here(self):
        readme = read("README.md")
        section = readme.split("\n## Writing an adapter\n", 1)[1].split("\n### ", 1)[0]
        self.assertIn(f"]({GUIDE})", section)
        self.assertNotIn("```", section)  # the protocol is written out in the guide, not again here
        self.assertLess(len(section.split()), 150)


if __name__ == "__main__":
    unittest.main()
