"""gui-tauri/src 의 tsx/ts 가 디자인 룰(Design System v1.0)을 지키는지 정적으로 검사한다.

- 앱 코드(src/*.tsx, components/*.tsx, hooks, lib): 간격·글자·모서리·색·이모지·임의값 전부 검사
- components/ui/ (shadcn 이식본): 글자 크기·색·이모지·모서리만 검사 (내부 패딩은 라이브러리 구조를 따른다)
"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "gui-tauri", "src")

ALLOWED_SPACING = {"0", "1", "2", "4", "6", "8", "16"}
ALLOWED_TEXT_SIZES = {"xs", "sm", "base", "xl", "2xl", "4xl"}
ALLOWED_RADIUS = {"lg", "xl", "full", "none"}

SPACING = re.compile(r"(?<![\w-])-?(?:p|px|py|pt|pb|pl|pr|ps|pe|m|mx|my|mt|mb|ml|mr|ms|me|gap|gap-x|gap-y|space-x|space-y)-(\d+(?:\.\d+)?)(?![\w.])")
TEXT_SIZE = re.compile(r"(?<![\w-])text-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)(?![\w-])")
RADIUS = re.compile(r"(?<![\w-])rounded(?:-[trbl]{1,2})?-(none|xs|sm|md|lg|xl|2xl|3xl|full)(?![\w-])")
ARBITRARY = re.compile(r"(?<![\w-])[a-z-]+-\[\d+(?:\.\d+)?(?:px|rem|em)\]")
RAW_COLOR = re.compile(r"(?<![\w-])(?:bg|text|border|ring|fill|stroke|from|to|via|outline|divide|shadow)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|black|white)(?:-\d{2,3})?(?![\w-])")
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")
WEIGHT = re.compile(r"(?<![\w-])font-(thin|extralight|light|medium|semibold|bold|extrabold|black)(?![\w-])")
SHADOW = re.compile(r"(?<![\w-])shadow-(xs|sm|md|lg|xl|2xl|inner)(?![\w-])")
GRADIENT = re.compile(r"(?<![\w-])(?:bg-gradient-to-\w+|bg-linear-\w+|bg-radial|bg-conic|(?:from|via|to)-[\w/\[\]-]+)")
SCALE_HOVER = re.compile(r"(?:hover|active|focus|group-hover):scale-")
DURATION = re.compile(r"(?<![\w-])duration-(\d+)(?![\w-])")
LINEAR = re.compile(r"ease-linear|transition-timing-function:\s*linear|\blinear\(")


def files(pattern_dirs, skip_ui):
    out = []
    for ext in ("tsx", "ts"):
        for path in glob.glob(os.path.join(SRC, "**", f"*.{ext}"), recursive=True):
            is_ui = os.sep + os.path.join("components", "ui") + os.sep in path
            if is_ui == (not skip_ui):
                out.append(path)
    return sorted(out)


def rel(path):
    return os.path.relpath(path, ROOT)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def scan(path, regex, bad):
    text = read(path)
    return [f"{rel(path)}: {m.group(0)}" for m in regex.finditer(text) if bad(m)]


APP = files(None, skip_ui=True)
VENDORED = files(None, skip_ui=False)


class AppCode(unittest.TestCase):
    def assertNone(self, found, hint):
        self.assertEqual(found, [], hint + "\n  " + "\n  ".join(found))

    def test_there_is_app_code_to_check(self):
        self.assertGreater(len(APP), 5)

    def test_spacing_scale(self):
        found = [v for p in APP for v in scan(p, SPACING, lambda m: m.group(1) not in ALLOWED_SPACING)]
        self.assertNone(found, "간격은 1/2/4/6/8/16 (4/8/16/24/32/64px)만 허용")

    def test_text_sizes(self):
        found = [v for p in APP + VENDORED for v in scan(p, TEXT_SIZE, lambda m: m.group(1) not in ALLOWED_TEXT_SIZES)]
        self.assertNone(found, "글자 크기는 xs/sm/base/xl/2xl/4xl만 허용")

    def test_radius(self):
        found = [v for p in APP for v in scan(p, RADIUS, lambda m: m.group(1) not in ALLOWED_RADIUS)]
        self.assertNone(found, "모서리는 컨트롤 rounded-lg(8px), 카드 rounded-xl(12px)")

    def test_no_arbitrary_pixel_values(self):
        found = [v for p in APP for v in scan(p, ARBITRARY, lambda m: True)]
        self.assertNone(found, "임의 px/rem 값 금지")

    def test_semantic_colors_only(self):
        found = [v for p in APP + VENDORED for v in scan(p, RAW_COLOR, lambda m: True)]
        self.assertNone(found, "원색 클래스 금지: bg-primary, text-muted-foreground 같은 의미 토큰만 사용")

    def test_no_hex_literals(self):
        found = [v for p in APP + VENDORED for v in scan(p, HEX, lambda m: True)]
        self.assertNone(found, "색은 tokens.css 의 변수로만")

    def test_no_emoji_and_no_linear_motion(self):
        found = [v for p in APP + VENDORED for v in scan(p, EMOJI, lambda m: True)]
        self.assertNone(found, "이모지 금지")
        found = [v for p in APP + VENDORED for v in scan(p, LINEAR, lambda m: True)]
        self.assertNone(found, "linear 전환 금지")

    def test_single_weight_only(self):
        found = [v for p in APP + VENDORED for v in scan(p, WEIGHT, lambda m: True)]
        self.assertNone(found, "Server Mono는 단일 굵기(400): font-normal만 허용, 위계는 크기와 색으로")

    def test_anti_slop_no_blurry_shadows(self):
        found = [v for p in APP + VENDORED for v in scan(p, SHADOW, lambda m: True)]
        self.assertNone(found, "번지는 그림자 금지: 선명한 얇은 테두리(border-border/60)를 쓴다")

    def test_anti_slop_no_gradients_and_no_hover_scale(self):
        found = [v for p in APP + VENDORED for v in scan(p, GRADIENT, lambda m: True)]
        self.assertNone(found, "그라디언트 금지")
        found = [v for p in APP + VENDORED for v in scan(p, SCALE_HOVER, lambda m: True)]
        self.assertNone(found, "hover 확대 금지")

    def test_anti_slop_transitions_are_300ms(self):
        found = [v for p in APP + VENDORED for v in scan(p, DURATION, lambda m: m.group(1) != "300")]
        self.assertNone(found, "전환은 duration-300 ease-out")

    def test_declares_design_system_version(self):
        for name in ("App.tsx", "components/FolderField.tsx", "components/LogPanel.tsx",
                     "components/OptionSelect.tsx", "components/BusyBar.tsx", "components/SettingsDialog.tsx"):
            text = read(os.path.join(SRC, name))
            self.assertIn("Design System v1.0 Applied", text, name)
            self.assertIn("Anti-Slop Rules Applied", text, name)


class Typography(unittest.TestCase):
    tokens = read(os.path.join(SRC, "tokens.css"))
    css = read(os.path.join(SRC, "index.css")) + tokens

    def test_pretendard_is_bundled_and_generic_fonts_are_banned(self):
        self.assertIn("pretendard", self.css.lower())
        for banned in ("Inter", "Roboto", "Open Sans"):
            self.assertIsNone(re.search(rf"[\"' ]{banned}[\"',]", self.css), banned)

    def test_server_mono_leads_the_stack_and_is_bundled(self):
        stack = re.search(r"--font-sans:\s*([^;]+);", self.tokens).group(1)
        self.assertTrue(stack.startswith("ServerMono"), stack)
        self.assertLess(stack.index("ServerMono"), stack.index("Pretendard"))  # Hangul falls through to Pretendard
        self.assertIn('font-family: "ServerMono"', self.css)
        for name in ("ServerMono-Regular.woff2", "ServerMono-OFL.md"):  # font + its SIL OFL licence ship together
            self.assertTrue(os.path.exists(os.path.join(SRC, "fonts", name)), name)

    def test_no_synthesised_weights_and_no_jetbrains(self):
        self.assertIn("font-synthesis: none", self.css)
        self.assertNotIn("jetbrains", self.css.lower())

    def test_buttons_have_no_focus_halo(self):
        button = read(os.path.join(SRC, "components", "ui", "button.tsx"))
        self.assertNotIn("ring-", button)  # no ring/halo classes at all (outline only, keyboard focus only)
        self.assertIn("focus-visible:outline-2", button)

    def test_korean_letter_spacing_and_line_height(self):
        self.assertIn("--letter-spacing: -0.02em", self.css)
        match = re.search(r"--line-height:\s*([\d.]+)", self.css)
        self.assertTrue(match and 1.5 <= float(match.group(1)) <= 1.6)

    def test_heading_levels_do_not_skip(self):
        text = "".join(read(p) for p in APP if p.endswith(".tsx"))
        self.assertEqual(len(re.findall(r"<h1[ >]", text)), 1)
        self.assertGreaterEqual(len(re.findall(r"<h2[ >]", text)), 3)
        self.assertEqual(re.findall(r"<h[3-6][ >]", text), [])


class Copy(unittest.TestCase):
    def test_all_visible_korean_text_lives_in_copy_ts(self):
        hangul = re.compile(r"[가-힣]")
        offenders = []
        for path in APP:
            if path.endswith(tuple(os.path.join("lib", n) for n in ("copy.ts", "backend.ts", "format.ts"))):
                continue  # backend.ts: 브라우저 미리보기용 목 데이터, format.ts: 엔진 로그 문구를 인식하는 패턴
            for n, line in enumerate(read(path).splitlines(), 1):
                code = re.sub(r"//.*$|/\*.*?\*/", "", line)  # 주석은 허용
                if hangul.search(code.strip().lstrip("* ")) and not line.strip().startswith(("*", "/*", "//")):
                    offenders.append(f"{rel(path)}:{n}: {line.strip()[:70]}")
        self.assertEqual(offenders, [], "UI 문구는 lib/copy.ts 로:\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
