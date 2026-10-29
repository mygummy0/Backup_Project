# Design System v1.0 Applied
"""Design tokens for the backup GUI. Values mirror the Tailwind-based spec; main.py must not
use any colour, font size, spacing or radius that is not defined here."""

# ---- Color palette ------------------------------------------------------------------
COLOR = {
    "brand_50": "#EEF2FF",
    "brand_400": "#818CF8",   # focus ring on dark
    "brand_600": "#4F46E5",   # primary
    "brand_700": "#4338CA",   # primary hover
    "brand_800": "#3730A3",   # primary active (pressed)
    "white": "#FFFFFF",
    "slate_50": "#F8FAFC",    # page background
    "slate_200": "#E2E8F0",   # border
    "slate_400": "#94A3B8",   # sub text on dark
    "slate_500": "#64748B",   # sub text
    "slate_700": "#334155",   # dark border / pressed
    "slate_800": "#1E293B",   # dark hover / track
    "slate_900": "#0F172A",   # main text / dark card
    "slate_950": "#020617",   # dark page
    # Semantic. emerald_600 / amber_500 are for non-text use (dots, bars); text uses the darker step
    # because emerald-600 and amber-500 fail WCAG AA (4.5:1) on white, and rose-600 misses it on slate-50.
    "emerald_600": "#059669",
    "emerald_400": "#34D399",
    "emerald_700": "#047857",
    "rose_600": "#E11D48",
    "rose_400": "#FB7185",
    "rose_700": "#BE123C",
    "amber_500": "#F59E0B",
    "amber_400": "#FBBF24",
    "amber_700": "#B45309",
}

# ---- Semantic roles per theme (role -> palette name) -------------------------------------
# The light/dark themes are designed as a pair: same roles, contrast checked independently.
# Dark text is slate-50, not pure white; dark surfaces step page < card so cards stay visible.
THEMES = {
    "light": {
        "page": "slate_50", "card": "white", "border": "slate_200", "field": "white", "log_bg": "slate_50",
        "text": "slate_900", "text_sub": "slate_500",
        "primary": "brand_600", "primary_hover": "brand_700", "primary_active": "brand_800", "on_primary": "white",
        "secondary": "white", "secondary_hover": "slate_50", "secondary_active": "slate_200",
        "off_bg": "slate_200", "off_surface": "slate_50", "off_text": "slate_500",
        "menu_hover": "brand_50", "track": "slate_200",
        "ring": "brand_600", "ring_on_primary": "slate_900",
        "success": "emerald_700", "error": "rose_700", "warn": "amber_700",
    },
    "dark": {
        "page": "slate_950", "card": "slate_900", "border": "slate_700", "field": "slate_950", "log_bg": "slate_950",
        "text": "slate_50", "text_sub": "slate_400",
        "primary": "brand_600", "primary_hover": "brand_700", "primary_active": "brand_800", "on_primary": "white",
        "secondary": "slate_900", "secondary_hover": "slate_800", "secondary_active": "slate_700",
        "off_bg": "slate_800", "off_surface": "slate_800", "off_text": "slate_500",
        "menu_hover": "slate_800", "track": "slate_800",
        "ring": "brand_400", "ring_on_primary": "slate_50",
        "success": "emerald_400", "error": "rose_400", "warn": "amber_400",
    },
}


def theme_colors(theme):
    """role -> hex for the given theme."""
    return {role: COLOR[name] for role, name in THEMES[theme].items()}

# ---- Typography scale: name -> (size px, weight) --------------------------------------
# Tk has no "extrabold"/"medium": display uses bold, caption uses normal.
TYPE = {
    "display1": (36, "bold"),
    "h1": (24, "bold"),
    "h2": (20, "bold"),
    "body_lg": (16, "normal"),
    "body": (14, "normal"),
    "caption": (12, "normal"),
}

# ---- Spacing (8px grid) and shape ----------------------------------------------------
SPACE = {"1": 4, "2": 8, "4": 16, "6": 24, "8": 32, "16": 64}
RADIUS_CARD = 12
RADIUS_CONTROL = 8
CONTROL_HEIGHT = 40
BORDER = 1
FOCUS_BORDER = 2

# ---- Motion: duration-200, cubic-bezier(0.16, 1, 0.3, 1) -----------------------------------
DURATION_MS = 200
EASE_OUT = (0.16, 1.0, 0.3, 1.0)

# Font families tried in order; Inter has no Hangul so it comes last.
FONT_CANDIDATES = ["Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR",
                   "Noto Sans KR", "NanumGothic", "Inter"]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def lerp_color(a, b, t):
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def cubic_bezier(x1, y1, x2, y2):
    """CSS-style timing function: returns f(t) for t in [0, 1]."""
    def bez(u, p1, p2):
        return 3 * (1 - u) ** 2 * u * p1 + 3 * (1 - u) * u ** 2 * p2 + u ** 3

    def f(t):
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):  # solve x(u) = t by bisection
            mid = (lo + hi) / 2
            if bez(mid, x1, x2) < t:
                lo = mid
            else:
                hi = mid
        return bez((lo + hi) / 2, y1, y2)
    return f


ease_out = cubic_bezier(*EASE_OUT)

# (text role, background role, where it is used) - every text/background pair the GUI draws,
# checked in BOTH themes. Disabled controls (off_text) are exempt from WCAG contrast.
TEXT_PAIRS = [
    ("text", "page", "main text on page"),
    ("text", "card", "main text on card"),
    ("text", "field", "input text"),
    ("text", "log_bg", "log text"),
    ("text_sub", "card", "caption on card"),
    ("text_sub", "page", "caption on page"),
    ("text_sub", "log_bg", "log timestamp"),
    ("on_primary", "primary", "primary button"),
    ("on_primary", "primary_hover", "primary button hover"),
    ("on_primary", "primary_active", "primary button pressed"),
    ("text", "secondary", "secondary button"),
    ("text", "secondary_hover", "secondary button hover"),
    ("text", "secondary_active", "secondary button pressed"),
    ("text", "menu_hover", "menu item hover"),
    ("success", "log_bg", "log success"),
    ("error", "log_bg", "log error"),
    ("error", "card", "inline error"),
    ("warn", "log_bg", "log warning"),
]
