import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import design_tokens as dt  # noqa: E402

SRC = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()


class TokenRules(unittest.TestCase):
    def test_text_contrast_meets_wcag_aa_in_both_themes(self):
        for theme in dt.THEMES:
            colors = dt.theme_colors(theme)
            for fg, bg, where in dt.TEXT_PAIRS:
                ratio = dt.contrast_ratio(colors[fg], colors[bg])
                self.assertGreaterEqual(ratio, 4.5, f"[{theme}] {fg} on {bg} ({where}) = {ratio:.2f}")

    def test_themes_define_the_same_roles(self):
        self.assertEqual(set(dt.THEMES["light"]), set(dt.THEMES["dark"]))

    def test_dark_text_is_not_pure_white(self):
        self.assertNotEqual(dt.theme_colors("dark")["text"], dt.COLOR["white"])

    def test_cards_are_distinguishable_from_the_page(self):
        for theme in dt.THEMES:
            c = dt.theme_colors(theme)
            self.assertNotEqual(c["card"], c["page"])
            self.assertNotEqual(c["border"], c["card"])

    def test_focus_ring_is_visible_against_its_surface(self):
        for theme in dt.THEMES:
            c = dt.theme_colors(theme)
            self.assertGreaterEqual(dt.contrast_ratio(c["ring"], c["card"]), 3.0)
            # the ring is the outer edge of the button, so it must stand out from the card it sits on
            self.assertGreaterEqual(dt.contrast_ratio(c["ring_on_primary"], c["card"]), 3.0)

    def test_known_failures_are_not_used_for_text(self):
        # these fail AA as text; they are only allowed for dots / bars, never as a text role
        for theme in dt.THEMES:
            for role in ("text", "text_sub", "on_primary", "success", "error", "warn"):
                self.assertNotIn(dt.THEMES[theme][role], ("emerald_600", "amber_500", "rose_600"))

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

    def test_uses_roles_not_palette_names(self):
        self.assertEqual(re.findall(r'"(?:slate|brand|emerald|rose|amber)_\d+"|"white"', SRC), [])

    def test_declares_design_system_version(self):
        self.assertIn("Design System v1.0 Applied", SRC)


if __name__ == "__main__":
    unittest.main()
