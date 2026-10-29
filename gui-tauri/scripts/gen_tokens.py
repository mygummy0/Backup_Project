"""design_tokens.py -> gui-tauri/src/tokens.css (shadcn CSS variables). Run: python gui-tauri/scripts/gen_tokens.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import design_tokens as dt  # noqa: E402

OUT = os.path.join(ROOT, "gui-tauri", "src", "tokens.css")

# shadcn variable -> design_tokens role
VARS = [
    ("background", "page"), ("foreground", "text"),
    ("card", "card"), ("card-foreground", "text"),
    ("popover", "card"), ("popover-foreground", "text"),
    ("primary", "primary"), ("primary-foreground", "on_primary"),
    ("primary-hover", "primary_hover"), ("primary-active", "primary_active"), ("pressed", "secondary_active"),
    ("secondary", "secondary_hover"), ("secondary-foreground", "text"),
    ("muted", "log_bg"), ("muted-foreground", "text_sub"),
    ("accent", "menu_hover"), ("accent-foreground", "text"),
    ("destructive", "error"),
    ("border", "border"), ("input", "border"), ("ring", "ring"),
    ("success", "success"), ("warning", "warn"),
]


def block(selector, theme):
    colors = dt.theme_colors(theme)
    lines = [f"  --{name}: {colors[role]};" for name, role in VARS]
    return f"{selector} {{\n" + "\n".join(lines) + "\n}\n"


def render():
    fonts = ", ".join(f'"{f}"' if " " in f else f for f in dt.FONT_CANDIDATES)
    return (
        "/* GENERATED from design_tokens.py by gui-tauri/scripts/gen_tokens.py - do not edit. */\n"
        + block(":root", "light") + "\n" + block(".dark", "dark")
        + f"\n:root {{\n  --radius-card: {dt.RADIUS_CARD}px;\n  --radius-control: {dt.RADIUS_CONTROL}px;\n"
        f"  --control-height: {dt.CONTROL_HEIGHT}px;\n  --duration: {dt.DURATION_MS}ms;\n"
        f"  --ease-out: cubic-bezier({', '.join(str(x) for x in dt.EASE_OUT)});\n"
        f"  --font-sans: {fonts}, sans-serif;\n  --letter-spacing: {dt.LETTER_SPACING};\n  --line-height: {dt.LINE_HEIGHT};\n}}\n"
    )


if __name__ == "__main__":
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render())
    print("wrote", OUT)
