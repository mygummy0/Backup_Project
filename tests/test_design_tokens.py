import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import design_tokens as dt  # noqa: E402

SRC = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()


class TokenRules(unittest.TestCase):
    def test_text_contrast_meets_wcag_aa(self):
        for fg, bg, where in dt.TEXT_PAIRS:
            ratio = dt.contrast_ratio(dt.COLOR[fg], dt.COLOR[bg])
            self.assertGreaterEqual(ratio, 4.5, f"{fg} on {bg} ({where}) = {ratio:.2f}")

    def test_known_failures_are_not_used_for_text(self):
        # these fail AA as text; they are only allowed for dots / bars, never in TEXT_PAIRS
        for fg, _bg, _ in dt.TEXT_PAIRS:
            self.assertNotIn(fg, ("emerald_600", "amber_500", "rose_600"))

    def test_spacing_is_on_the_8px_grid_scale(self):
        self.assertEqual(sorted(dt.SPACE.values()), [4, 8, 16, 24, 32, 64])

    def test_control_height_is_multiple_of_8(self):
        self.assertEqual(dt.CONTROL_HEIGHT % 8, 0)

    def test_ease_out_curve(self):
        f = dt.ease_out
        self.assertEqual((f(0), f(1)), (0.0, 1.0))
        self.assertGreater(f(0.5), 0.5)                      # ease-out is front-loaded, not linear
        samples = [f(i / 20) for i in range(21)]
        self.assertEqual(samples, sorted(samples))           # monotonic

    def test_lerp_endpoints(self):
        self.assertEqual(dt.lerp_color("#000000", "#FFFFFF", 0), "#000000")
        self.assertEqual(dt.lerp_color("#000000", "#FFFFFF", 1), "#FFFFFF")


class SourceRules(unittest.TestCase):
    """main.py may only use tokens: no literal colours, no ad-hoc font sizes, no emoji."""

    def test_no_hex_literals(self):
        self.assertEqual(re.findall(r'"#[0-9A-Fa-f]{3,8}"', SRC), [])

    def test_no_literal_font_sizes(self):
        self.assertEqual(re.findall(r"\bsize\s*=\s*\d+", SRC), [])

    def test_no_emoji(self):
        emoji = re.findall("[\U0001F300-\U0001FAFF☀-➿️]", SRC)
        self.assertEqual(emoji, [])

    def test_no_linear_transition(self):
        self.assertNotIn("linear", SRC.lower())

    def test_declares_design_system_version(self):
        self.assertIn("Design System v1.0 Applied", SRC)


if __name__ == "__main__":
    unittest.main()
