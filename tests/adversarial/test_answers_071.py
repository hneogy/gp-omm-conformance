# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""An answer that is not a list of records fails in its own words (D-330), with its wrong-on-purpose adapters and twins.

Before: a parser that returned its records as strings ended the corrupt-input case as "internal error in runner:
AttributeError" and failed every other file as "parser raised AttributeError", though the parser raised nothing; a
dict read the same way; and the corrupt-input case's comparison file, when the parser gave something other than a
list for it, was set aside with no failure of its own. Now each fails as `parse`, worded as the parser's answer.
Any iterable of records will do: a tuple or a generator of dicts is read like a list. The separate reviewer's two
readings of the mend (D-334, D-337) are the last two classes.

Run: python -m unittest tests.adversarial.test_answers_071"""
import os
import shlex
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import NotRecords, as_records  # noqa: E402
from tests.adversarial.test_hardening import failing, run  # noqa: E402

THREE = ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"]


def shaped(how):
    class Adapter(Reference):
        def parse(self, raw, fmt):
            return how(super().parse(raw, fmt))
    return Adapter()


def fails(results):
    return [i for c in results.values() for i in c.items if i.status == "fail"]


class AnAnswerThatIsNotAListOfRecordsFailsInItsOwnWords(unittest.TestCase):

    def check(self, adapter, words):
        r = run(adapter)
        self.assertEqual(failing(r), THREE)
        details = [i.detail for i in fails(r)]
        for d in details:
            self.assertNotIn("internal error in runner", d)
            self.assertNotIn("AttributeError", d)
            self.assertNotIn("parser raised", d)
        self.assertTrue(any(words in d for d in details), details[:2])
        return r

    def test_records_returned_as_strings(self):
        self.check(shaped(lambda out: [str(x) for x in out]), "the answer holds str at entry 1, where every entry must be a record (a mapping)")

    def test_a_dict_in_place_of_the_list(self):
        self.check(shaped(lambda out: {"records": out}), "the answer is dict, not a list of records")

    def test_one_string_among_the_records(self):
        self.check(shaped(lambda out: list(out) + ["x"]), "where every entry must be a record")

    def test_the_corrupt_input_cases_comparison_file_fails_as_parse_too(self):
        r = run(shaped(lambda out: [str(x) for x in out]), cases=["corrupt-input"])
        parse = [i for i in r["corrupt-input"].items if i.check == "parse" and i.status == "fail"]
        self.assertTrue(any(os.path.basename(i.file or "").startswith("unedited") for i in parse), [i.file for i in parse])

    def test_twins_the_same_records_as_a_list_a_tuple_or_a_generator_pass(self):
        for name, how in (("list", list), ("tuple", tuple), ("generator", lambda out: (x for x in out))):
            with self.subTest(container=name):
                self.assertEqual(failing(run(shaped(how))), [])

    def test_the_helper_itself(self):
        self.assertEqual(as_records(({"a": 1},)), [{"a": 1}])
        for bad, words in (({"a": 1}, "is dict"), ("text", "is str"), (b"x", "is bytes"), (None, "is NoneType"), (5, "is int"),
                           ([{"a": 1}, 2], "holds int at entry 2")):
            with self.subTest(bad=bad), self.assertRaises(NotRecords) as cm:
                as_records(bad)
            self.assertIn(words, str(cm.exception))


UNEDITED = {open(os.path.join(ROOT, "derived", "corrupt-input", n), "rb").read()
            for n in ("unedited-sets.tle", "unedited-rows.csv", "unedited-array.json")}


class Dropper(Reference):
    """A wrong parser: it drops every corrupt record silently (no refusal, no record)."""

    def parse(self, raw, fmt):
        return [r for r in super().parse(raw, fmt) if "_refused" not in r]


class TheReviewersRoutes(unittest.TestCase):
    """The separate reviewer's reading of D-330 (2026-10-15) found these; each closed in D-334, with its twin."""

    def test_a_dropper_that_answers_a_dict_for_the_comparison_files_still_fails(self):
        class HidesBehindTheComparisonFile(Dropper):
            def parse(self, raw, fmt):
                if raw in UNEDITED:
                    return {"records": super().parse(raw, fmt)}
                return super().parse(raw, fmt)
        r = run(HidesBehindTheComparisonFile(), cases=["corrupt-input"])
        self.assertEqual(failing(r), ["corrupt-input"])
        twin = run(Dropper(), cases=["corrupt-input"])      # the same bug, the comparison files read normally
        self.assertEqual(failing(twin), ["corrupt-input"])

    def test_a_generator_that_exits_halfway_is_caught_like_an_eager_exit(self):
        import sys as _sys

        class LazyExit(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)

                def g():
                    yield from out[:1]
                    _sys.exit(0)
                return g()

        class EagerExit(Reference):
            def parse(self, raw, fmt):
                _sys.exit(0)
        for adapter in (LazyExit(), EagerExit()):
            with self.subTest(adapter=type(adapter).__name__):
                r = run(adapter, cases=["corrupt-input"])
                self.assertEqual(failing(r), ["corrupt-input"])
                self.assertTrue(any("must not end the run" in i.detail or "parser-exit" in i.check for i in fails(r)))

    def test_a_generator_that_refuses_or_declares_a_format_unsupported_is_read_like_its_eager_twin(self):
        from gpconf.runner import Unsupported

        def lazy(base_raise):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)

                    def g():
                        if fmt == "csv":
                            base_raise(fmt)
                        yield from out
                    return g()
            return Adapter()

        def eager(base_raise):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    if fmt == "csv":
                        base_raise(fmt)
                    return super().parse(raw, fmt)
            return Adapter()

        def refuse(fmt):
            raise ValueError("cannot read this file")

        def unsupported(fmt):
            raise Unsupported(fmt)
        for name, how in (("refuses", refuse), ("unsupported", unsupported)):
            with self.subTest(how=name):
                a, b = run(lazy(how)), run(eager(how))
                self.assertEqual(failing(a), failing(b))
                self.assertEqual({c: r.status for c, r in a.items()}, {c: r.status for c, r in b.items()})
                for i in fails(a):
                    self.assertNotIn("internal error in runner", i.detail)

    def test_a_mapping_whose_get_and_items_disagree_cannot_hide_an_unparsed_epoch(self):
        """D-306: an epoch handed back as the input's own text fails. A mapping whose get('epoch') says None while its
        items() carry that text went round the check; each record is now copied into a plain dict first."""
        import re as _re
        DOY = _re.compile(r"^\d{4}-\d{3}T")

        class Lying(dict):
            def get(self, key, default=None):
                return None if key == "epoch" else super().get(key, default)

        def passes_text_back(cls):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    if fmt != "kvn":
                        return out
                    text = raw.decode("utf-8", "replace")
                    found = _re.findall(r"(?m)^EPOCH\s*=\s*(\S+)", text)
                    res = []
                    for r, e in zip([x for x in out if "_refused" not in x], found):
                        r = cls(r)
                        if DOY.match(e):
                            dict.__setitem__(r, "epoch", e)
                        res.append(r)
                    return res + [x for x in out if "_refused" in x]
            return Adapter()
        lying, plain = run(passes_text_back(Lying), cases=["kvn-syntax-variants"]), run(passes_text_back(dict), cases=["kvn-syntax-variants"])
        self.assertEqual(failing(plain), ["kvn-syntax-variants"])
        self.assertEqual(failing(lying), ["kvn-syntax-variants"])

    def test_a_correct_parser_returning_read_only_mappings_passes(self):
        from types import MappingProxyType

        class ReadOnly(Reference):
            def parse(self, raw, fmt):
                return [MappingProxyType(r) for r in super().parse(raw, fmt)]
        self.assertEqual(failing(run(ReadOnly())), [])

    def test_a_command_adapter_that_prints_an_object_fails_as_parse_in_the_same_words(self):
        import tempfile as _tf
        from gpconf.runner import CommandParser
        with _tf.TemporaryDirectory() as d:
            script = os.path.join(d, "obj.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write("import sys, json\nsys.stdin.buffer.read()\nprint(json.dumps({'records': []}))\n")
            # quoted for the shell that runs it, cmd.exe on Windows (single quotes are not quotes there), as the suite's
            # other command tests do (lane C, 2026-10-24)
            Q = (lambda s: subprocess.list2cmdline([s])) if os.name == "nt" else shlex.quote
            r = run(CommandParser(cmd=f"{Q(sys.executable)} {Q(script)} {{fmt}}"), cases=["corrupt-input"])
            details = [i.detail for i in fails(r)]
            self.assertTrue(any("the answer is dict, not a list of records" in d for d in details), details[:2])
            self.assertFalse(any("stdout must be a JSON array" in d for d in details))



def every_record(how, only=None):
    """The reference's answer with each record (refusals included unless only says otherwise) passed through how."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            return [how(r) if (only is None or only(r)) else r for r in super().parse(raw, fmt)]
    return Adapter()


class TheReviewersSecondReading(unittest.TestCase):
    """The separate reviewer's second reading (2026-10-15) found the parser's code still run after the guarded call had
    returned: a list subclass's own iteration, the record copy's keys() and [], a str subclass's strip() and __eq__, a
    key that is not text, and a value's own methods. Each closed in D-337, with its twin; the dict subclass's test
    follows the owner's ruling on the third reading."""

    def statuses(self, r):
        return {c: x.status for c, x in r.items()}

    def items(self, r):
        return [(c, i.check, i.status, i.file, i.detail) for c in sorted(r) for i in r[c].items]

    def test_a_list_or_tuple_subclass_is_iterated_inside_the_guard(self):
        from gpconf.runner import Unsupported

        def subclass(base, act):
            class Sub(base):
                def __iter__(self):
                    items = list(base.__iter__(self))
                    yield from items[:1]
                    act()
                    yield from items[1:]

            class Adapter(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    return Sub(out) if fmt == "csv" else out
            return Adapter()

        def eager(act):
            class Adapter(Reference):     # the exact twin: the same act, after the same reading (the third reading's 6)
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    if fmt == "csv":
                        act()
                    return out
            return Adapter()

        def refuse():
            raise ValueError("cannot read this file")

        def unsupported():
            raise Unsupported("csv")

        def leave():
            sys.exit(0)
        for base in (list, tuple):
            for name, act in (("refuses", refuse), ("unsupported", unsupported), ("exits", leave)):
                with self.subTest(base=base.__name__, how=name):
                    a, b = run(subclass(base, act)), run(eager(act))   # the run goes on, for the exit too
                    self.assertEqual(self.items(a), self.items(b))      # item for item, not only the statuses
                    self.assertFalse([i for i in fails(a) if "internal error in runner" in i.detail])
                    if name == "exits":
                        self.assertTrue(any(i.check == "parser-exit" for i in a["corrupt-input"].items))

    def test_a_dict_subclass_is_read_two_ways_and_must_agree_with_itself(self):
        """D-337, on the owner's ruling (the third reading's 1 and 2): a dict subclass is read by what it holds and
        through its own keys() and []; a record that holds one thing and shows another has no one answer, and fails
        in words, whichever way it differs. D-337's first form read what it holds only, and a record type that held
        the right value and handed out a wrong one passed."""
        class Hides(dict):
            """Lists its public keys only, so a refusal's `_refused` is held and not shown (the reviewer's probe10)."""
            def __iter__(self):
                return (k for k in dict.__iter__(self) if not k.startswith("_"))

            def keys(self):
                return [k for k in dict.keys(self) if not k.startswith("_")]

        class Doubles(dict):
            """Holds the right mean motion and hands out its double, through every method (the third reading's 1)."""
            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                return str(float(v) * 2) if k == "mean_motion" and v is not None else v

            def get(self, k, default=None):
                return self[k] if k in self else default

            def items(self):
                return [(k, self[k]) for k in dict.keys(self)]

            def __iter__(self):
                return iter(dict.keys(self))

            def keys(self):
                return list(dict.keys(self))

        class Internal(dict):
            """Holds its fields under keys of its own and shows the protocol's names (the third reading's 2)."""
            def __init__(self, r):
                super().__init__({"f:" + k: v for k, v in r.items()})

            def keys(self):
                return [k[2:] for k in dict.keys(self)]

            def __iter__(self):
                return iter(self.keys())

            def __getitem__(self, k):
                return dict.__getitem__(self, "f:" + k)
        words = "show other fields or values than it holds"
        for cls, expect in ((Hides, ["corrupt-input"]), (Doubles, THREE), (Internal, THREE)):
            with self.subTest(record=cls.__name__):
                r = run(every_record(cls))
                self.assertEqual(failing(r), expect)
                self.assertTrue(any(words in i.detail for i in fails(r)), [i.detail[:120] for i in fails(r)][:3])

        class Exits(dict):
            def keys(self):
                sys.exit(0)
        r = run(every_record(Exits))                                            # its keys() runs inside the guard now
        self.assertEqual(len(r), 5)
        self.assertEqual(failing(r), THREE)
        self.assertTrue(all(any(i.check == "parser-exit" for i in r[c].items) for c in THREE))

        class Agrees(dict):
            """A dict subclass that holds and shows the same fields, an attribute-style record, say."""
            def __getattr__(self, k):
                return self[k]
        self.assertEqual(failing(run(every_record(Agrees))), [])                # twins: it passes,
        self.assertEqual(failing(run(every_record(dict))), [])                  # and so do plain dicts

    def test_a_mapping_that_is_not_a_dict_is_read_inside_the_guard(self):
        from collections.abc import Mapping

        def mapping(exit_on_read):
            class M(Mapping):
                def __init__(self, d):
                    self._d = dict(d)

                def __getitem__(self, k):
                    return self._d[k]

                def __iter__(self):
                    if exit_on_read:
                        sys.exit(0)
                    return iter(self._d)

                def __len__(self):
                    return len(self._d)

                def keys(self):
                    if exit_on_read:
                        sys.exit(0)
                    return self._d.keys()
            return M
        r = run(every_record(mapping(True)))
        self.assertEqual(len(r), 5)                                              # the run went on
        self.assertEqual(failing(r), THREE)
        for c in THREE:
            self.assertTrue(any(i.check == "parser-exit" and "SystemExit(0) in parse" in i.detail for i in r[c].items), c)
        self.assertEqual(failing(run(every_record(mapping(False)))), [])         # twin: the same mapping, read honestly

    def test_a_str_subclass_cannot_hide_an_epoch_passed_back_unparsed(self):
        """D-306 read value.strip() and the record's get("epoch"); a str subclass answered both its own way."""
        import re as _re
        DOY = _re.compile(r"^\d{4}-\d{3}T")

        class LyingStrip(str):
            def strip(self, *a):
                return ""

        def hands_back(make_key=lambda: "epoch", make_value=lambda e: e):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    if fmt != "kvn":
                        return out
                    found = _re.findall(r"(?m)^EPOCH\s*=\s*(\S+)", raw.decode("utf-8", "replace"))
                    res = []
                    for r, e in zip([x for x in out if "_refused" not in x], found):
                        d = {k: v for k, v in r.items() if k != "epoch"}
                        d[make_key()] = make_value(e) if DOY.match(e) else r["epoch"]
                        res.append(d)
                    return res + [x for x in out if "_refused" in x]
            return Adapter()

        def flaky_key(n_false):
            class K(str):
                n = 0

                def __hash__(self):
                    return str.__hash__(self)

                def __eq__(self, other):
                    same = str.__eq__(self, other)
                    if same is True:
                        type(self).n += 1
                        if type(self).n == n_false:
                            return False
                    return same
            return lambda: K("epoch")
        twin = run(hands_back(), cases=["kvn-syntax-variants"])
        self.assertEqual(failing(twin), ["kvn-syntax-variants"])
        self.assertTrue(any("passed back unparsed" in i.detail for i in fails(twin)))
        for name, adapter in [("strip() says nothing", hands_back(make_value=LyingStrip))] + \
                [(f"__eq__ false on comparison {n}", hands_back(make_key=flaky_key(n))) for n in range(1, 9)]:
            with self.subTest(how=name):
                r = run(adapter, cases=["kvn-syntax-variants"])
                self.assertEqual(failing(r), ["kvn-syntax-variants"])
                self.assertTrue(any("passed back unparsed" in i.detail for i in fails(r)), [i.detail[:100] for i in fails(r)])

    def test_a_key_that_is_not_text_is_ignored_like_any_unknown_key(self):
        def with_key(k):
            def how(r):
                r = dict(r)
                r[k] = "a note of the parser's own"
                return r
            return every_record(how, only=lambda r: "_refused" not in r)
        for k in (0, ("a", "tuple"), b"epoch"):
            with self.subTest(key=k):
                r = run(with_key(k))
                self.assertEqual(failing(r), [])
        self.assertEqual(failing(run(with_key("note"))), [])                    # twin: a text key it does not know

    def test_the_same_field_twice_in_one_record_is_named(self):
        class Twin(str):
            def __hash__(self):          # a second "epoch" in the same dict: a different hash, the same text
                return hash("not the epoch")

        def how(r):
            r = dict(r)
            r[Twin("epoch")] = "2000-01-01T00:00:00"
            return r
        r = run(every_record(how, only=lambda r: "_refused" not in r))
        self.assertEqual(failing(r), THREE)
        self.assertTrue(any("holds the field 'epoch' twice" in i.detail for i in fails(r)), [i.detail[:100] for i in fails(r)][:3])

    def test_a_value_whose_own_method_exits_fails_the_case_and_the_run_goes_on(self):
        def value(exits):
            class V:
                def __init__(self, text):
                    self.text = text

                def __str__(self):
                    if exits:
                        sys.exit(0)
                    return self.text

                __repr__ = __str__
            return V

        def with_mean_motion(cls):
            def how(r):
                r = dict(r)
                if r.get("mean_motion") is not None:
                    r["mean_motion"] = cls(str(r["mean_motion"]))
                return r
            return every_record(how, only=lambda r: "_refused" not in r)
        r = run(with_mean_motion(value(True)))
        self.assertEqual(len(r), 5)                                              # the run went on
        self.assertEqual(failing(r), THREE)
        for c in THREE:
            # its __str__ runs inside the guard now, as the answer is read (D-337), so the guard counts the exit
            self.assertTrue(any(i.check == "parser-exit" and "SystemExit(0) in parse" in i.detail for i in r[c].items), c)
        self.assertEqual(failing(run(with_mean_motion(value(False)))), [])      # twin: the same object, read honestly



class Lies(str):
    """Text whose comparisons always say "equal"."""
    __hash__ = str.__hash__

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False


def with_field(field, make, only_set=True):
    """The reference's records, `field` replaced by make(its value) wherever it holds one."""
    def how(r):
        r = dict(r)
        if r.get(field) is not None or not only_set:
            r[field] = make(r.get(field))
        return r
    return every_record(how, only=lambda r: "_refused" not in r)


class TheReviewersThirdReading(unittest.TestCase):
    """The separate reviewer's third reading (2026-10-15), under the owner's model: gpconf grades wrong answers, and a
    wrong value that survives the reading into plain values is an escape. Each of these passed before D-337's boundary,
    on the code before D-337 and on its first form; each closes because the guard reads every answer into plain
    built-in values before any check sees it. Each has its twin."""

    def test_text_from_objects_whose_comparisons_lie(self):
        """Finding 3a: an object whose __str__ hands back a str subclass whose __eq__ always says equal."""
        class Wrapper:
            def __init__(self, text):
                self.text = text

            def __str__(self):
                return Lies(self.text)
        for field in ("object_name", "object_id", "classification_type"):
            with self.subTest(field=field):
                self.assertEqual(failing(run(with_field(field, lambda v: Wrapper("GARBAGE")))), THREE)
                self.assertEqual(failing(run(with_field(field, lambda v: "GARBAGE"))), THREE)      # twin: plain garbage
                self.assertEqual(failing(run(with_field(field, lambda v: Wrapper(v)))), [])         # honest wrapper

    def test_a_datetime_subclass_whose_strftime_lies(self):
        """Finding 3b: a parser that reads no epoch, answering a datetime subclass whose strftime() lies."""
        import datetime as _dt

        class When(_dt.datetime):
            def strftime(self, fmt):
                return Lies("no epoch was read")

            def isoformat(self, *a, **k):
                return Lies("no epoch was read")
        self.assertEqual(failing(run(with_field("epoch", lambda v: When(2000, 1, 1)))), THREE)
        self.assertEqual(failing(run(with_field("epoch", lambda v: _dt.datetime(2000, 1, 1)))), THREE)   # twin
        from gpconf import tle as _tle
        right = lambda v: When.fromisoformat(_tle.iso_epoch(v))   # noqa: E731
        self.assertEqual(failing(run(with_field("epoch", right))), [])                     # the right instant passes

    def test_an_epoch_passed_back_unparsed_inside_a_wrapper(self):
        """Finding 3c: D-306 read isinstance(value, str) only, so the file's own text in a UserString passed."""
        import re as _re
        from collections import UserString
        DOY = _re.compile(r"^\d{4}-\d{3}T")

        class Text:
            def __init__(self, s):
                self.s = s

            def __str__(self):
                return self.s

        def hands_back(wrap):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    if fmt != "kvn":
                        return out
                    found = _re.findall(r"(?m)^EPOCH\s*=\s*(\S+)", raw.decode("utf-8", "replace"))
                    res = []
                    for r, e in zip([x for x in out if "_refused" not in x], found):
                        r = dict(r)
                        if DOY.match(e):
                            r["epoch"] = wrap(e)
                        res.append(r)
                    return res + [x for x in out if "_refused" in x]
            return Adapter()
        for name, wrap in (("plain str, the twin", str), ("UserString", UserString), ("an object with __str__", Text)):
            with self.subTest(how=name):
                r = run(hands_back(wrap), cases=["kvn-syntax-variants"])
                self.assertEqual(failing(r), ["kvn-syntax-variants"])
                self.assertTrue(any("passed back unparsed" in i.detail for i in fails(r)))

    def test_hook_answers_whose_comparisons_lie(self):
        """Finding 4: hooks that check the form of their input, compute nothing, and answer int and str subclasses
        whose __eq__ and __ne__ say equal."""
        import re as _re
        FORM = _re.compile(r"[0-9]{5}|[A-HJ-NP-Z][0-9]{4}")

        class LiarInt(int):
            __hash__ = int.__hash__

            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False

        def hooks(int_, str_):
            class Adapter(Reference):
                def alpha5_decode(self, field):
                    if not FORM.fullmatch(field):
                        raise ValueError("not a catalog field")
                    return int_(0)

                def alpha5_encode(self, n):
                    if not 0 <= n <= 339999:
                        raise ValueError("cannot encode")
                    return str_("?????")

                def two_digit_year(self, yy):
                    return int_(0)
            return Adapter()
        checks = ("alpha5-decode", "alpha5-encode", "two-digit-year-pivot")
        for name, adapter in (("liars", hooks(LiarInt, Lies)), ("the twin, plain wrong answers", hooks(int, str))):
            with self.subTest(how=name):
                r = run(adapter, cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
                self.assertEqual({i.check: i.status for i in r.items if i.check in checks}, {c: "fail" for c in checks})

        class Honest(int):
            pass

        class RightHooks(Reference):                                             # honest subclasses of the right answers
            def alpha5_decode(self, field):
                return Honest(super().alpha5_decode(field))
        r = run(RightHooks(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        self.assertEqual(next(i.status for i in r.items if i.check == "alpha5-decode"), "pass")

    def test_a_parser_raising_the_runners_own_corpus_incomplete_does_not_end_the_run(self):
        """Finding 5: the runner's CorpusIncomplete ends a run (a broken copy of the corpus). Raised by the parser from a
        value's __str__ or a property, it ended the run with exit 2 and the parser's words; raised from inside parse() it
        was already caught as the parser's (the twin of the two). Now each is the parser's exception, and the file
        fails as parse."""
        from gpconf.runner import CorpusIncomplete

        class Raises(Reference):
            def parse(self, raw, fmt):
                if fmt == "tle":      # alpha5-tle-derived's files are all valid, so a raise there fails them as parse
                    raise CorpusIncomplete("re-clone the corpus")
                return super().parse(raw, fmt)

        class Value:
            def __str__(self):
                raise CorpusIncomplete("re-clone the corpus")
        class Property(Reference):
            @property
            def alpha5_decode(self):
                raise CorpusIncomplete("re-clone the corpus")
        for name, adapter in (("from parse()", Raises()), ("from a value", with_field("mean_motion", lambda v: Value()))):
            with self.subTest(source=name):
                r = run(adapter)
                self.assertEqual(len(r), 5)
                self.assertTrue(any("parser raised CorpusIncomplete" in i.detail for i in fails(r)), [i.detail[:100] for i in fails(r)][:3])
        r = run(Property())                                                        # from a property: the run goes on
        self.assertEqual(len(r), 5)
        self.assertEqual(r["alpha5-encoding-vectors"].status, "fail")

        class ValueRaisesValueError:                                              # twin: an ordinary exception, the same way
            def __str__(self):
                raise ValueError("no")
        r = run(with_field("mean_motion", lambda v: ValueRaisesValueError()))
        self.assertEqual(failing(r), THREE)
        self.assertTrue(any("parser raised ValueError" in i.detail for i in fails(r)))

    def test_a_float_is_read_by_its_value_past_its_own_methods(self):
        """2g, W0's leftovers: a float subclass is its value, whatever its __repr__ and __float__ say; another binary
        floating type (numpy's float32, say) is compared as the value it holds, not as the short text it prints."""
        import numbers

        class Says(float):
            """Holds 1.0; its own __repr__, __str__ and __float__ give the right value."""
            def __new__(cls, right):
                obj = super().__new__(cls, 1.0)
                obj.right = right
                return obj

            def __repr__(self):
                return repr(self.right)

            __str__ = __repr__

            def __float__(self):
                return self.right

        self.assertEqual(failing(run(with_field("mean_motion", lambda v: Says(float(v))))), THREE)
        self.assertEqual(failing(run(with_field("mean_motion", lambda v: 1.0))), THREE)    # twin: the plain wrong value
        self.assertEqual(failing(run(with_field("mean_motion", lambda v: float(v)))), [])  # the right float passes

        import struct

        class Float32:
            """A binary32 value, as numpy's float32 holds it, printing the shortest text that reads back to it."""
            def __init__(self, x):
                self.v = struct.unpack("f", struct.pack("f", x))[0]
                self.text = x

            def __float__(self):
                return self.v

            def __str__(self):
                return str(self.text)
        numbers.Real.register(Float32)
        self.assertEqual(failing(run(with_field("mean_motion", lambda v: Float32(float(v))))), THREE)  # 1e-8 off, not 1e-12

        class Float64Like(Float32):
            def __init__(self, x):
                self.v, self.text = x, x
        numbers.Real.register(Float64Like)
        self.assertEqual(failing(run(with_field("mean_motion", lambda v: Float64Like(float(v))))), [])   # twin: holds it



class TheBoundarysFirstReading(unittest.TestCase):
    """The separate reviewer's reading of D-337's boundary (2026-10-15), under the owner's model. Each route with its
    twin."""

    def test_a_refusal_reason_that_is_not_text_is_no_reason(self):
        """Finding 1: the reading turned bytes, a set or an object into their str(), a non-empty reason, and the corrupt
        record was credited as refused with a reason (D-144 says a reason is a non-empty string)."""
        class Blank:
            pass

        def reason(make):
            def how(r):
                r = dict(r)
                r["_refused"] = make()
                return r
            return every_record(how, only=lambda r: "_refused" in r)
        for name, make in (("bytes", lambda: b""), ("a bytearray", bytearray), ("a set", set), ("an object", Blank),
                           ("a range", lambda: range(0)), ("the twin, an empty string", lambda: ""), ("the twin, None", lambda: None)):
            with self.subTest(reason=name):
                r = run(reason(make), cases=["corrupt-input"])
                self.assertEqual(failing(r), ["corrupt-input"])
                self.assertTrue(any("without a reason" in i.detail for i in fails(r)), [i.detail[:100] for i in fails(r)][:2])
        self.assertEqual(failing(run(reason(lambda: "the line is corrupt"), cases=["corrupt-input"])), [])   # a reason in words

    def test_a_writer_may_return_its_lines_in_any_shape_it_did_before(self):
        """Finding 2: bytes, a generator, an iterator or a map of lines read as their str(), so a correct writer failed."""
        def writer(shape):
            class Adapter(Reference):
                def write_tle(self, record):
                    out = super().write_tle(record)
                    return shape([l for l in out if l.strip()])
            return Adapter()
        shapes = (("a list", list), ("a tuple", tuple), ("one text block", "\n".join),
                  ("a bytes block", lambda ls: "\n".join(ls).encode()), ("a generator", lambda ls: (l for l in ls)),
                  ("an iterator", iter), ("a map", lambda ls: map(str, ls)))
        for name, shape in shapes:
            with self.subTest(shape=name):
                self.assertEqual(failing(run(writer(shape), cases=["tle-writer-alpha5"])), [])

        class Wrong(Reference):                                                   # twin: wrong lines in a generator fail
            def write_tle(self, record):
                out = super().write_tle(record)
                return (l.replace(" 0 ", " 9 ", 1) for l in out if l.strip())
        self.assertEqual(failing(run(Wrong(), cases=["tle-writer-alpha5"])), ["tle-writer-alpha5"])

    def test_writer_output_that_is_no_lines_is_counted_and_nothing_unchecked_passes(self):
        """Finding 7: "-753 of 0 records correct", and three items passing on nothing written."""
        class NoLines(Reference):
            def write_tle(self, record):
                return "only one line"
        r = run(NoLines(), cases=["tle-writer-alpha5"])["tle-writer-alpha5"]
        by = {i.check: i for i in r.items}
        self.assertEqual(by["tle-checksums-valid"].status, "fail")
        self.assertNotIn("-", by["tle-checksums-valid"].detail.split(" of ")[0])
        self.assertTrue(by["tle-checksums-valid"].detail.startswith("0 of "), by["tle-checksums-valid"].detail[:60])
        for c in ("tle-writer-catalog-field", "tle-writer-column-layout", "tle-writer-round-trip"):
            self.assertEqual(by[c].status, "not-exercised", (c, by[c].detail[:80]))

    def test_a_registered_number_type_without_index_or_float_is_read_not_raised_on(self):
        """Finding 3: operator.index and float() raised TypeError inside the guard, which read as the parser raising."""
        import numbers

        class CatNo:
            def __init__(self, n):
                self.n = n

            def __int__(self):
                return self.n
        numbers.Integral.register(CatNo)

        class Text:
            def __init__(self, s):
                self.s = s

            def __str__(self):
                return self.s
        numbers.Real.register(Text)
        # an integer type (D-295) holding the right value passes, as it did before D-337; the parser raised nothing
        self.assertEqual(failing(run(with_field("element_set_no", lambda v: CatNo(v)))), [])
        r = run(with_field("element_set_no", lambda v: CatNo(v + 1)))                       # twin: a wrong value fails
        self.assertEqual(failing(r), THREE)
        self.assertFalse([i for i in fails(r) if "parser raised" in i.detail], [i.detail[:100] for i in fails(r)][:2])
        self.assertEqual(failing(run(with_field("mean_motion", lambda v: Text(str(v))))), [])        # read as its text
        self.assertEqual(failing(run(with_field("mean_motion", lambda v: Text("1.0")))), THREE)      # twin: wrong text

    def test_a_property_that_declares_a_format_unsupported_skips_as_from_inside_the_call(self):
        """Finding 4: a property raising Unsupported read as the parser raising it, a fail where the call's skip was."""
        from gpconf.runner import Unsupported

        class Property(Reference):
            @property
            def write_tle(self):
                raise Unsupported("this build has no writer")

        class Inside(Reference):                                                   # twin: raised from inside the call
            def write_tle(self, record):
                raise Unsupported("this build has no writer")
        a, b = run(Property(), cases=["tle-writer-alpha5"]), run(Inside(), cases=["tle-writer-alpha5"])
        self.assertEqual([(i.check, i.status) for i in a["tle-writer-alpha5"].items], [(i.check, i.status) for i in b["tle-writer-alpha5"].items])
        self.assertEqual(a["tle-writer-alpha5"].status, "skip")

    def test_a_list_that_holds_one_answer_and_iterates_another_fails_in_words(self):
        """Finding 5, the owner's rule for a record extended to its container: a list subclass whose own iteration shows
        other records than it holds has no one answer."""
        def two_faced(cls_iter):
            class Shows(list):
                def __iter__(self):
                    return cls_iter(list.__iter__(self))
            return Shows

        def doubled(rs):
            out = []
            for r in rs:
                r = dict(r)
                if "_refused" not in r and r.get("mean_motion") is not None:
                    r["mean_motion"] = str(float(r["mean_motion"]) * 2)
                out.append(r)
            return out

        class Holds(Reference):
            """Holds records with a doubled mean motion; its own iteration hands out the right ones."""
            def parse(self, raw, fmt):
                right = super().parse(raw, fmt)
                lst = two_faced(lambda it: iter(right))(doubled(right))
                return lst
        r = run(Holds())
        self.assertEqual(failing(r), THREE)
        self.assertTrue(any("shows other entries than it holds" in i.detail for i in fails(r)))
        self.assertEqual(failing(run(shaped(two_faced(lambda it: it)))), [])     # twin: a list subclass that agrees

    def test_an_empty_answer_that_holds_a_record_and_iterates_none_fails(self):
        """Finding 5 on the provider's empty answer: one invented record held, none iterated."""
        from gpconf.runner import CaseResult, Runner

        class Shows(list):
            def __iter__(self):
                return iter(())
        invented = {"norad_cat_id": 0, "object_name": "NO DATA", "epoch": "2000-01-01T00:00:00", "mean_motion": "0"}

        def check(wrap):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    return wrap([dict(invented)])
            body = open(os.path.join(ROOT, "recorded", "celestrak-no-gp-data-found.txt"), "rb").read()
            res = CaseResult("x", "x")
            Runner(Adapter(), root=ROOT, fetch_hints=False).check_empty_answer(res, "fixtures/x/raw/y.tle", "tle", body, body.decode().strip(), 404)
            return res.items[0]
        self.assertEqual(check(Shows).status, "fail")
        self.assertIn("shows other entries than it holds", check(Shows).detail)
        self.assertEqual(check(list).status, "fail")                                 # twin: the invented record, plainly
        self.assertEqual(check(lambda x: []).status, "pass")                         # and no record passes

    def test_a_record_is_graded_by_keys_and_brackets_its_get_and_items_are_not_read(self):
        """Finding 5, as the owner ruled on the third reading: a dict subclass honest through keys() and [] and in what
        it holds, doubling a value through get() or items() only, is graded by the face the runner reads, and passes:
        a stated limit (D-337, docs/ADAPTERS.md). A mend compared those faces too; it failed correct record types."""
        class GetLies(dict):
            def get(self, k, default=None):
                v = dict.get(self, k, default)
                return str(float(v) * 2) if k == "mean_motion" and v is not None else v

        class ItemsLie(dict):
            def items(self):
                return [(k, (str(float(v) * 2) if k == "mean_motion" and v is not None else v)) for k, v in dict.items(self)]
        for cls in (GetLies, ItemsLie):
            with self.subTest(record=cls.__name__):
                self.assertEqual(failing(run(every_record(cls))), [])

        class BracketsLie(dict):                                                   # twin: the face that is read
            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                return str(float(v) * 2) if k == "mean_motion" and v is not None else v
        r = run(every_record(BracketsLie))
        self.assertEqual(failing(r), THREE)
        self.assertTrue(any("keys() and [] show other fields or values than it holds" in i.detail for i in fails(r)))

    def test_the_reading_does_not_raise_on_a_huge_integer_or_a_deep_nest(self):
        """Finding 3's absurd cases: str() of an int of more than 4,300 digits, and a list nested 200,000 deep."""
        from gpconf import plain as _plain

        class Rec(dict):
            pass
        self.assertEqual(type(_plain.record(Rec(n=10 ** 5000))), dict)
        deep = []
        for _ in range(200000):
            deep = [deep]
        self.assertTrue(_plain.is_plain(_plain.value(deep)))

    def test_an_exception_class_with_a_made_up_name_is_named_by_its_own(self):
        """Finding 6i: an exception class whose metaclass makes up a __name__ is named by the one it was given."""
        class Meta(type):
            @property
            def __name__(cls):
                return 42

        class Odd(ValueError, metaclass=Meta):
            pass

        class Raises(Reference):
            def parse(self, raw, fmt):
                if fmt == "tle":
                    raise Odd("no")
                return super().parse(raw, fmt)
        r = run(Raises())
        self.assertTrue(any("parser raised Odd: no" in i.detail for i in fails(r)), [i.detail[:80] for i in fails(r)][:2])



class TheBoundarysSecondReading(unittest.TestCase):
    """The separate reviewer's second reading of D-337 (2026-10-15), under the owner's model. Each route with its twin."""

    def test_a_timezone_is_read_from_what_it_holds(self):
        """Finding 1: a datetime.timezone passed the guard as it was, with the parser's own timedelta and str subclasses
        inside; their methods ran later, and one raising the runner's ParserExit stopped the case early, reading pass."""
        import datetime as _dt
        from gpconf.runner import ParserExit

        class Off(_dt.timedelta):
            def __repr__(self):
                raise ParserExit("hidden")

        class Name(str):
            def __eq__(self, other):
                raise ParserExit("hidden")
            __hash__ = str.__hash__

        class Encodes(Reference):
            def alpha5_encode(self, n):
                return _dt.timezone(Off(hours=1), Name("x"))
        r = run(Encodes(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        self.assertEqual(r.status, "fail")
        self.assertEqual(next(i.status for i in r.items if i.check == "alpha5-encode"), "fail")

        class Plain(Reference):                                                    # twin: a plain timezone, as wrong
            def alpha5_encode(self, n):
                return _dt.timezone(_dt.timedelta(hours=1))
        r = run(Plain(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        self.assertEqual(next(i.status for i in r.items if i.check == "alpha5-encode"), "fail")
        from gpconf import plain as _plain
        self.assertTrue(_plain.is_plain(_plain.value(_dt.timezone(Off(hours=1), Name("x")))))

    def test_a_property_whose_attribute_error_misbehaves_is_the_runners_own(self):
        """Finding 1: the parser's own AttributeError passed the guard, and a caller that looked a hook up with no default
        (the empty-answer check did, for parse) worded it with str() after the guard, running the parser's __str__."""
        from gpconf.runner import ParserExit, _Guarded

        class Odd(AttributeError):
            def __str__(self):
                raise ParserExit("hidden")

        class Hook(Reference):
            @property
            def alpha5_decode(self):
                raise Odd("no")
        events = []
        with self.assertRaises(AttributeError) as cm:
            _Guarded(Hook(), events).alpha5_decode
        self.assertIs(type(cm.exception), AttributeError)                           # the runner's own, plain
        self.assertIn("could not be read", str(cm.exception))                        # its text read inside the guard
        r = run(Hook(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        self.assertEqual(next(i.status for i in r.items if i.check == "alpha5-decode"), "skip")   # absent, as with no hook

    def test_a_parser_exit_the_guard_did_not_count_fails_the_case(self):
        """Finding 1: run_case's `except ParserExit: pass` trusted that the guard had counted it; one raised after the
        guard by the parser's code stopped the case early, and what had passed so far read as a pass."""
        from unittest import mock
        from gpconf.runner import ParserExit, Runner
        with mock.patch.object(Runner, "run_vectors", side_effect=ParserExit("raised after the guard")):
            r = run(Reference(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        self.assertEqual(r.status, "fail")
        self.assertTrue(any(i.check == "parser-exit" for i in r.items))

    def test_containers_that_fill_themselves_or_reorder_are_one_answer(self):
        """Finding 2: what a list or dict subclass held was read before its own faces, so one that fills itself when first
        read was judged two-faced; and an answer's records in another order were, though their order is not graded."""
        class Lazy(list):
            def __init__(self, src):
                super().__init__()
                self.src = src

            def __iter__(self):
                if not list.__len__(self):
                    self.extend(self.src)
                return list.__iter__(self)

            def __len__(self):
                if not list.__len__(self):
                    self.extend(self.src)
                return list.__len__(self)

        class Reversed(list):
            def __iter__(self):
                return iter(list(list.__iter__(self))[::-1])

        class Caches(dict):
            """Converts each field on first read and keeps the converted value."""
            def __init__(self, r):
                super().__init__({k: ("raw", v) for k, v in r.items()})

            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                if type(v) is tuple and len(v) == 2 and v[0] == "raw":
                    v = v[1]
                    dict.__setitem__(self, k, v)
                return v

            def get(self, k, default=None):
                return self[k] if k in self else default

            def items(self):
                return [(k, self[k]) for k in dict.keys(self)]
        for name, adapter in (("a list that fills itself", shaped(Lazy)), ("records in another order", shaped(Reversed)),
                              ("records that convert on first read", every_record(Caches))):
            with self.subTest(how=name):
                self.assertEqual(failing(run(adapter)), [])

    def test_a_field_listed_twice_with_one_value_is_one_field(self):
        """Finding 3: a mapping that lists a field twice with the same value (defaults layered under the parser's values)
        failed as "a str subclass beside the plain key"; two values for one field still fail, in plain words."""
        from collections.abc import Mapping

        def layered(dupe_value):
            class Layered(Mapping):
                """Lists center_name twice, the parser's value under a default; [] answers the default the second time."""
                def __init__(self, r):
                    self.r = dict(r)
                    self.asked = 0

                def __getitem__(self, k):
                    if k == "center_name":
                        self.asked += 1
                        if self.asked == 2:
                            return dupe_value(self.r[k])
                    return self.r[k]

                def __iter__(self):
                    return iter(list(self.r) + [k for k in ("center_name",) if k in self.r])

                def __len__(self):
                    return len(self.r) + ("center_name" in self.r)

                def keys(self):
                    return list(iter(self))
            return Layered
        self.assertEqual(failing(run(every_record(layered(lambda v: v)))), [])
        r = run(every_record(layered(lambda v: "MARS")))
        self.assertTrue(failing(r))
        self.assertFalse([i for i in fails(r) if "str subclass" in i.detail])

    def test_a_mapping_that_is_not_a_dict_is_graded_by_keys_and_brackets(self):
        """Finding 5, as the owner ruled on the third reading: a mapping that is not a dict has no storage of its own to
        compare with, and is graded by the one face the runner reads, keys() and []; one doubling a value through
        items() only passes, a stated limit (D-337). A mend compared items() and get() too, and failed correct types."""
        from collections.abc import Mapping

        class Faces(Mapping):
            def __init__(self, r):
                self.r = dict(r)

            def __getitem__(self, k):
                return self.r[k]

            def __iter__(self):
                return iter(self.r)

            def __len__(self):
                return len(self.r)

            def items(self):
                return [(k, (str(float(v) * 2) if k == "mean_motion" and v is not None else v)) for k, v in self.r.items()]
        self.assertEqual(failing(run(every_record(Faces))), [])

        class Brackets(Faces):                                                     # twin: the face that is read
            def __getitem__(self, k):
                v = self.r[k]
                return str(float(v) * 2) if k == "mean_motion" and v is not None else v
        self.assertEqual(failing(run(every_record(Brackets))), THREE)

    def test_writer_words_and_nothing_written(self):
        """Finding 4: a two-faced writer answer read "'Problem' object is not iterable"; with nothing written, the checksum
        item read "pass: 0 records written" beside two catalog-field items."""
        from gpconf.runner import Unsupported

        class TwoFaced(list):
            def __iter__(self):
                return iter(["x"])

        class Writer(Reference):
            def write_tle(self, record):
                return TwoFaced(super().write_tle(record))
        r = run(Writer(), cases=["tle-writer-alpha5"])["tle-writer-alpha5"]
        details = " ".join(i.detail for i in r.items)
        self.assertNotIn("'Problem' object", details)
        self.assertIn("shows other entries than it holds", details)

        class Nothing(Reference):
            def write_tle(self, record):
                if record["norad_cat_id"] <= 339999 and record["norad_cat_id"] >= 0:
                    raise Unsupported("no writer")
                raise ValueError("cannot encode")
        r = run(Nothing(), cases=["tle-writer-alpha5"])["tle-writer-alpha5"]
        by = [(i.check, i.status) for i in r.items]
        self.assertIn(("tle-checksums-valid", "not-exercised"), by)
        self.assertEqual(len([c for c, _ in by if c == "tle-writer-catalog-field"]), 1, by)

    def test_a_callable_adapter_answers_the_empty_answer_and_bytes_input_is_text(self):
        """Finding 6: the empty-answer check looked up parse() with no fallback to the adapter itself; and a refusal's
        _input given as bytes was quoted as "b'...'" text."""
        from gpconf.runner import CaseResult, Runner, split_refusals
        body = open(os.path.join(ROOT, "recorded", "celestrak-no-gp-data-found.txt"), "rb").read()
        res = CaseResult("x", "x")
        Runner(lambda raw, fmt: [], root=ROOT, fetch_hints=False).check_empty_answer(res, "fixtures/x/raw/y.tle", "tle", body, body.decode().strip(), 404)
        self.assertEqual(res.items[0].status, "pass", res.items[0].detail)
        _, refusals, _ = split_refusals([{"_refused": "corrupt", "_input": b"1 25544U 98067A"}])
        self.assertEqual(refusals[0]["input"], "1 25544U 98067A")

    def test_nested_subclasses_that_agree_are_read_quickly(self):
        """Finding 7 (outside the model, mended for the cost): faces that hand back the same objects are read once."""
        import time
        from gpconf import plain as _plain

        class D(dict):
            pass
        x = {"v": 1}
        for _ in range(14):
            x = D(v=x)
        start = time.monotonic()
        self.assertEqual(type(_plain.value(x)), dict)
        self.assertLess(time.monotonic() - start, 1.0)


class TheBoundarysThirdReading(unittest.TestCase):
    """The separate reviewer's third reading of D-337 (2026-10-15), and the owner's ruling on it: the rule that a
    container which holds one thing and shows another has no one answer is bounded to the containers with storage of
    their own, a dict, list or tuple subclass, compared with the one face the runner reads; every other container is
    graded by that one face, a stated limit; and a transparent proxy is read through its own methods where it says it is
    a record, an integer or a datetime. Each route with its twin."""

    def test_a_transparent_proxy_is_read_as_what_it_says_it_is(self):
        """The wrapt.ObjectProxy and lazy-object-proxy pattern: __class__ forwarded, so isinstance() sees the wrapped
        type, which type() does not; records, integers and epochs behind one failed every case that reads them."""
        import datetime as _dt

        class Proxy:
            __slots__ = ("__wrapped__",)

            def __init__(self, w):
                object.__setattr__(self, "__wrapped__", w)

            @property
            def __class__(self):
                return type(self.__wrapped__)

            def __getattr__(self, n):
                return getattr(self.__wrapped__, n)

            def __str__(self):
                return str(self.__wrapped__)

            def __iter__(self):
                return iter(self.__wrapped__)

            def __len__(self):
                return len(self.__wrapped__)

            def __getitem__(self, k):
                return self.__wrapped__[k]

            def __index__(self):
                return self.__wrapped__.__index__()

            def __bool__(self):
                return bool(self.__wrapped__)

        def epoch(v):
            return Proxy(_dt.datetime.strptime(v[:26], "%Y-%m-%dT%H:%M:%S.%f")) if type(v) is str else v
        for name, adapter in (("records", every_record(Proxy, only=lambda r: "_refused" not in r)),
                              ("catalog numbers", with_field("norad_cat_id", Proxy)),
                              ("epochs", with_field("epoch", epoch))):
            with self.subTest(behind_a_proxy=name):
                self.assertEqual(failing(run(adapter)), [])
        for name, adapter in (("records", every_record(lambda r: Proxy(dict(r, mean_motion="1.5")), only=lambda r: "_refused" not in r)),
                              ("catalog numbers", with_field("norad_cat_id", lambda v: Proxy(v + 1))),
                              ("epochs", with_field("epoch", lambda v: Proxy(_dt.datetime(2001, 1, 1))))):
            with self.subTest(twin_wrong_behind_a_proxy=name):
                self.assertEqual(failing(run(adapter)), THREE)

    def test_correct_containers_the_extended_rule_failed_now_pass(self):
        """The two false fails of the extended rule: a list subclass whose [] looks a record up by catalog number, and a
        mapping registered with Mapping.register that has keys() and [] but no items() or get()."""
        from collections.abc import Mapping

        class ById(list):
            def __getitem__(self, cat):
                if isinstance(cat, slice):
                    return list.__getitem__(self, cat)
                for r in list.__iter__(self):
                    if r.get("norad_cat_id") == cat:
                        return r
                raise KeyError(cat)

        class Rec:
            def __init__(self, r):
                self._r = dict(r)

            def keys(self):
                return self._r.keys()

            def __getitem__(self, k):
                return self._r[k]

            def __iter__(self):
                return iter(self._r)

            def __len__(self):
                return len(self._r)
        Mapping.register(Rec)
        self.assertEqual(failing(run(shaped(ById))), [])
        self.assertEqual(failing(run(every_record(Rec))), [])

        class WrongRec(Rec):                                                       # twin: a wrong value through []
            def __getitem__(self, k):
                return "1.5" if k == "mean_motion" else self._r[k]
        self.assertEqual(failing(run(every_record(WrongRec))), THREE)

    def test_a_container_other_than_a_dict_list_or_tuple_subclass_is_graded_by_the_face_read(self):
        """The stated limit: a deque or UserList subclass, or a dict subclass behind MappingProxyType, ChainMap or
        UserDict, that shows the right records through the face the runner reads while it holds wrong ones, is graded
        by that face. The twins: the same containers showing a wrong value through that face fail."""
        import collections
        import types

        def wrongly(r):
            r = dict(r)
            if r.get("mean_motion") is not None and "_refused" not in r:
                r["mean_motion"] = "1.5"
            return r

        def shows(base, right_face):
            class Shows(base):
                def __init__(self, right, wrong):
                    super().__init__(wrong)
                    self._shown = right if right_face else wrong

                def __iter__(self):
                    return iter(self._shown)

            class Adapter(Reference):
                def parse(self, raw, fmt):
                    right = super().parse(raw, fmt)
                    return Shows(right, [wrongly(r) for r in right])
            return Adapter()

        class Holds(dict):
            """Holds a wrong mean motion, shows the right one through every method."""
            def __init__(self, right):
                super().__init__(wrongly(right))
                self._right = dict(right)

            def keys(self):
                return self._right.keys()

            def __getitem__(self, k):
                return self._right[k]
        for name, base in (("a deque subclass", collections.deque), ("a UserList subclass", collections.UserList)):
            with self.subTest(container=name):
                self.assertEqual(failing(run(shows(base, True))), [])
                self.assertEqual(failing(run(shows(base, False))), THREE)
        for name, wrap in (("MappingProxyType", types.MappingProxyType), ("ChainMap", collections.ChainMap), ("UserDict", collections.UserDict)):
            with self.subTest(behind=name):
                self.assertEqual(failing(run(every_record(lambda r, wrap=wrap: wrap(Holds(r))))), [])
                self.assertEqual(failing(run(every_record(lambda r, wrap=wrap: wrap(wrongly(r))))), THREE)
        r = run(every_record(Holds))                                               # the bare dict subclass is compared
        self.assertEqual(failing(r), THREE)

    def test_a_writer_that_writes_some_and_declines_the_rest_is_graded_on_what_it_wrote(self):
        """The writer's words: write_tle answering Unsupported for most records and writing three with a wrong catalog
        field had only the all-or-none item for the catalog field, and nothing said the three were wrong (a loss in this
        change's second form; the runner before D-337 graded them, and does again)."""
        from gpconf import tle as T
        from gpconf.runner import Unsupported

        def writer(field):
            class W(Reference):
                n = 0

                def write_tle(self, rec):
                    out = super().write_tle(rec)
                    type(self).n += 1
                    if type(self).n > 3:
                        raise Unsupported("tle-writing")
                    lines = list(out) if not isinstance(out, str) else out.splitlines()
                    l1, l2 = lines[-2], lines[-1]
                    l1, l2 = l1[:2] + field(l1[2:7]) + l1[7:68], l2[:2] + field(l2[2:7]) + l2[7:68]
                    return [l1 + str(T.checksum(l1 + "0")), l2 + str(T.checksum(l2 + "0"))]
            return W()
        def graded(items):
            return [i.status for i in items if i.check == "tle-writer-catalog-field" and "answered unsupported" not in i.detail]
        items = run(writer(lambda f: "00005"), cases=["tle-writer-alpha5"])["tle-writer-alpha5"].items
        self.assertEqual(graded(items), ["fail"], [(i.check, i.status, i.detail[:80]) for i in items])
        items = run(writer(lambda f: f), cases=["tle-writer-alpha5"])["tle-writer-alpha5"].items     # twin: right fields
        self.assertEqual(graded(items), ["pass"], [(i.check, i.status, i.detail[:80]) for i in items])

    def test_the_runners_own_problem_type_is_worded_never_shown(self):
        """A hook answering a list whose iteration shows other entries than it holds read "A0000 -> Problem('...')"."""
        class TwoFaced(list):
            def __iter__(self):
                return iter(["x"])

        class H(Reference):
            def alpha5_decode(self, f):
                return TwoFaced([super().alpha5_decode(f)])
        r = run(H(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        details = " ".join(i.detail for i in r.items if i.status == "fail")
        self.assertIn("an answer that is a list (TwoFaced) whose own iteration shows other entries than it holds", details)
        self.assertNotIn("Problem(", details)

        class Plain(Reference):                                                    # twin: a plain wrong answer, plainly
            def alpha5_decode(self, f):
                return [super().alpha5_decode(f)]
        r = run(Plain(), cases=["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        self.assertEqual(r.status, "fail")

    def test_a_false_declaration_of_a_type_of_its_own_is_false(self):
        """The capability declaration {"_adapter": {"refusals": X}} with X a false value of the adapter's own type (the
        numpy.bool_ pattern: bool() False, str() 'False') read as a true one, and a dropped record read as dropped
        silently by an adapter that reports refusals."""
        class B:
            def __bool__(self):
                return False

            def __str__(self):
                return "False"

        def declares(x):
            class A(Reference):
                def parse(self, raw, fmt):
                    return [{"_adapter": {"refusals": x}}] + [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return A()
        class No:
            def __bool__(self):
                return False

            def __str__(self):
                return "no"

        def reported(x):
            r = run(declares(x), cases=["corrupt-input"])["corrupt-input"]
            return next(i for i in r.items if i.check == "corrupt-tle-line-short").counts.get("refusals_reported")
        for x in (B(), No(), False, 0):                  # the fourth reading: its truth value, not its text
            with self.subTest(declaration=f"{type(x).__name__} {x}"):
                self.assertFalse(reported(x))
        for x in (True, "False", 1):                     # twins: true, as bool() has always read them
            with self.subTest(declaration=f"{type(x).__name__} {x!r}"):
                self.assertTrue(reported(x))



class TheBoundarysFourthReading(unittest.TestCase):
    """The separate reviewer's fourth reading of D-337 (2026-10-16), under the owner's model and the bounded ruling. Each
    route with its twin."""

    @staticmethod
    def proxy(w, cls=None):
        class Proxy:
            __slots__ = ("__wrapped__",)

            def __init__(self, w):
                object.__setattr__(self, "__wrapped__", w)

            @property
            def __class__(self):
                return cls or self.__wrapped__.__class__

            def __getattr__(self, n):
                return getattr(self.__wrapped__, n)

            def __str__(self):
                return str(self.__wrapped__)

            def __iter__(self):
                return iter(self.__wrapped__)

            def __len__(self):
                return len(self.__wrapped__)

            def __getitem__(self, k):
                return self.__wrapped__[k]

            def __index__(self):
                import operator
                return operator.index(self.__wrapped__)

            def __int__(self):
                return int(self.__wrapped__)

            def __bool__(self):
                return bool(self.__wrapped__)
        return Proxy(w)

    def test_a_proxy_that_says_it_is_a_datetime_is_never_its_text(self):
        """Finding 1, an escape: fields giving a wrong instant beside a utcoffset() that is no timedelta, or fields that
        are text, made the reading fall back to the proxy's str(), the right epoch, and the wrong value passed."""
        import datetime as _dt

        def epoch(v):
            return _dt.datetime.strptime(v[:26], "%Y-%m-%dT%H:%M:%S.%f")

        class WrongFieldsRightText:
            def __init__(self, w):
                self.w = w

            @property
            def __class__(self):
                return _dt.datetime

            def __getattr__(self, n):
                if n == "year":
                    return 2001
                if n == "utcoffset":
                    return lambda: 0
                return getattr(self.w, n)

            def __str__(self):
                return self.w.isoformat()

        class TextFields(WrongFieldsRightText):
            def __getattr__(self, n):
                if n in ("year", "month", "day", "hour", "minute", "second", "microsecond", "fold"):
                    return str(getattr(self.w, n))
                return getattr(self.w, n)
        for cls in (WrongFieldsRightText, TextFields):
            with self.subTest(proxy=cls.__name__):
                self.assertEqual(failing(run(with_field("epoch", lambda v, cls=cls: cls(epoch(v))))), THREE)
        self.assertEqual(failing(run(with_field("epoch", lambda v: self.proxy(epoch(v))))), [])   # twin: a true proxy

    def test_a_proxied_integer_of_any_integral_type_reads(self):
        """Finding 2, a false fail: a proxy around a registered numbers.Integral (or numpy's integers) was read as its
        text, "norad_cat_id returned as str", where the bare value and the runner before D-337 passed."""
        import numbers

        class CatNo:
            def __init__(self, n):
                self.n = n

            def __index__(self):
                return self.n
        numbers.Integral.register(CatNo)
        self.assertEqual(failing(run(with_field("norad_cat_id", lambda v: self.proxy(CatNo(v))))), [])
        self.assertEqual(failing(run(with_field("norad_cat_id", lambda v: self.proxy(CatNo(v + 1))))), THREE)   # twin
        try:
            import numpy as np
        except ImportError:
            return
        self.assertEqual(failing(run(with_field("norad_cat_id", lambda v: self.proxy(np.int64(v))))), [])

    def test_a_record_that_holds_its_answer_or_itself_is_read_once(self):
        """Finding 9 (outside the model, mended for the cost, as the second reading's item 7 was): each container was read
        once per path to it, so three records holding their answer took ten seconds a file and four did not end."""
        import time

        class BackRef(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    r["_answer"] = out
                return out

        class SelfRef(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    r["_self"] = r
                    r["_again"] = r
                return out
        for cls in (BackRef, SelfRef):
            with self.subTest(adapter=cls.__name__):
                start = time.monotonic()
                self.assertEqual(failing(run(cls())), [])
                self.assertLess(time.monotonic() - start, 60)

        class InItsOwnField(Reference):                                          # twin: itself where a value goes
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" not in r:
                        r["mean_motion"] = r
                return out
        self.assertEqual(failing(run(InItsOwnField())), THREE)

    def test_entries_in_another_order_are_named_as_in_order(self):
        """Finding 7: a list subclass that iterates its entries in another order, one of them no record, read as
        showing other entries than it holds, where the plain list read "holds str at entry"."""
        class Reversed(list):
            def __iter__(self):
                return iter(list(list.__iter__(self))[::-1])
        r = run(shaped(lambda out: Reversed(list(out) + ["x"])))
        self.assertTrue(any("holds str at entry" in i.detail for i in fails(r)), [i.detail[:100] for i in fails(r)][:2])
        self.assertFalse([i for i in fails(r) if "shows other entries" in i.detail])
        r = run(shaped(lambda out: list(out) + ["x"]))                            # twin: the plain list, the same words
        self.assertTrue(any("holds str at entry" in i.detail for i in fails(r)))

    def test_a_proxy_is_read_through_its_own_methods_only(self):
        """Finding 10, the stated limit within the proxy ruling: what a dict subclass behind a proxy holds is not
        compared with what it shows. The twin: the same dict subclass bare is compared, and fails."""
        def wrongly(r):
            r = dict(r)
            if r.get("mean_motion") is not None and "_refused" not in r:
                r["mean_motion"] = "1.5"
            return r

        class Holds(dict):
            def __init__(self, right):
                super().__init__(wrongly(right))
                self._right = dict(right)

            def keys(self):
                return self._right.keys()

            def __getitem__(self, k):
                return self._right[k]
        self.assertEqual(failing(run(every_record(lambda r: self.proxy(Holds(r))))), [])
        self.assertEqual(failing(run(every_record(Holds))), THREE)



class TheBoundarysFifthReading(unittest.TestCase):
    """The separate reviewer's fifth reading of D-337 (2026-10-16), of the fourth reading's mend. Each route with its
    twin."""

    def test_a_container_met_at_two_depths_is_read_at_each(self):
        """Finding 1, a false fail the mend made: the memo kept one reading per container, so a record met first deep
        inside another record's unknown field was read there, its epoch cut at the depth limit, and its own entry
        failed. The twin: the same answer without the deep reference."""
        import datetime as _dt

        def deep(n):
            class Deep(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    for r in out:
                        if "_refused" not in r and isinstance(r.get("epoch"), str):
                            r["epoch"] = _dt.datetime.fromisoformat(r["epoch"])
                    recs = [r for r in out if "_refused" not in r]
                    if n and len(recs) >= 2:
                        chain = recs[1]
                        for _ in range(n):
                            chain = [chain]
                        recs[0]["_deep"] = chain
                    return out
            return Deep()
        for n in (29, 30, 31, 0):
            with self.subTest(lists_down=n):
                self.assertEqual(failing(run(deep(n))), [])

    def test_the_declaration_is_read_from_the_pairs_a_record_is_read_by(self):
        """Finding 2, a false fail the mend made: the declaration's truth was read through `in` and [], so a record
        type registered as a Mapping with keys() and [] only raised KeyError inside the guard, the parser raising; and
        one whose __contains__ said no lost it. The twins: a plain dict declaring the same."""
        from collections.abc import Mapping

        class Rec:
            def __init__(self, r):
                self._r = dict(r)

            def keys(self):
                return self._r.keys()

            def __getitem__(self, k):
                return self._r[k]
        Mapping.register(Rec)

        class Hides(Rec):
            def __contains__(self, k):
                return False

        class NoBool:
            def __bool__(self):
                return False

            def __str__(self):
                return "False"

        def reported(x):
            class A(Reference):
                def parse(self, raw, fmt):
                    return [{"_adapter": x}] + [r for r in super().parse(raw, fmt) if "_refused" not in r]
            r = run(A(), cases=["corrupt-input"])["corrupt-input"]
            self.assertFalse([i for i in r.items if "parser raised" in (i.detail or "")])
            return next(i for i in r.items if i.check == "corrupt-tle-line-short").counts.get("refusals_reported")
        for cls in (Rec, Hides, dict):
            with self.subTest(declaration=cls.__name__):
                self.assertTrue(reported(cls({"refusals": True})))
                self.assertFalse(reported(cls({"refusals": NoBool()})))

    def test_an_integral_whose_int_raises_is_its_text(self):
        """Finding 3, older: a numbers.Integral whose int() raises TypeError (numpy's timedelta64) made the parser
        "raise", though it sat in a key every check ignores; and a proxy around an Integral with __int__ only raised
        through the proxy's own __index__. The twins: the same in a graded field fails as text, not as a raise."""
        import numbers

        class Odd:
            def __int__(self):
                raise TypeError("no int")
        numbers.Integral.register(Odd)

        class IntOnly:
            def __init__(self, n):
                self.n = n

            def __int__(self):
                return self.n
        numbers.Integral.register(IntOnly)
        proxy = TheBoundarysFourthReading.proxy
        self.assertEqual(failing(run(every_record(lambda r: dict(r, _age=Odd()), only=lambda r: "_refused" not in r))), [])
        self.assertEqual(failing(run(with_field("norad_cat_id", lambda v: proxy(IntOnly(v))))), [])
        self.assertEqual(failing(run(with_field("norad_cat_id", lambda v: proxy(IntOnly(v + 1))))), THREE)   # twin: wrong
        r = run(with_field("norad_cat_id", lambda v: Odd()))                       # twin: where a value goes, it fails
        self.assertEqual(failing(r), THREE)
        self.assertFalse([i for i in fails(r) if "parser raised" in i.detail])
        try:
            import numpy as np
        except ImportError:
            return
        self.assertEqual(failing(run(every_record(lambda r: dict(r, _age=np.timedelta64(5, "s")), only=lambda r: "_refused" not in r))), [])

    def test_a_shared_container_is_looked_at_once(self):
        """Finding 8 (outside the model, mended for the cost): a list built as L = [L', L'], twenty levels deep, under
        a key every check ignores, was walked as a tree by the checks on the reading and by the text the runner made of
        it (str()), a million paths; a deque of it too, read through its iteration."""
        import time
        x = [1]
        for _ in range(20):
            x = [x, x]
        import collections
        for name, held in (("a list", x), ("a deque", collections.deque([x, x]))):
            with self.subTest(under_an_unknown_key=name):
                start = time.monotonic()
                self.assertEqual(failing(run(every_record(lambda r, held=held: dict(r, _shared=held), only=lambda r: "_refused" not in r))), [])
                self.assertLess(time.monotonic() - start, 60)
        r = run(with_field("object_name", lambda v: x))                          # twin: the same list where text goes fails
        self.assertTrue(failing(r))
        r = run(with_field("object_name", lambda v: collections.deque([x, x])))  # and so does the deque
        self.assertTrue(failing(r))

    def test_a_text_key_behind_a_proxy_is_no_key(self):
        """Finding 7, the owner's ruling: proxied strings are a stated limit, not read; a record whose keys are proxied
        strings has no field the runner knows. The twin: the same record with plain keys passes."""
        proxy = TheBoundarysFourthReading.proxy

        class Key:
            """A hashable proxy around a str key."""
            def __init__(self, s):
                self.s = s

            @property
            def __class__(self):
                return str

            def __hash__(self):
                return hash(self.s)

            def __eq__(self, other):
                return self.s == other

            def __str__(self):
                return self.s
        self.assertTrue(failing(run(every_record(lambda r: {Key(k): v for k, v in r.items()}, only=lambda r: "_refused" not in r))))
        self.assertEqual(failing(run(every_record(lambda r: {k: v for k, v in r.items()}))), [])
        del proxy



class TheBoundarysSixthReading(unittest.TestCase):
    """The separate reviewer's sixth reading of D-337 (2026-10-16), of the fifth reading's mend; the owner's stopping
    rule applies. Each route with its twin."""

    def test_a_container_in_a_text_field_is_compared_whole(self):
        """Finding 1, an escape the mend made: a text cut short (reprlib) made two different containers alike, so a
        parser whose names are tuples of characters, changed past the sixth on an edited file, had the change hidden
        from the corrupt-input case's exact comparison with the unedited file. The twin: nothing changed, nothing
        flagged."""
        unedited = set()
        for n in ("unedited-sets.tle", "unedited-rows.csv", "unedited-array.json"):
            with open(os.path.join(ROOT, "derived", "corrupt-input", n), "rb") as f:
                unedited.add(f.read())

        def names_as_tuples(edit):
            class A(Reference):
                def parse(self, raw, fmt):
                    out = []
                    for r in super().parse(raw, fmt):
                        if "_refused" not in r and r.get("object_name"):
                            r, name = dict(r), r["object_name"]
                            if edit and raw not in unedited:
                                name = name[:7] + "#" + name[8:] if len(name) > 7 else name + "########"
                            r["object_name"] = tuple(name)
                        out.append(r)
                    return out
            return A()

        def neighbours(edit):
            items = run(names_as_tuples(edit), cases=["corrupt-input"])["corrupt-input"].items
            return [i.status for i in items if i.check == "corrupt-input-neighbours-load"]
        self.assertIn("fail", neighbours(True))
        self.assertNotIn("fail", neighbours(False))

    def test_an_integer_python_will_not_write_is_no_raise(self):
        """Finding 3: an integer of more than 4,300 digits under a key no check reads made the runner's own str()
        raise, and every file failed as the parser raising. The twin: in a graded field it fails as a wrong value."""
        r = run(every_record(lambda r: dict(r, _big=10 ** 5000), only=lambda r: "_refused" not in r))
        self.assertEqual(failing(r), [])
        r = run(with_field("object_name", lambda v: 10 ** 5000))
        self.assertEqual(failing(r), THREE)
        self.assertFalse([i for i in fails(r) if "parser raised" in i.detail])

    def test_a_shared_list_ends_in_every_field_and_in_a_refusal(self):
        """Finding 4 (b), a hang, never negligible: a list that holds itself twice at each of 30 levels, in a graded
        field or a refusal's input, was written out by the runner's own str() as a tree, a billion values; a field's
        value is now bounded, written past the bound as a marker with its digest. The twins: each fails, in words."""
        import time
        x = [1]
        for _ in range(30):
            x = [x, x]
        for field in ("norad_cat_id", "mean_motion", "epoch", "object_name"):
            with self.subTest(field=field):
                start = time.monotonic()
                r = run(with_field(field, lambda v: x), cases=["kvn-syntax-variants"])
                self.assertLess(time.monotonic() - start, 60)
                self.assertTrue(failing(r))
                self.assertFalse([i for i in fails(r) if "internal error" in i.detail or "parser raised" in i.detail])
        start = time.monotonic()
        r = run(every_record(lambda r: dict(r, _input=x), only=lambda r: "_refused" in r), cases=["corrupt-input"])
        self.assertLess(time.monotonic() - start, 60)
        self.assertFalse([i for i in fails(r) if "internal error" in i.detail or "parser raised" in i.detail])

    def test_faces_that_copy_a_shared_list_are_compared_quickly(self):
        """Finding 4 (a), the cost: faces compared by keys built as trees, a dict subclass whose [] copies a list
        holding a shared list, quadrupling every two levels; now compared by digest. The twin: a two-faced one still
        fails."""
        import time
        from gpconf import plain as _plain
        big = [1]
        for _ in range(30):
            big = [big, big]

        class Copies(dict):
            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                return list(v) if type(v) is list else v
        start = time.monotonic()
        out = _plain.answer([Copies({"norad_cat_id": i, "_shared": [big]}) for i in range(10)])
        self.assertLess(time.monotonic() - start, 10)
        self.assertTrue(all(type(r) is dict for r in out))

        class Lies(dict):
            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                return [big, 2] if k == "_shared" else v
        self.assertIs(type(_plain.answer([Lies({"norad_cat_id": 1, "_shared": [big]})])[0]), _plain.Problem)



class TheBoundarysSeventhReading(unittest.TestCase):
    """The separate reviewer's seventh reading of D-337 (2026-10-16), under the owner's stopping rule: a crash or a hang
    blamed on the corpus is never negligible. Each route with its twin."""

    def test_a_container_shared_by_many_fields_or_records_is_written_once(self):
        """Finding 1, a hang the mend made: the bound counted values, not characters, and started afresh for every
        field, and the runner wrote each field whole, so 3,000 keys sharing one list of 99,000 integers took 100 s on
        one case, and a field of 99,999 references to one 100,000-character string wrote 10 GB. A container in a
        record's field is now its text, written once in a reading and cut at FIELD_TEXT with a digest. The twins: the
        same list where text goes fails."""
        import time
        from gpconf import plain as _plain
        big = list(range(99_000))
        meta = {f"k{i}": big for i in range(3000)}
        start = time.monotonic()
        self.assertEqual(failing(run(every_record(lambda r: dict(r, _meta=meta), only=lambda r: "_refused" not in r), cases=["kvn-syntax-variants"])), [])
        self.assertLess(time.monotonic() - start, 30)
        self.assertEqual(failing(run(with_field("object_name", lambda v: big), cases=["kvn-syntax-variants"])), ["kvn-syntax-variants"])
        s = "x" * 100_000
        start = time.monotonic()
        rec = _plain.answer([{"norad_cat_id": 1, "_wide": [s] * 99_999}])[0]
        self.assertLess(time.monotonic() - start, 10)
        self.assertLessEqual(len(rec["_wide"]), _plain.FIELD_TEXT + 100)
        other = _plain.answer([{"norad_cat_id": 1, "_wide": [s] * 99_998 + ["y"]}])[0]
        self.assertNotEqual(rec["_wide"], other["_wide"])                         # twin: another content, another text

    def test_a_written_line_that_is_a_shared_list_ends(self):
        """Finding 2, a hang older than the mend: write_tle answering a generator read each line unbounded, and the
        writer's own reading wrote it out. The twin: the same line in a list, which already ended."""
        import time
        x = [1]
        for _ in range(30):
            x = [x, x]

        def writer(shape):
            class W(Reference):
                def write_tle(self, record):
                    return shape([l for l in super().write_tle(record) if l.strip()] + [x])
            return W()
        for name, shape in (("a generator", lambda ls: (l for l in ls)), ("a list", list)):
            with self.subTest(answer=name):
                start = time.monotonic()
                self.assertEqual(failing(run(writer(shape), cases=["tle-writer-alpha5"])), ["tle-writer-alpha5"])
                self.assertLess(time.monotonic() - start, 60)

    def test_an_integer_python_will_not_write_fails_in_words_wherever_it_is(self):
        """Finding 3, a crash older than the mend: such an integer as the catalog number or a counter ended the case as
        an internal error of the runner (an f-string of ids), in a refusal's input it crashed split_refusals, and a
        refusal's catalog field of 5,000 digits crashed field_to_id. The twins: an ordinary wrong value fails the same
        way."""
        huge = 10 ** 5000
        for name, adapter in (("norad_cat_id", with_field("norad_cat_id", lambda v: huge)),
                              ("element_set_no", with_field("element_set_no", lambda v: huge)),
                              ("a refusal's _input", every_record(lambda r: dict(r, _input=[huge]), only=lambda r: "_refused" in r)),
                              ("a refusal's _field", every_record(lambda r: dict(r, _field="9" * 5000), only=lambda r: "_refused" in r)),
                              ("the twin, an ordinary wrong number", with_field("norad_cat_id", lambda v: v + 1))):
            with self.subTest(where=name):
                r = run(adapter)
                self.assertFalse([i for i in fails(r) if "internal error" in i.detail or "parser raised" in i.detail],
                                 [i.detail[:120] for i in fails(r)][:2])
                if "refusal" not in name:   # a wrong value where a number goes fails, the huge one as the ordinary one does
                    self.assertEqual(failing(r), THREE)

    def test_two_equal_sets_read_alike(self):
        """Finding 5, a false fail the mend made: a set read in its order of iteration, and two equal sets can iterate
        differently, so a record type whose [] copies a set field was judged two-faced. The twin: a [] that changes the
        set still is."""
        from gpconf import plain as _plain
        s = {5, 37, 69}
        copy = set([37, 69, 5])

        class Copies(dict):
            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                return set(copy) if k == "_tags" else v

        class Changes(dict):
            def __getitem__(self, k):
                v = dict.__getitem__(self, k)
                return {5, 37, 70} if k == "_tags" else v
        self.assertIs(type(_plain.answer([Copies({"norad_cat_id": 1, "_tags": s})])[0]), dict)
        self.assertIs(type(_plain.answer([Changes({"norad_cat_id": 1, "_tags": s})])[0]), _plain.Problem)

    def test_an_exception_holding_a_shared_list_is_worded_in_bounded_time(self):
        """Finding 7, a hang older than the mend: the guard read str() of a builtin exception whose argument was a shared
        list, quadrupling every two levels. The twin: an ordinary message reads as Python writes it."""
        import time
        x = [1]
        for _ in range(30):
            x = [x, x]

        def raising(arg):
            class R(Reference):
                def parse(self, raw, fmt):
                    raise ValueError(arg)
            return R()
        start = time.monotonic()
        r = run(raising(x), cases=["kvn-syntax-variants"])
        self.assertLess(time.monotonic() - start, 30)
        self.assertTrue(failing(r))
        r = run(raising("bad line"), cases=["kvn-syntax-variants"])
        self.assertTrue(any("parser raised ValueError: bad line" in i.detail for i in fails(r)), [i.detail[:80] for i in fails(r)][:2])



class TheBoundarysEighthReading(unittest.TestCase):
    """The separate reviewer's eighth reading of D-337 (2026-10-16), under the owner's stopping rule. Each route with its
    twin."""

    def test_a_decimal_too_long_for_an_integer_field_fails_in_words(self):
        """Finding 1, a crash older than the mend: a Decimal with an exponent of 4,300 or more passed the guard, and the
        runner's int() raised outside every guard ("internal error in runner"); with an exponent of hundreds of
        thousands the same int() ran for minutes, and the one comparison now refuses both before int() is called. The
        twin: an ordinary wrong Decimal fails the same way."""
        import time
        from decimal import Decimal
        for field in ("norad_cat_id", "element_set_no", "rev_at_epoch"):
            with self.subTest(field=field):
                start = time.monotonic()
                r = run(with_field(field, lambda v: Decimal("1E+5000")))
                self.assertLess(time.monotonic() - start, 30)
                self.assertEqual(failing(r), THREE)
                self.assertFalse([i for i in fails(r) if "internal error" in i.detail])
        self.assertEqual(failing(run(with_field("element_set_no", lambda v: Decimal(v + 1)))), THREE)

    def test_an_adapter_key_beside_the_fields_is_never_written_out(self):
        """Finding 2, a hang the mend made: a record carrying `_adapter` beside its fields kept a container there, and the
        runner wrote it out with str(), a shared list as a tree. The twin: the same under a key of no meaning."""
        import time
        x = [1]
        for _ in range(26):
            x = [x, x]
        for key in ("_adapter", "_meta"):
            with self.subTest(key=key):
                start = time.monotonic()
                self.assertEqual(failing(run(every_record(lambda r, key=key: dict(r, **{key: {"refusals": True, "notes": x}}),
                                                          only=lambda r: "_refused" not in r), cases=["kvn-syntax-variants"])), [])
                self.assertLess(time.monotonic() - start, 30)

    def test_long_leaves_and_many_holders_cost_what_they_are(self):
        """Findings 3 and 4, hangs: a long text, bytes or Decimal was written or digested once per container holding it,
        each distinct container kept up to 100,000 characters, and bytes under a key no check reads were written out for
        every record. Now a container's text is cut at 1,000 characters, a long leaf is written and digested once, and
        a key no check reads is never written. The twins: the same values as the field itself."""
        import time
        from decimal import Decimal
        from gpconf import plain as _plain
        from gpconf.runner import norm_record
        text, raw = "x" * 1_700_000, b"y" * 560_000
        big = Decimal("1" * 1_000_000)
        shared = list(range(99_000))
        for name, recs in (("records holding a long text and their place", [{"norad_cat_id": i, "_src": (text, i)} for i in range(12000)]),
                           ("a field of references to long bytes", [{"norad_cat_id": 1, "_raw": [raw] * 20000}]),
                           ("a field of references to a long Decimal", [{"norad_cat_id": 1, "_d": [big] * 1000}]),
                           ("many small lists around one shared list", [{"norad_cat_id": i, "_w": [shared, i]} for i in range(20000)]),
                           ("records each holding the file's bytes", [{"norad_cat_id": i, "_raw": raw} for i in range(4000)])):
            with self.subTest(answer=name):
                start = time.monotonic()
                out = _plain.answer(recs)
                for r in out:
                    norm_record(r)
                self.assertLess(time.monotonic() - start, 30)
                self.assertTrue(all(type(r) is dict for r in out))
        self.assertEqual(_plain.answer([{"norad_cat_id": 1, "_src": text}])[0]["_src"], text)   # twin: a text as itself

    def test_a_container_and_its_own_text_read_apart(self):
        """Finding 5, an escape the mend made: a container in a field became a plain text, alike with the parser's own
        text that spells the same, so a parser that answered [v] on the unedited file and "[v]" on the edited ones had
        the change hidden from the corrupt-input case's exact comparison. The twin: the same on both reads alike."""
        unedited = set()
        for n in ("unedited-sets.tle", "unedited-rows.csv", "unedited-array.json"):
            with open(os.path.join(ROOT, "derived", "corrupt-input", n), "rb") as f:
                unedited.add(f.read())

        def answers(as_text_on_edited):
            class A(Reference):
                def parse(self, raw, fmt):
                    out = []
                    for r in super().parse(raw, fmt):
                        if "_refused" not in r and r.get("element_set_no") is not None:
                            v = [r["element_set_no"]]
                            r = dict(r, element_set_no=str(v) if as_text_on_edited and raw not in unedited else v)
                        out.append(r)
                    return out
            return A()

        def neighbours(flag):
            items = run(answers(flag), cases=["corrupt-input"])["corrupt-input"].items
            return [i.status for i in items if i.check == "corrupt-input-neighbours-load" and (i.file or "").endswith(".tle")]
        self.assertIn("fail", neighbours(True))
        self.assertNotIn("fail", neighbours(False))

    def test_pythons_own_exception_words_are_kept(self):
        """Finding 6, wording the mend made: an exception's text rebuilt from its arguments differed from Python's where an
        argument is an object, decimal.InvalidOperation's list of conditions among them; and a text exit code that began
        with a bracket was shown unquoted. The twin: an exception holding a shared list is still worded in bounded time."""
        from decimal import Decimal

        def raising(make):
            class R(Reference):
                def parse(self, raw, fmt):
                    make()
            return R()
        r = run(raising(lambda: Decimal("not a number")), cases=["kvn-syntax-variants"])
        self.assertTrue(any("parser raised InvalidOperation: [<class 'decimal.ConversionSyntax'>]" in i.detail for i in fails(r)),
                        [i.detail[:120] for i in fails(r)][:2])
        r = run(raising(lambda: sys.exit("[fatal] bad TLE")), cases=["kvn-syntax-variants"])
        self.assertTrue(any("SystemExit('[fatal] bad TLE')" in i.detail for i in r["kvn-syntax-variants"].items))
        import time
        x = [1]
        for _ in range(26):
            x = [x, x]
        def shared_list():
            raise ValueError(x)
        start = time.monotonic()
        r = run(raising(shared_list), cases=["kvn-syntax-variants"])   # the twin the docstring names
        self.assertLess(time.monotonic() - start, 30)
        self.assertTrue(any(i.detail.startswith("parser raised ValueError: [[") for i in fails(r)), [i.detail[:120] for i in fails(r)][:2])

    def test_the_digit_limit_is_pythons_own(self):
        """Finding 8: the 4,300 was written into the code; with Python's limit set lower, a 1,000-digit counter ended three
        cases as an internal error. The twin: under the default limit the same value fails in words too."""
        if not hasattr(sys, "set_int_max_str_digits"):
            self.skipTest("Python before 3.11 has no limit on the digits it writes")
        old = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            r = run(with_field("element_set_no", lambda v: 10 ** 1000))
            self.assertEqual(failing(r), THREE)
            self.assertFalse([i for i in fails(r) if "internal error" in i.detail])
        finally:
            sys.set_int_max_str_digits(old)
        self.assertEqual(failing(run(with_field("element_set_no", lambda v: 10 ** 1000))), THREE)


    def test_a_list_subclass_of_copies_costs_what_it_holds(self):
        """Found while the reviewers' probes were run again on this mend, older: a list subclass is compared with what
        it holds by digest, and each comparison digested afresh all the reading below it, so records each holding a
        list subclass that hands back copies of the records before them cost the cube of the records (60 records, 37 s;
        250 did not end). Now each container is digested once in the reading. The twin: the same records in plain
        lists."""
        import time
        from gpconf import plain as _plain

        class Copies(list):
            def __iter__(self):
                return iter([dict(r) for r in list.__iter__(self)])
        for kind in (Copies, list):
            with self.subTest(kind=kind.__name__):
                recs = [{"norad_cat_id": i, "epoch": "2020-01-01T00:00:00", "mean_motion": "15.5"} for i in range(120)]
                for r in recs:
                    r["_peers"] = kind(dict(x) for x in recs)
                start = time.monotonic()
                out = _plain.answer(recs)
                self.assertLess(time.monotonic() - start, 30)
                self.assertEqual(len(out), 120)
                self.assertTrue(all(type(r) is dict for r in out))


def _shared(levels, wrap=0, make=lambda y: [y, y]):
    """A structure that shares its parts: 2 ** levels paths through levels + 1 parts, inside `wrap` single lists."""
    x = 1
    for _ in range(levels):
        x = make(x)
    for _ in range(wrap):
        x = [x]
    return x


def _raising(make):
    class R(Reference):
        def parse(self, raw, fmt):
            raise make()
    return R()


def _words(r):
    return [i.detail for c in r for i in r[c].items if i.status == "fail"]


def _late_filename(x):
    e = OSError(2, "gone", "f.tle")
    e.filename = x
    return e


class TheBoundarysNinthReading(unittest.TestCase):
    """The separate reviewer's ninth reading of D-337 (2026-10-16), and the owner's ruling on it: the mends, and a reading
    budget per answer, each route with its twin."""

    def test_an_exception_deeper_than_the_reading_or_keyed_by_a_shared_tuple_is_worded_in_bounded_time(self):
        """Finding 1, a hang the eighth mend made: Python's own words were used whenever the arguments' plain reading wrote
        short, but that reading stops at DEPTH and leaves out keys that are not text, so a shared list 33 lists deep, or a
        dict keyed by a shared tuple, was walked by Python as a tree. The twin: plain short arguments keep Python's
        words exactly."""
        import time
        for label, make in (("33 lists around a shared list", lambda: ValueError(_shared(26, wrap=33))),
                            ("a dict keyed by a shared tuple", lambda: ValueError({_shared(28, make=lambda y: (y, y)): 1})),
                            ("a list 100,000 deep", lambda: ValueError(_shared(0, wrap=100_000)))):
            with self.subTest(label=label):
                start = time.monotonic()
                words = _words(run(_raising(make), cases=["kvn-syntax-variants"]))
                self.assertLess(time.monotonic() - start, 30)
                self.assertTrue(any(w.startswith("parser raised ValueError: ") and "could not be read" not in w for w in words),
                                words[:2])
        words = _words(run(_raising(lambda: ValueError([1, [2, "three"]], {"k": 4.5})), cases=["kvn-syntax-variants"]))
        self.assertIn("parser raised ValueError: " + str(ValueError([1, [2, "three"]], {"k": 4.5})), words)

    def test_a_raised_digit_limit_does_not_stop_the_reading(self):
        """Finding 2, a hang the eighth mend made, for every parser: the check for an int too long to write built
        10 ** limit, so a limit raised to a hundred million stopped the reference's own run at its first integer. The
        twin: the same run under the default limit."""
        import time
        if not hasattr(sys, "set_int_max_str_digits"):
            self.skipTest("Python before 3.11 has no limit on the digits it writes")
        old = sys.get_int_max_str_digits()
        try:
            for limit in (100_000_000, 2_147_483_647):
                with self.subTest(limit=limit):
                    sys.set_int_max_str_digits(limit)
                    start = time.monotonic()
                    self.assertEqual(failing(run(Reference())), [])
                    self.assertLess(time.monotonic() - start, 60)
        finally:
            sys.set_int_max_str_digits(old)
        self.assertEqual(failing(run(Reference())), [])

    def test_an_integer_too_long_to_write_is_named_in_an_exceptions_words(self):
        """Finding 3, wording the eighth mend made: an exception holding such an integer read "its message could not be
        read", and the marker's repr leaked into written texts. The twin: an ordinary file name reads as Python writes
        it."""
        for make, want in ((lambda: ValueError([10 ** 5000]), "parser raised ValueError: [<an integer of "),
                           (lambda: KeyError((1, 10 ** 5000)), "parser raised KeyError: (1, <an integer of "),
                           (lambda: OSError(2, "gone", [10 ** 5000]),
                            "parser raised FileNotFoundError: (2, 'gone'); filename: [<an integer of ")):
            with self.subTest(want=want):
                words = _words(run(_raising(make), cases=["kvn-syntax-variants"]))
                self.assertTrue(any(w.startswith(want) for w in words), words[:2])
        words = _words(run(_raising(lambda: OSError(2, "gone", "f.tle")), cases=["kvn-syntax-variants"]))
        self.assertIn("parser raised FileNotFoundError: [Errno 2] gone: 'f.tle'", words)

    def test_a_long_leaf_shared_by_many_holders_is_copied_and_measured_once(self):
        """Findings 4 and 5, costs older in part: a long Decimal's length was measured, and a long subclass of str or
        bytes, a bytearray or numpy's str_ copied, once for every holder, every copy kept; and a text field holding one
        shared bytes was written once for every record. The twins: the same with a plain str."""
        import time
        import tracemalloc
        from decimal import Decimal
        from gpconf import plain as _plain
        from gpconf.runner import norm_record

        class Sub(str):
            pass
        leaves = {"Decimal": Decimal("7" * 1_000_000), "str subclass": Sub("x" * 1_000_000),
                  "bytearray": bytearray(b"y" * 1_000_000), "str (twin)": "z" * 1_000_000}
        try:
            import numpy
            leaves["numpy.str_"] = numpy.str_("w" * 1_000_000)
        except ImportError:
            pass
        for label, leaf in leaves.items():
            with self.subTest(leaf=label):
                n = 2000 if label == "Decimal" else 400   # a Decimal's cost was time: its length measured for each holder
                recs = [{"norad_cat_id": i, "_x": [leaf], "object_name": "n" if label == "Decimal" else leaf} for i in range(n)]
                tracemalloc.start()
                start = time.monotonic()
                out = _plain.answer(recs)
                for r in out:
                    norm_record(r)
                elapsed = time.monotonic() - start
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
                self.assertLess(elapsed, 5 if label == "Decimal" else 30)
                self.assertLess(peak, 60_000_000, f"{peak:,} bytes")   # one copy kept, not four hundred
                self.assertTrue(all(type(r) is dict for r in out))
        for label, leaf in (("bytes", b"q" * 1_000_000), ("Decimal", Decimal("8" * 1_000_000)), ("str (twin)", "s" * 1_000_000)):
            with self.subTest(text_field=label):
                tracemalloc.start()
                start = time.monotonic()
                for i in range(4000):   # its cost was time: the value written out for each record
                    norm_record({"norad_cat_id": i, "object_name": leaf})
                elapsed = time.monotonic() - start
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
                self.assertLess(elapsed, 1)
                self.assertLess(peak, 60_000_000, f"{peak:,} bytes")

    def test_a_parsers_own_bad_or_notes_key_is_not_the_runners(self):
        """Finding 6, a crash older than D-337: a record carrying a key `_bad` of the parser's own ended cases as "internal
        error in runner", and a `_notes` of its own was silently replaced. The twin: the same values under a key of no
        meaning."""
        for key in ("_bad", "_notes", "_mine"):
            for v in (None, "", "checksum", {"note": 1}, 0):
                with self.subTest(key=key, value=v):
                    r = run(every_record(lambda rec, key=key, v=v: dict(rec, **{key: v}), only=lambda rec: "_refused" not in rec))
                    self.assertEqual(failing(r), [])

    def test_an_oserror_or_syntaxerror_holding_a_shared_list_is_worded_in_bounded_time(self):
        """Finding 8, a hang older than the eighth mend: OSError's and SyntaxError's own __str__, not BaseException's,
        walked a shared file name or message as a tree, one set after the exception was made among them. The twin:
        plain parts keep Python's words."""
        import time
        for label, make in (("OSError", lambda: OSError(2, "gone", _shared(26))), ("SyntaxError", lambda: SyntaxError(_shared(26))),
                            ("a file name set afterwards", lambda: _late_filename(_shared(26)))):
            with self.subTest(label=label):
                start = time.monotonic()
                words = _words(run(_raising(make), cases=["kvn-syntax-variants"]))
                self.assertLess(time.monotonic() - start, 30)
                self.assertTrue(words and all("could not be read" not in w for w in words), words[:2])
        words = _words(run(_raising(lambda: SyntaxError("bad", ("f.py", 1, 2, "x = ("))), cases=["kvn-syntax-variants"]))
        self.assertIn("parser raised SyntaxError: bad (f.py, line 1)", words)

    def test_an_object_python_would_print_by_walking_what_it_holds_is_never_printed(self):
        """The ninth reading's (9), a stated limit before: a subclass of deque, a SimpleNamespace, a dict view, a slice or a
        UserList holding a shared list was its str(), which Python writes by walking what it holds as a tree. By the
        owner's ruling on the readings of the tenth reading's mend, Python never prints such an object: a container with
        a defined face (a subclass of deque, a dict view, a UserList) is read through it to plain values, and one with
        none (a SimpleNamespace, a slice) is written as its type's name. The twin: an object whose writing is the
        parser's own is its str()."""
        import collections
        import time
        import types
        from gpconf import plain as _plain

        class Held(collections.deque):
            pass

        class Own:
            def __init__(self, y):
                self.y = y

            def __repr__(self):
                return "Own(...)"
        x = _shared(26)
        faced = {"deque subclass": lambda y: Held([y]), "dict view": lambda y: {"k": y}.values(),
                 "UserList": lambda y: collections.UserList([y])}
        faceless = {"namespace": (lambda y: types.SimpleNamespace(a=y), "<SimpleNamespace object>"),
                    "slice": (lambda y: slice(y, y), "<slice object>")}
        for label, make in faced.items():
            with self.subTest(holder=label):
                start = time.monotonic()
                got = _plain.value(make(x))
                self.assertLess(time.monotonic() - start, 10)
                self.assertIs(type(got), list)
                self.assertTrue(_plain.is_plain(got))
                self.assertEqual(_plain.value(make([1, 2])), [[1, 2]])
        for label, (make, words) in faceless.items():
            with self.subTest(holder=label):
                start = time.monotonic()
                self.assertEqual(_plain.value(make(x)), words)
                self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(_plain.value(Own(x)), "Own(...)")

    def test_an_answer_past_the_reading_budget_fails_in_words(self):
        """The owner's addition on the ninth reading: a hard budget per answer, objects visited and bytes copied, hashed or
        written. An answer that never ends, or one past the budget, fails the file in those words, never a hang. The
        twins: the reference's own answers, which sit far below the budget."""
        import time
        from unittest import mock
        from gpconf import plain as _plain

        class Endless(Reference):
            def parse(self, raw, fmt):
                def records():
                    i = 0
                    while True:
                        i += 1
                        yield {"norad_cat_id": i}
                return records()
        start = time.monotonic()
        words = _words(run(Endless(), cases=["kvn-syntax-variants"]))
        self.assertLess(time.monotonic() - start, 300)
        self.assertTrue(any("the answer was too large or too deeply shared to read" in w for w in words), words[:2])
        with mock.patch.object(_plain, "BUDGET_OBJECTS", 5):
            words = _words(run(Reference(), cases=["kvn-syntax-variants"]))
        self.assertTrue(any("too large or too deeply shared to read (past the reading's budget of 5 objects" in w for w in words),
                        words[:2])
        _plain.READING_PEAK[:] = [0, 0]
        self.assertEqual(failing(run(Reference())), [])
        self.assertLess(_plain.READING_PEAK[0], _plain.BUDGET_OBJECTS // 20)
        self.assertLess(_plain.READING_PEAK[1], _plain.BUDGET_BYTES // 20)


class TheBoundarysTenthReading(unittest.TestCase):
    """The separate reviewer's tenth reading of D-337 (2026-10-16), the last, limited to the ninth reading's mend: what
    that mend made, each route with its twin."""

    def test_values_real_libraries_return_stay_far_below_the_budget(self):
        """Finding 1, a false fail the mend made: the count before Python's own writing walked an Enum member's whole class
        (its metaclass is no plain `type`), afresh for every read, so one Enum, UUID or Fraction field on every record of
        a large answer spent the budget and the file failed. No count is made now, and such an object is its type's
        name. The twin: the same records with plain texts."""
        import enum
        import fractions
        import time
        import uuid
        from gpconf import plain as _plain
        Owner = enum.Enum("Owner", {f"C{i}": i for i in range(5000)})
        ids = [uuid.UUID(int=i) for i in range(10)]
        for label, extra in (("Enum, UUID and Fraction fields", lambda i: {"_owner": Owner.C1, "_ids": ids[i % 10], "_r": fractions.Fraction(i, 7)}),
                             ("plain texts (twin)", lambda i: {"_owner": "Owner.C1", "_ids": str(ids[i % 10]), "_r": f"{i}/7"})):
            with self.subTest(fields=label):
                recs = [dict({"norad_cat_id": i, "epoch": "2026-01-01T00:00:00"}, **extra(i)) for i in range(12000)]
                _plain.READING_PEAK[:] = [0, 0]
                start = time.monotonic()
                out = _plain.answer(recs)
                self.assertLess(time.monotonic() - start, 20)
                self.assertIsNot(type(out), _plain.Problem, getattr(out, "what", ""))
                self.assertLess(_plain.READING_PEAK[0], _plain.BUDGET_OBJECTS // 10)
        self.assertEqual(_plain.value(Owner.C1), "<Owner object>")   # never printed by Python: its type's name

    def test_a_writing_made_by_exec_is_read(self):
        """Finding 2, a false fail the mend made: a __repr__ whose __module__ is None (made by exec() with globals that
        hold no __name__, as dataclasses does for a module loaded by path) raised AttributeError inside the reading, and
        the report blamed the parser. The twin: the same class with an ordinary __repr__."""
        namespace: dict = {}
        exec("def __repr__(self):\n    return 'Source(provider=celestrak)'\n", {}, namespace)
        Made = type("Made", (), {"__repr__": namespace["__repr__"]})
        self.assertIsNone(Made.__repr__.__module__)

        class Plain:
            def __repr__(self):
                return "Source(provider=celestrak)"
        for kind in (Made, Plain):
            with self.subTest(kind=kind.__name__):
                r = run(every_record(lambda rec, kind=kind: dict(rec, _source=kind()), only=lambda rec: "_refused" not in rec))
                self.assertEqual(failing(r), [])

    def test_exceptions_held_one_inside_another_are_worded_in_bounded_text(self):
        """Finding 3, a hang the mend made: an exception held in another's attribute was worded afresh at each level and
        its text quoted whole, so a chain of OSErrors grew fourfold a level (95.9 s and 3.7 GB at 30), and one that held
        itself filled memory. Now a held exception is read through the reading's memo, one that holds itself is a
        marker, and each part written from the arguments is cut at FIELD_TEXT with a digest. Measured on the guard's
        own words, not the report's, which cuts every detail at 200 characters. The twin: a plain file name keeps
        Python's words."""
        import time
        import tracemalloc
        from gpconf import plain as _plain

        def chain(n, both):
            e = OSError(2, "gone", "f.tle")
            for _ in range(n):
                outer = OSError(2, "gone")
                outer.filename = e
                if both:
                    outer.filename2 = e
                e = outer
            return e

        def itself():
            e = OSError(2, "gone", "f.tle")
            e.filename = e
            e.filename2 = e
            return e
        for label, make in (("a chain of 30", lambda: chain(30, False)), ("a chain of 30, two attributes", lambda: chain(30, True)),
                            ("one that holds itself", itself)):
            with self.subTest(label=label):
                e = make()
                tracemalloc.start()
                start = time.monotonic()
                words = _plain.exception_text(e)
                elapsed = time.monotonic() - start
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
                self.assertLess(elapsed, 5)
                self.assertLess(len(words), 10_000)
                self.assertLess(peak, 50_000_000, f"{peak:,} bytes")
        self.assertEqual(_plain.exception_text(OSError(2, "gone", "f.tle")), "[Errno 2] gone: 'f.tle'")

    def test_an_exception_held_deeper_than_the_reading_is_its_marker(self):
        """The marker for arguments deeper than the reading goes is written as itself, where it read "its message could not
        be read" (the reading of the tenth reading's mend asked for a test). The twin: a short chain reads as Python
        writes it."""
        from gpconf import plain as _plain

        def chain(n):
            e = ValueError("k")
            for _ in range(n):
                e = ValueError(e)
            return e
        words = _plain.exception_text(chain(20))
        self.assertNotIn("could not be read", words)
        self.assertIn("nested more than", words)
        self.assertEqual(_plain.exception_text(chain(3)), "k")

    def test_objects_holding_one_shared_list_end_within_the_budget(self):
        """Finding 4, a hang older than the mend: Python's own writing, or a count of what it would walk, met one shared
        list once for every namespace that held it, records times the list. Now such an object is never printed by Python
        and nothing is counted: it is its type's name. The twin: an object whose writing is the parser's own is its
        str()."""
        import time
        import types
        from gpconf import plain as _plain

        class Own:
            def __init__(self, rows):
                self.rows = rows

            def __repr__(self):
                return "Own(rows)"
        shared = [(1, 2)] * 4_000_000
        for label, make, words in (("a namespace", lambda: types.SimpleNamespace(rows=shared), "<SimpleNamespace object>"),
                                   ("the parser's own writing (twin)", lambda: Own(shared), "Own(rows)")):
            with self.subTest(holder=label):
                recs = [{"norad_cat_id": i, "_ns": make()} for i in range(500)]
                start = time.monotonic()
                out = _plain.answer(recs)
                self.assertLess(time.monotonic() - start, 5)
                self.assertIsNot(type(out), _plain.Problem, getattr(out, "what", ""))
                self.assertEqual(out[0]["_ns"], words)

    def test_a_group_and_a_unicode_error_keep_pythons_words(self):
        """Finding 5, wording the mend made: an ExceptionGroup lost Python's words, since the exceptions it holds are not
        plain, though its writing only counts them; a UnicodeError's start and end were named again after its arguments.
        And, from the reading of that mend: a group is told by its type, never through its own __class__, and its
        message is read from its own member."""
        import builtins
        from gpconf import plain as _plain
        group = getattr(builtins, "ExceptionGroup", None)   # Python 3.11 and later
        if group is not None:
            class Msg(str):
                pass
            with self.subTest(group="plain"):
                self.assertEqual(_plain.exception_text(group("errors", [ValueError("a")])), "errors (1 sub-exception)")
            with self.subTest(group="a message of a str subclass"):
                self.assertEqual(_plain.exception_text(group(Msg("errors"), [ValueError("a"), ValueError("b")])),
                                 "errors (2 sub-exceptions)")
        with self.subTest(unicode="plain"):
            e = UnicodeDecodeError("utf-8", b"x" * 400, 300, 301, "bad")
            self.assertEqual(_plain.exception_text(e), str(e))
        with self.subTest(unicode="a bytes subclass"):
            class Raw(bytes):
                pass
            words = _plain.exception_text(UnicodeDecodeError("utf-8", Raw(b"x" * 400), 300, 301, "bad"))
            self.assertTrue(words.startswith("('utf-8', b'xxx"), words[:40])
            self.assertNotIn("start:", words)
            self.assertNotIn("end:", words)

    def test_an_exceptions_own_class_is_not_asked(self):
        """From the reading of the tenth reading's mend, a false fail those lines made: the group test asked the exception
        its own __class__, the parser's code, which may raise. The twin: the same exception with an honest class."""
        class Liar(ValueError):
            @property
            def __class__(self):
                raise RuntimeError("asked")

        for kind in (Liar, ValueError):
            with self.subTest(kind=kind.__name__):
                r = run(every_record(lambda rec, kind=kind: dict(rec, _why=kind("b")), only=lambda rec: "_refused" not in rec))
                self.assertEqual(failing(r), [])


    def test_one_object_shared_by_every_record_is_written_once(self):
        """From the reading of the tenth reading's mend, a false fail older than it: one object Python writes (an
        argparse.Namespace of 4,000 entries, a dict's keys()), shared by every record, was counted and written again for
        each record, and the answer spent the budget. Now its text is kept for the reading, through a weak reference, or,
        for a type that has none, among the last HELD such objects. The twin: the same text as a plain str."""
        import argparse
        import time
        from gpconf import plain as _plain
        ns = argparse.Namespace(**{f"k{i}": "x" * 20 for i in range(4000)})
        keys = {f"k{i}": i for i in range(4000)}.keys()
        for label, shared in (("an argparse.Namespace", ns), ("a dict's keys()", keys), ("a plain str (twin)", str(ns))):
            with self.subTest(shared=label):
                start = time.monotonic()
                out = _plain.answer([{"norad_cat_id": i, "_x": shared} for i in range(12000)])
                self.assertLess(time.monotonic() - start, 20)
                self.assertIsNot(type(out), _plain.Problem, getattr(out, "what", ""))

    def test_a_count_made_inside_a_cycle_is_not_used_elsewhere(self):
        """From the reading of the tenth reading's mend, a hang those lines made: a count kept for the whole reading was
        made while a part met its holder again on its own path, and handed out where the holder was not on the path, so
        Python then wrote everything under it. No count is made now: such an object is its type's name. The twin: the
        part alone."""
        import time
        import types
        from gpconf import plain as _plain
        b = [1]
        for _ in range(30):
            b = [b, b]
        a = [b]
        x = types.SimpleNamespace(a=a)
        a.append(x)
        y = types.SimpleNamespace(L=a)
        class Own:   # the twin: the part under a writing of the parser's own, which is its code
            def __init__(self, a):
                self.a = a

            def __repr__(self):
                return "Own(a)"
        for label, recs, words in (("the holder first, then the part", [{"norad_cat_id": 1, "_y": y}, {"norad_cat_id": 2, "_x": x}],
                                    "<SimpleNamespace object>"),
                                   ("the parser's own writing (twin)", [{"norad_cat_id": 1, "_y": y}, {"norad_cat_id": 2, "_x": Own(a)}],
                                    "Own(a)")):
            with self.subTest(label=label):
                start = time.monotonic()
                out = _plain.answer(recs)
                self.assertLess(time.monotonic() - start, 5)
                self.assertEqual(out[-1]["_x"], words)

    def test_objects_made_afresh_for_each_read_are_not_kept_alive(self):
        """From the reading of the tenth reading's mend, a crash those lines made: the kept count held every object it
        counted until the answer was read, so a record type that makes a fresh array each time a field is read kept
        them all. The twin: one array shared by every row."""
        import tracemalloc
        from collections.abc import Mapping
        from gpconf import plain as _plain
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        shared = numpy.zeros(125_000)

        class Row(Mapping):
            def __init__(self, i, fresh):
                self.i, self.fresh = i, fresh

            def __getitem__(self, k):
                if k == "norad_cat_id":
                    return self.i
                if k == "_track":
                    return numpy.full(125_000, float(self.i)) if self.fresh else shared
                raise KeyError(k)

            def __iter__(self):
                return iter(("norad_cat_id", "_track"))

            def __len__(self):
                return 2
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                tracemalloc.start()
                out = _plain.answer([Row(i, fresh) for i in range(1000)])
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
                self.assertIsNot(type(out), _plain.Problem)
                self.assertLess(peak, 100_000_000, f"{peak:,} bytes")



class TheBoundarysTwelfthReading(unittest.TestCase):
    """The separate reviewer's reading of the fix to the tenth reading's mend (2026-10-16), and the owner's ruling on it:
    Python never prints an object it would print by walking what it holds. Each route with its twin."""

    FIELDS = ("object_name", "mean_motion", "epoch", "norad_cat_id")

    def test_a_container_with_a_face_in_a_graded_field_is_read_through_it(self):
        """The owner's premise test: a container that Python would print by walking it, sitting in a field a check reads,
        is read through its defined face to plain values, never written as its type's name; so no verdict can move. Each
        such container in each graded field fails or passes exactly as the same values in an exact list do (the
        twin)."""
        import collections
        from gpconf import plain as _plain

        class Held(collections.deque):
            pass

        class Bag(set):
            pass
        makers = {"a subclass of deque": Held, "a subclass of set": Bag, "a UserList": collections.UserList,
                  "a dict's values()": lambda xs: {i: x for i, x in enumerate(xs)}.values()}
        for field in self.FIELDS:
            for label, make in makers.items():
                with self.subTest(field=field, container=label):
                    rec = _plain.answer([{"norad_cat_id": 1, field: make(["15.5"])}])[0]
                    self.assertIs(type(rec[field]), _plain.Written)
                    self.assertEqual(rec[field].kind, "list")
                    self.assertNotIn("object>", rec[field])
                    got = failing(run(with_field(field, lambda v, make=make: make([v]))))
                    twin = failing(run(with_field(field, lambda v: [v])))
                    self.assertEqual(got, twin)

    def test_an_object_with_no_face_in_a_graded_field_moves_no_verdict(self):
        """The other half of the owner's premise: an object with no face (a namespace, a slice) in a field a check reads is
        written as its type's name, and fails exactly where Python's own writing of it did (the twin: the same field
        holding that writing as a text); no correct value is such an object."""
        import types
        for field in self.FIELDS:
            for label, make in (("a namespace", lambda v: types.SimpleNamespace(value=v)), ("a slice", lambda v: slice(v, None))):
                with self.subTest(field=field, holder=label):
                    got = failing(run(with_field(field, make)))
                    twin = failing(run(with_field(field, lambda v, make=make: str(make(v)))))
                    self.assertEqual(got, twin)

    def test_a_cycle_inside_one_writing_is_never_walked(self):
        """Finding 1, older: inside one count, a part counted while its holder was on the path was reused where it was not,
        and Python wrote the holder whole (16,875,507 characters at 14 levels). Nothing is counted or printed now. The
        twin: the same shape, small."""
        import time
        import types
        from gpconf import plain as _plain

        def shape(k, leaf):
            r = [leaf]
            for _ in range(k):
                h = [None, r]
                part = [h]
                h[0] = part
                r = [part, h]
            return types.SimpleNamespace(r=r)
        class Own:   # the twin: the same shape under a writing of the parser's own, which is its code
            def __init__(self, r):
                self.r = r

            def __repr__(self):
                return "Own(r)"
        start = time.monotonic()
        self.assertEqual(_plain.value(shape(24, "x" * 1000)), "<SimpleNamespace object>")
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(_plain.value(Own(shape(24, "x").r)), "Own(r)")

    def test_one_table_shared_by_every_record_costs_nothing_per_record(self):
        """Finding 2, a false fail the fix made: a count paid for a shared table once for each record's own namespace, so
        450 entries on every record of a large answer spent the budget. Nothing is counted now. The twin: the same
        records with a plain text."""
        import types
        from gpconf import plain as _plain
        table = {f"k{i}": f"v{i}" for i in range(5000)}
        for label, make in (("a namespace", lambda: types.SimpleNamespace(**table)), ("a dict's values() (read)", lambda: table.values()),
                            ("a plain text (twin)", lambda: "table")):
            with self.subTest(holder=label):
                out = _plain.answer([{"norad_cat_id": i, "_t": make()} for i in range(12000)])
                self.assertIsNot(type(out), _plain.Problem, getattr(out, "what", ""))

    def test_a_large_leaf_is_its_type_name(self):
        """A leaf that holds more than LEAF_BYTES itself (an array.array) is its type's name: Python's writing of it was
        as long as it is (297 MB). numpy's arrays are numpy's own writing, a short summary, and are not named. The twin: a
        small array is Python's writing."""
        import array
        from gpconf import plain as _plain
        self.assertEqual(_plain.value(array.array("d", [0.0]) * 200_000), "<array object>")
        self.assertEqual(_plain.value(array.array("d", [1.0, 2.0])), "array('d', [1.0, 2.0])")



class TheBoundarysThirteenthReading(unittest.TestCase):
    """The separate reviewer's last reading of D-337 (2026-10-16), limited to the type-name rule: what it found, each route
    with its twin."""

    def test_a_libraries_own_compiled_writing_is_its_text(self):
        """Finding 1, a false fail the rule made, on a type a real library returns: lxml.objectify's elements, which a thin
        OMM-XML adapter hands back, have a compiled __str__ of lxml's own, and were taken as Python's writing and named;
        mean_motion, the epoch and the name then failed three cases. A writing is Python's own now only when its type is
        a builtin or standard-library one. The twin: the same values as plain texts."""
        try:
            from lxml import objectify
        except ImportError:
            self.skipTest("lxml is not installed")

        def element(text):
            return getattr(objectify.fromstring(f"<r><v>{text}</v></r>".encode()), "v")
        for field in ("mean_motion", "epoch", "object_name", "eccentricity", "bstar"):
            with self.subTest(field=field):
                got = failing(run(with_field(field, lambda v: element(v if type(v) is str else str(v)))))
                twin = failing(run(with_field(field, lambda v: v if type(v) is str else str(v))))
                self.assertEqual(got, twin)

    def test_a_standard_library_value_in_a_graded_field_is_named_a_stated_limit(self):
        """Finding 2, a false fail on standard-library types, ruled not blocking: Fraction(0) as a derivative is its type's
        name, and fails where Python's writing would read "0". The fix that kept Python's writing for an object whose parts
        hold nothing further opened four hangs (the reading of that fix), and was taken out: this is a stated limit, and
        this test holds it, so that a change to it is seen. The twin: the plain text "0" passes."""
        import fractions
        from decimal import Decimal

        def zero(v):
            return Decimal(str(v)) == 0
        self.assertNotEqual(failing(run(with_field("mean_motion_ddot", lambda v: fractions.Fraction(0) if zero(v) else v))), [])
        self.assertEqual(failing(run(with_field("mean_motion_ddot", lambda v: "0" if zero(v) else v))), [])

    def test_the_faced_containers_read_as_their_face_says(self):
        """From the same reading, untested pieces: a UserString in a field the checks read is its text; a subclass of
        frozenset reads in an order of its own; two equal keys or items views of dicts built in other orders read alike;
        two view kinds of one dict each read their own face. The twins: the plain values."""
        import collections
        from gpconf import plain as _plain

        class Frozen(frozenset):
            pass
        self.assertEqual(failing(run(with_field("object_name", lambda v: collections.UserString(v)))),
                         failing(run(with_field("object_name", lambda v: v))))
        self.assertEqual(_plain.value(Frozen({"b", "a"})), _plain.value(Frozen({"a", "b"})))
        first, second = {"a": 1, "b": 2}, {"b": 2, "a": 1}
        self.assertEqual(_plain.value(first.keys()), _plain.value(second.keys()))
        self.assertEqual(_plain.value(first.items()), _plain.value(second.items()))
        both = _plain.answer([{"norad_cat_id": 1, "_k": first.keys(), "_v": first.values()}])[0]
        self.assertEqual((str.__str__(both["_k"]), str.__str__(both["_v"])), ("['a', 'b']", "[1, 2]"))



class TheBoundarysFourteenthReading(unittest.TestCase):
    """The separate reviewer's reading of the fix to the last reading (2026-10-16): three hangs that fix's second rule
    made (an object whose parts hold nothing further kept Python's writing), taken out, and one on Python 3.9 its first
    rule made. Each route with its twin."""

    def test_a_compiled_in_standard_library_writing_is_pythons_own_on_every_version(self):
        """Finding 1, a hang on 3.9: a module compiled into the interpreter (itertools, _io) has no file, so it was not
        taken for the standard library there, and Python printed itertools.repeat of a shared list as a tree. The twin: a
        writing of the parser's own is its code."""
        import itertools
        import time
        from gpconf import plain as _plain

        class Own:
            def __init__(self, x):
                self.x = x

            def __repr__(self):
                return "Own(x)"
        x = _shared(26)
        start = time.monotonic()
        self.assertEqual(_plain.value(itertools.repeat(x, 1)), "<repeat object>")
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(_plain.value(Own(x)), "Own(x)")

    def test_a_part_gc_does_not_show_is_never_printed(self):
        """Findings 2 to 4, hangs: an object whose parts held nothing further by gc kept Python's writing, but gc does not
        show a datetime's time zone, a part of few bytes can be a long int, and asking each part what it holds cost a
        shared table's length for every record. Any object holding another besides its class is named again. The twins:
        the same values held by a writing of the parser's own, which is its code."""
        import datetime
        import time
        from gpconf import plain as _plain

        class Own:
            def __init__(self, x):
                self.x = x

            def __repr__(self):
                return "Own(...)"

        class Zone(datetime.tzinfo):   # a time zone whose name is a shared list: gc does not show a datetime's zone
            def __init__(self, key):
                self.key = key

            def utcoffset(self, when):
                return datetime.timedelta(0)

            def tzname(self, when):
                return "UTC"

            def __repr__(self):
                return repr(self.key)
        when = datetime.datetime(2008, 9, 20, tzinfo=Zone(_shared(26)))
        table = list(range(1_000_000))
        big = 10 ** 4000 * 3
        for label, held, make in (("a slice of a datetime in a zone that holds a shared list", when, slice),
                                  ("a slice of a long int", big, slice),
                                  ("a slice of a shared table", table, slice),
                                  ("an argparse.Namespace of a shared table", table,
                                   lambda x: __import__("argparse").Namespace(table=x))):
            for holder, want in ((make, None), (Own, "Own(...)")):
                with self.subTest(holder=label if want is None else f"{label}, held by the parser's own writing"):
                    start = time.monotonic()
                    out = _plain.answer([{"norad_cat_id": i, "_x": holder(held)} for i in range(3000)])
                    self.assertLess(time.monotonic() - start, 10)
                    self.assertIsNot(type(out), _plain.Problem)
                    if want is None:
                        self.assertTrue(out[0]["_x"].endswith(" object>"), out[0]["_x"])
                    else:
                        self.assertEqual(out[0]["_x"], want)


class ARaiseOnTheComparisonFileFailsAsParse(unittest.TestCase):
    """Round one's finding 6 on D-330 (D-334), ruled by the owner (2026-10-15): a parser that raised on the corrupt-input
    case's unedited comparison file had the case's checks set aside, not failed, so a silent dropper that also raised
    there read "not-exercised" where its twin failed. A raise on that file, a valid file of its format, fails it as
    `parse`, as on any other valid file (D-339). The twins: the same dropper reading the comparison files fails as
    before; a correct parser reading them passes; a raise on a corrupt input is still that file refused as a whole."""

    def test_a_dropper_that_raises_on_the_comparison_files_fails(self):
        class RaisesOnTheComparisonFiles(Dropper):
            def parse(self, raw, fmt):
                if raw in UNEDITED:
                    raise ValueError("not this one")
                return super().parse(raw, fmt)
        r = run(RaisesOnTheComparisonFiles(), cases=["corrupt-input"])
        self.assertEqual(failing(r), ["corrupt-input"])
        parse = [i for i in r["corrupt-input"].items if i.check == "parse" and i.status == "fail"]
        self.assertEqual(sorted(os.path.basename(i.file or "") for i in parse),
                         ["unedited-array.json", "unedited-rows.csv", "unedited-sets.tle"])
        for i in parse:
            self.assertIn("parser raised ValueError: not this one", i.detail)
        self.assertEqual(failing(run(Dropper(), cases=["corrupt-input"])), ["corrupt-input"])   # the same bug, read normally

    def test_a_correct_parser_fails_only_when_it_raises_on_a_comparison_file(self):
        class RaisesOnOneComparisonFile(Reference):
            def parse(self, raw, fmt):
                if raw in UNEDITED and fmt == "tle":
                    raise ValueError("not this one")
                return super().parse(raw, fmt)
        r = run(RaisesOnOneComparisonFile(), cases=["corrupt-input"])
        self.assertEqual(failing(r), ["corrupt-input"])
        self.assertEqual([os.path.basename(i.file or "") for i in r["corrupt-input"].items if i.status == "fail"],
                         ["unedited-sets.tle"])
        self.assertEqual(failing(run(Reference(), cases=["corrupt-input"])), [])

    def test_a_raise_on_a_corrupt_input_is_still_the_file_refused_as_a_whole(self):
        cut = {open(os.path.join(ROOT, "derived", "corrupt-input", n), "rb").read()
               for n in ("c5-cut-last-row.csv", "c5-cut-closing-bracket.json")}

        class RaisesOnTheCutFiles(Reference):
            def parse(self, raw, fmt):
                if raw in cut:
                    raise ValueError("cut short")
                return super().parse(raw, fmt)
        r = run(RaisesOnTheCutFiles(), cases=["corrupt-input"])
        self.assertEqual(failing(r), [])
        self.assertEqual([i for i in r["corrupt-input"].items if i.check == "parse"], [])


if __name__ == "__main__":
    unittest.main()
