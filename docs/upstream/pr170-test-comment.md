# Comment posted on brandon-rhodes/python-sgp4 PR #170

Status: **posted 2026-09-21 from the owner's account, verbatim, with the owner's explicit authorisation
(D-091):** https://github.com/brandon-rhodes/python-sgp4/pull/170#issuecomment-5755703491. Drafted and
revised the same day (D-089, D-090); results from D-088. Everything below the rule is the posted text.
---

Thanks for picking this up. I tested the PR at commit 5e4f308 against a conformance corpus for the
2026 catalog-number migration (https://github.com/hneogy/gp-omm-conformance), on Python 3.14.4 with
both the accelerated and the pure-Python `Satrec`.

The two new tests are useful and target the defect exactly. One thing worth flagging: at this
commit, the `omm.initialize` change from the first commit is no longer present (the second commit's
message says it was removed for C++ accelerated compatibility), so the tests are currently the only
change.

Because both tests skip when `api.accelerated` is true, a green CI run on the accelerated build
would not show whether the nine-digit case loads.

What I saw at 5e4f308:

- The CCSDS 502.0-B-3 annex G example OMM with `NORAD_CAT_ID` 799501621 still raises
  `ValueError: satellite number cannot exceed 339999` on both builds, as in 2.27.
- On the pure-Python build, both new tests fail with that error.
- The corpus's 16 cases give the same results as 2.27: no fixes, no regressions.

Happy to test any follow-up commit against live nine-digit data and the corpus.
