import datetime
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backup_core as core  # noqa: E402


def make_tree(root):
    os.makedirs(os.path.join(root, "sub"))
    for rel, text in (("a.txt", "hello"), ("sub/b.txt", "world")):
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write(text)


class BackupCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "내 원본")
        self.dst = os.path.join(self.tmp.name, "dst")
        make_tree(self.src)
        os.makedirs(self.dst)
        self.when = datetime.datetime(2026, 10, 29, 9, 5, 16)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_creates_named_copy_without_partial(self):
        name = core.run_backup(self.src, self.dst, threading.Event(), self.when)
        self.assertEqual(name, "내 원본_20261029_090516")
        self.assertEqual(os.listdir(self.dst), [name])
        with open(os.path.join(self.dst, name, "sub", "b.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "world")

    def test_cancel_before_start_leaves_nothing(self):
        ev = threading.Event()
        ev.set()
        with self.assertRaises(core.Cancelled):
            core.run_backup(self.src, self.dst, ev, self.when)
        self.assertEqual(os.listdir(self.dst), [])

    def test_cancel_mid_copy_removes_the_partial_backup(self):
        ev = threading.Event()
        original = core.shutil.copy2
        calls = []

        def cancelling_copy(s, d):
            calls.append(s)
            result = original(s, d)
            ev.set()  # the user presses stop after the first file
            return result

        core.shutil.copy2 = cancelling_copy
        try:
            with self.assertRaises(core.Cancelled):
                core.run_backup(self.src, self.dst, ev, self.when)
        finally:
            core.shutil.copy2 = original
        self.assertEqual(len(calls), 1)                   # it stopped, it did not copy everything
        self.assertEqual(os.listdir(self.dst), [])        # and left no half-finished backup

    def test_failure_leaves_nothing_behind(self):
        original = core.shutil.copy2

        def failing_copy(s, d):
            raise PermissionError("denied")

        core.shutil.copy2 = failing_copy
        try:
            with self.assertRaises(Exception):
                core.run_backup(self.src, self.dst, threading.Event(), self.when)
        finally:
            core.shutil.copy2 = original
        self.assertEqual(os.listdir(self.dst), [])

    def test_existing_backup_is_never_overwritten(self):
        core.run_backup(self.src, self.dst, threading.Event(), self.when)
        with self.assertRaises(FileExistsError):
            core.run_backup(self.src, self.dst, threading.Event(), self.when)

    def test_prune_keeps_newest_and_ignores_other_folders(self):
        for n in ("20240101_000001", "20240101_000002", "20240101_000003"):
            os.makedirs(os.path.join(self.dst, f"내 원본_{n}"))
        os.makedirs(os.path.join(self.dst, "other_20240101_000001"))
        os.makedirs(os.path.join(self.dst, "내 원본_20240101_000009.partial"))
        deleted, failed = core.prune(self.dst, "내 원본", 2)
        self.assertEqual(deleted, ["내 원본_20240101_000001"])
        self.assertEqual(failed, [])
        self.assertEqual(sorted(os.listdir(self.dst)),
                         ["other_20240101_000001", "내 원본_20240101_000002",
                          "내 원본_20240101_000003", "내 원본_20240101_000009.partial"])

    def test_prune_zero_means_unlimited(self):
        os.makedirs(os.path.join(self.dst, "내 원본_20240101_000001"))
        self.assertEqual(core.prune(self.dst, "내 원본", 0), ([], []))

    def test_readable_size(self):
        self.assertEqual(core.readable_size(31), "31.0 B")
        self.assertEqual(core.readable_size(1536), "1.5 KB")


if __name__ == "__main__":
    unittest.main()
