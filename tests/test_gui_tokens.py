import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gui-tauri", "scripts"))
import gen_tokens  # noqa: E402


class GeneratedTokens(unittest.TestCase):
    def test_tokens_css_is_up_to_date(self):
        with open(gen_tokens.OUT, encoding="utf-8") as f:
            self.assertEqual(f.read(), gen_tokens.render(),
                             "design_tokens.py 가 바뀌었습니다: python gui-tauri/scripts/gen_tokens.py 를 실행하세요")

    def test_both_themes_are_emitted(self):
        css = gen_tokens.render()
        self.assertIn(":root {", css)
        self.assertIn(".dark {", css)
        self.assertIn("--primary-active:", css)


if __name__ == "__main__":
    unittest.main()
