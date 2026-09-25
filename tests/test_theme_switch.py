"""
Guards for the light/dark switch.

The switch depends on one thing Streamlit does not promise: the browser
localStorage key its frontend reads the viewer's theme preference from. There
is no Python API for setting the theme -- `st.context.theme` is read-only, and
its own docstring warns the value is unreliable during a change -- so the
button writes that key and reloads.

An internal detail is an acceptable dependency only if it cannot break
silently. These tests re-derive the key from the *installed* Streamlit bundle,
so a version bump that moves it fails here, at upgrade time, instead of
shipping a button that quietly does nothing.

The palette tests exist for the other half of the problem: `st.dataframe`
paints a canvas grid from Streamlit's own theme, which never sees the app
stylesheet, so `.streamlit/config.toml` has to agree with the Palette objects
or light mode shows dark tables on a white page.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from ais_fmd.ui import shell, theme

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = pytest.importorskip("tomli")

CONFIG = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"


def _streamlit_bundle() -> str:
    import streamlit

    static = Path(streamlit.__file__).parent / "static" / "static" / "js"
    if not static.is_dir():
        pytest.skip("Streamlit static bundle not present in this install")
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in static.glob("*.js")
    )


def test_theme_storage_key_template_still_exists():
    """The key Streamlit builds must still be the one `shell` writes."""
    bundle = _streamlit_bundle()
    assert "stActiveTheme-${window.location.pathname}" in bundle, (
        "Streamlit no longer builds its theme localStorage key as "
        "`stActiveTheme-${window.location.pathname}`. shell._write_theme_preference "
        "writes that key, so the light/dark button is now a no-op. Re-derive the "
        "key from the frontend bundle and update _THEME_KEY_TEMPLATE."
    )


def test_theme_storage_version_still_matches():
    """
    The key is suffixed `-v<CACHED_THEME_VERSION>`. Minified, that version is a
    variable assigned immediately before the key template, so it is read back
    from the same expression rather than from a name that will not survive
    minification.
    """
    bundle = _streamlit_bundle()
    match = re.search(
        r"(?:var|let|const)\s+\w+\s*=\s*(\d+)\s*,\s*\w+\s*=\s*[`\"']stActiveTheme-",
        bundle,
    )
    assert match, "could not locate the cached-theme version beside the key template"
    found = int(match.group(1))
    assert found == shell._THEME_STORAGE_VERSION, (
        f"Streamlit's cached theme version is now v{found}, but shell writes "
        f"v{shell._THEME_STORAGE_VERSION}. The light/dark button writes a key "
        f"nothing reads. Update _THEME_STORAGE_VERSION."
    )


def test_theme_switch_writes_a_value_streamlit_accepts():
    """
    Streamlit validates the stored value against exactly "Light", "Dark" and
    "System" and ignores anything else, so the two names the button writes have
    to be among them.
    """
    bundle = _streamlit_bundle()
    for name in ("Light", "Dark"):
        assert f"`{name}`" in bundle or f'"{name}"' in bundle, (
            f"Streamlit no longer recognises the theme name {name!r}."
        )


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_config_matches_palette(mode: str):
    """
    Streamlit paints the dataframe grid and the widget chrome from config.toml,
    not from the app stylesheet. If these drift apart, light mode renders dark
    tables on a white page.
    """
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    section = config["theme"][mode]
    palette = theme.PALETTES[mode]

    pairs = {
        "backgroundColor": palette.void,
        "secondaryBackgroundColor": palette.surface,
        "textColor": palette.ink,
        "primaryColor": palette.accent,
    }
    for key, expected in pairs.items():
        assert section[key].upper() == expected.upper(), (
            f"[theme.{mode}] {key} is {section[key]} but the {mode} palette says "
            f"{expected}. Streamlit's own chrome would disagree with the app."
        )


def _contrast(foreground: str, background: str) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(colour: str) -> float:
        colour = colour.lstrip("#")
        r, g, b = (int(colour[i : i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    a, b = luminance(foreground), luminance(background)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_semantic_colour_clears_aa_on_its_own_ground(mode: str):
    """
    Colour is a relationship, which is why there are two palettes rather than
    one palette on two backgrounds. Measured against white, the dark values
    collapse -- its income green reads 1.86:1 and its amber 1.75:1 -- so this
    checks each palette against the surface it is actually drawn on.

    The tile ground is the stricter of the two surfaces, so it is the one used.
    """
    palette = theme.PALETTES[mode]
    ground = palette.surface
    for field in ("income", "expense", "budget", "over", "approaching", "accent",
                  "ink", "ink_soft", "ink_mute", "ink_mute_raised"):
        colour = getattr(palette, field)
        ratio = _contrast(colour, ground)
        assert ratio >= 4.5, (
            f"{mode}.{field} ({colour}) is {ratio:.2f}:1 on {ground} -- below the "
            f"4.5:1 AA threshold for small text."
        )


def test_active_falls_back_to_dark_outside_a_runtime():
    """The tests call this with no browser attached; it must not explode."""
    assert theme.active() in (theme.DARK, theme.LIGHT)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_css_carries_no_unresolved_tokens(mode: str):
    css = theme.app_css(theme.PALETTES[mode])
    assert not re.findall(r"\{[A-Z_]+\}", css), "unrendered f-string token in the stylesheet"
    assert "var(--void)" in css and ":root" in css


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_template_grounds_are_transparent(mode: str):
    """
    The page draws a blueprint ruling and every chart sits on it. Streamlit
    writes its own background onto figures even when told not to, so the
    template must at minimum ask for transparent.
    """
    template = theme.build_template(theme.PALETTES[mode])
    assert template.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert template.layout.plot_bgcolor == "rgba(0,0,0,0)"
