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

    def test_declares_design_system_version(self):
        for name in ("App.tsx", "components/FolderField.tsx", "components/LogPanel.tsx",
                     "components/OptionSelect.tsx", "components/BusyBar.tsx"):
            self.assertIn("Design System v1.0 Applied", read(os.path.join(SRC, name)), name)


class Copy(unittest.TestCase):
    def test_all_visible_korean_text_lives_in_copy_ts(self):
        hangul = re.compile(r"[가-힣]")
        offenders = []
        for path in APP:
            if path.endswith(os.path.join("lib", "copy.ts")) or path.endswith(os.path.join("lib", "backend.ts")):
                continue  # backend.ts 의 한국어는 브라우저 미리보기용 목 데이터
            for n, line in enumerate(read(path).splitlines(), 1):
                code = re.sub(r"//.*$|/\*.*?\*/", "", line)  # 주석은 허용
                if hangul.search(code.strip().lstrip("* ")) and not line.strip().startswith(("*", "/*", "//")):
                    offenders.append(f"{rel(path)}:{n}: {line.strip()[:70]}")
        self.assertEqual(offenders, [], "UI 문구는 lib/copy.ts 로:\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
