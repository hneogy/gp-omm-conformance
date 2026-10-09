"""D-205, v0.5.0 item 2: a vector hook may declare its operation unsupported, by a command answering
{"unsupported": "<reason>"} or a Python hook raising gpconf.runner.Unsupported, and the item then skips with the
reason, as it does for an adapter without the hook. An operation is unsupported for all of its vectors or none: a mix
fails the item. Any non-zero exit of a vectors command stays a rejection, exit 3 included, so no existing adapter's
rejections turn into skips; an unsupported answer without a reason is malformed, like an answer with no key."""
import json
import os
import shlex
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner, CommandParser, Unsupported  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

CASE = "alpha5-encoding-vectors"
ITEMS = ("alpha5-decode", "alpha5-encode", "two-digit-year-pivot", "ccsds-epoch-strings", "catalog-number-is-integer")


def run(parser):
    r = Runner(parser, root=ROOT).run(case_ids=[CASE])[0]
    return r, {i.check: i for i in r.items}


class PythonHook(unittest.TestCase):
    def test_an_operation_declared_unsupported_skips_its_item_with_the_reason(self):
        class P(Reference):
            def alpha5_encode(self, n):
                raise Unsupported("no TLE writer")
        r, c = run(P())
        self.assertEqual(c["alpha5-encode"].status, "skip", c["alpha5-encode"].detail)
        self.assertEqual(c["alpha5-encode"].detail, "parser reports alpha5_encode unsupported: no TLE writer")
        for other in ITEMS:
            if other != "alpha5-encode":
                self.assertEqual(c[other].status, "pass", other)
        self.assertEqual(r.status, "pass")  # a skipped item does not fail the case

    def test_unsupported_for_some_vectors_fails_the_item_and_says_so(self):
        class P(Reference):
            def alpha5_encode(self, n):
                if n >= 200000:
                    raise Unsupported("letters above J not implemented")
                return super().alpha5_encode(n)
        r, c = run(P())
        self.assertEqual(c["alpha5-encode"].status, "fail")
        d = c["alpha5-encode"].detail
        self.assertIn("alpha5_encode answered unsupported for", d)
        self.assertIn("letters above J not implemented", d)
        self.assertIn("all of its vectors or none", d)
        self.assertEqual(r.status, "fail")

    def test_an_unsupported_raise_without_a_reason_still_skips_and_says_so(self):
        class P(Reference):
            def parse_catalog_id(self, text):
                raise Unsupported("")
        _, c = run(P())
        self.assertEqual(c["catalog-number-is-integer"].status, "skip")
        self.assertIn("no reason given", c["catalog-number-is-integer"].detail)

    def test_any_other_raise_still_fails_that_vector(self):
        class P(Reference):
            def two_digit_year(self, yy):
                if yy == "57":
                    raise ValueError("boom")
                return super().two_digit_year(yy)
        _, c = run(P())
        self.assertEqual(c["two-digit-year-pivot"].status, "fail")
        self.assertIn("raised ValueError", c["two-digit-year-pivot"].detail)

    def test_an_adapter_without_the_hook_skips_as_before(self):
        class P(Reference):
            alpha5_encode = None
        _, c = run(P())
        self.assertEqual((c["alpha5-encode"].status, c["alpha5-encode"].detail), ("skip", "parser exposes no alpha5_encode hook"))


class CommandAnswer(unittest.TestCase):
    """The command protocol: the answer's shape and the exit code decide."""

    def answer(self, stdout, code=0):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "vec.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.stdout.write(%r)\nsys.exit(%d)\n" % (stdout, code))
        return f"{shlex.quote(sys.executable)} {shlex.quote(p)}"

    def test_the_unsupported_answer_raises_unsupported_with_the_reason(self):
        cp = CommandParser(None, vectors_cmd=self.answer('{"unsupported": "no writer"}'))
        with self.assertRaises(Unsupported) as cm:
            cp.alpha5_encode(100000)
        self.assertEqual(str(cm.exception), "no writer")

    def test_a_non_zero_exit_is_a_rejection_whatever_the_answer_says_exit_3_included(self):
        for code in (1, 2, 3):
            with self.subTest(exit=code):
                cp = CommandParser(None, vectors_cmd=self.answer('{"unsupported": "x"}', code))
                with self.assertRaises(ValueError) as cm:
                    cp.alpha5_encode(100000)
                self.assertNotIsInstance(cm.exception, Unsupported)
                self.assertIn(f"exit {code}", str(cm.exception))

    def test_an_unsupported_answer_without_a_reason_is_malformed(self):
        for stdout in ('{"unsupported": ""}', '{"unsupported": "   "}', '{"unsupported": 5}'):
            with self.subTest(answer=stdout):
                cp = CommandParser(None, vectors_cmd=self.answer(stdout))
                with self.assertRaises(ValueError) as cm:
                    cp.alpha5_encode(100000)
                self.assertNotIsInstance(cm.exception, Unsupported)
                self.assertIn("no reason", str(cm.exception))

    def test_error_result_and_empty_answers_keep_their_meaning(self):
        cp = CommandParser(None, vectors_cmd=self.answer('{"error": "cannot"}'))
        with self.assertRaises(ValueError) as cm:
            cp.alpha5_encode(100000)
        self.assertEqual(str(cm.exception), "cannot")
        self.assertEqual(CommandParser(None, vectors_cmd=self.answer('{"result": "A0000"}')).alpha5_encode(100000), "A0000")
        with self.assertRaises(ValueError) as cm:
            CommandParser(None, vectors_cmd=self.answer("{}")).alpha5_encode(100000)
        self.assertIn("neither", str(cm.exception))

    def test_end_to_end_a_command_that_lacks_two_operations_skips_their_items(self):
        code = ("import json, sys\n"
                "sys.path.insert(0, %r)\n"
                "from tests.adapters.reference import Parser\n"
                "req = json.load(sys.stdin); p = Parser()\n"
                "if req['op'] == 'alpha5_encode':\n"
                "    print(json.dumps({'unsupported': 'this library has no TLE writer'})); sys.exit(0)\n"
                "if req['op'] == 'parse_epoch':\n"
                "    print(json.dumps({'unsupported': 'this library reads TLE lines only'})); sys.exit(0)\n"
                "try:\n"
                "    r = getattr(p, req['op'])(req['input'])\n"
                "    print(json.dumps({'result': r}))\n"
                "except Exception as e:\n"
                "    print(json.dumps({'error': str(e)})); sys.exit(1)\n") % ROOT
        d = tempfile.mkdtemp()
        p = os.path.join(d, "vec.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write(code)
        cp = CommandParser(None, vectors_cmd=f"{shlex.quote(sys.executable)} {shlex.quote(p)}")
        r, c = run(cp)
        self.assertEqual(c["alpha5-encode"].status, "skip")
        self.assertEqual(c["alpha5-encode"].detail, "parser reports alpha5_encode unsupported: this library has no TLE writer")
        self.assertEqual(c["ccsds-epoch-strings"].status, "skip")
        self.assertIn("reads TLE lines only", c["ccsds-epoch-strings"].detail)
        for other in ("alpha5-decode", "two-digit-year-pivot", "catalog-number-is-integer"):
            self.assertEqual(c[other].status, "pass", c[other].detail)
        self.assertEqual(r.status, "pass")
        self.assertNotIn("runner", c)


if __name__ == "__main__":
    unittest.main()
