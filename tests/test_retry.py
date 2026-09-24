"""重试助手单测（内核源码 502 那次事故的回归网）。"""

from __future__ import annotations

import unittest

from kbx.pipeline import retry


class RetryTests(unittest.TestCase):
    def test_succeeds_after_failures(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("模拟 502")
            return "ok"

        self.assertEqual(retry(flaky, attempts=3, base_delay=0), "ok")
        self.assertEqual(calls["n"], 3)

    def test_raises_last_error(self):
        def always_fail():
            raise RuntimeError("一直是 502")

        with self.assertRaises(RuntimeError) as ctx:
            retry(always_fail, attempts=2, base_delay=0)
        self.assertIn("502", str(ctx.exception))

    def test_single_attempt_no_sleep(self):
        calls = {"n": 0}

        def once():
            calls["n"] += 1
            return 42

        self.assertEqual(retry(once, attempts=1, base_delay=0), 42)
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
