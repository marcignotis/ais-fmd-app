"""
Design tokens, the Plotly template, and the app stylesheet -- in two palettes.

The look is a technical drawing. Dark mode is chalk on a board; light mode is
ink on paper. Both are the same drawing: hairline rules, wireframe marks,
monospaced figures, and colour reserved almost entirely for meaning.

FINDING (visual). `.streamlit/config.toml` set a dark palette, but no Plotly
template was ever registered or applied, so charts rendered on Plotly's default
light-oriented theme. The income donut used `qualitative.Set3` -- pale pastels
built for white backgrounds -- while the expense donut immediately beside it
used `Set1`, harsh saturated primaries. Two unrelated palettes, side by side,
on a ground neither was designed for.

FINDING (correctness). Colour is a *relationship*, so a second ground needs a
second palette rather than the same swatches on a different backdrop. Measured
against white, the dark palette collapses: income green #2BD97C reads at
1.86:1, the amber at 1.75:1, and the accent blue at 3.63:1 -- all far below the
4.5:1 that small text needs, and two of them illegible outright. Light mode
therefore carries its own semantic values, chosen against paper.

One happy consequence: light mode can use UF's *actual* blue, #0021A5, which is
too dark to survive on black and reads at 11.3:1 on paper.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import plotly.graph_objects as go

# --- Brand -------------------------------------------------------------------
# University of Florida. The official blue is very dark, so the dark palette
# uses a lightened derivative and the light palette uses the real thing.

UF_ORANGE = "#FA4616"
UF_BLUE = "#0021A5"
UF_BLUE_LIT = "#4C7FFF"
UF_GREEN = "#2BD97C"

TEMPLATE_NAME = "ais_fmd"

# Space Grotesk for the interface, JetBrains Mono for anything numeric. The
# mono face is not decoration: a financial table only lines up if the digits
# are the same width, and a technical drawing takes its character from its
# labels. Both fall back to a system stack, so the app stays fully legible with
# no network -- the webfont is a browser request, not a server one, and nothing
# about the sandbox guarantee depends on it.
_FONT = "'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', 'Cascadia Mono', Consolas, 'Liberation Mono', monospace"


@dataclass(frozen=True)
class Palette:
    """
    One complete ground and everything drawn on it.

    Every colour the app uses lives here, so a second mode is a second instance
    rather than a scattering of conditionals. Line tokens are rgba strings
    deliberately: Plotly parses them, they composite correctly over both the
    page and a raised tile, and they must stay out of `charts._translucent`,
    which expects hex. Verified -- no line token is ever passed to it.
    """

    name: str

    # Grounds
    void: str
    surface: str
    raised: str

    # Rules -- three weights: construction ruling, working divider, edge.
    line: str
    line_lit: str
    line_edge: str
    rule: str          # the page's blueprint ruling
    tile_bg: str
    tile_bg_hover: str

    # Ink
    ink: str
    ink_soft: str
    ink_mute: str
    ink_mute_raised: str

    # Brand
    accent: str
    accent_dim: str
    accent_alt: str
    accent_wash: str

    # Semantic -- meaning, not brand.
    income: str
    expense: str
    budget: str
    over: str
    over_wash: str
    approaching: str
    approaching_wash: str
    on_track: str
    on_track_wash: str
    unbudgeted: str

    # How hard to push the fill behind a wireframe mark.
    #
    # The wireframe treatment was tuned on black, where a 16% wash of a bright
    # colour reads as a body under its edge. Inverted, the same 16% of a *dark*
    # colour on white is a barely-there tint -- the edge ends up carrying the
    # shape alone and the bars look washed out. Light mode therefore pushes its
    # fills harder. Applied as a multiplier so every existing call site keeps
    # its relative intent.
    fill_scale: float = 1.0

    categorical: tuple[str, ...] = field(default=())

    @property
    def status_colors(self) -> dict[str, str]:
        return {
            "over": self.over,
            "approaching": self.approaching,
            "on track": self.on_track,
            "unbudgeted": self.unbudgeted,
            "no budget": self.unbudgeted,
        }


# --- Dark: chalk on a board --------------------------------------------------
# Near-black rather than charcoal. A drawing reads as a drawing because the
# ground gives the line nothing to compete with.
#
# The lines are chalk -- white at three opacities -- rather than the cool greys
# they started as. A grey line on a black ground is a dark line: #3B4753
# resolves to about 8% luminance, so panel borders and axis rules were losing
# themselves in the page and the drawing had no visible structure.

DARK = Palette(
    name="dark",
    void="#000000",
    surface="#0A0C0F",
    raised="#12161B",
    line="rgba(237,242,247,.10)",
    line_lit="rgba(237,242,247,.24)",
    line_edge="rgba(237,242,247,.58)",
    rule="rgba(237,242,247,.038)",
    tile_bg="rgba(237,242,247,.014)",
    tile_bg_hover="rgba(237,242,247,.045)",
    ink="#F4F7F9",
    ink_soft="#A9B4BF",
    # #6E7A85 cleared AA on the page ground (4.79:1) but not on a tile
    # (4.46:1). Nudged until it clears both, since chart tick labels sit on the
    # page while a caption inside a tile does not.
    ink_mute="#737F8A",
    ink_mute_raised="#7B8794",
    # Blue leads. Blueprint convention is white linework over blue, and blue is
    # the half of the UF pair that can carry a whole interface without
    # shouting -- orange at any real coverage reads as an alert, which is
    # precisely the job it is given below.
    accent=UF_BLUE_LIT,
    accent_dim="#1E3F8F",
    accent_alt=UF_ORANGE,
    accent_wash="rgba(76,127,255,.09)",
    income=UF_GREEN,
    expense=UF_ORANGE,
    budget=UF_BLUE_LIT,
    # OVER deliberately does *not* reuse UF orange. Orange already carries
    # "expense" in the waterfall and the category bars, and an over-budget
    # committee sitting next to an ordinary expense in the same orange is
    # exactly the confusion the status colours exist to prevent.
    over="#FF3355",
    over_wash="rgba(255,51,85,.10)",
    approaching="#FFB627",
    approaching_wash="rgba(255,182,39,.10)",
    on_track=UF_GREEN,
    on_track_wash="rgba(43,217,124,.10)",
    unbudgeted="#5A6570",
    fill_scale=1.0,
    categorical=(
        UF_BLUE_LIT, UF_ORANGE, UF_GREEN, "#FFB627", "#B47CFF",
        "#2BC4D9", "#FF6FA5", "#8C97A3", "#6BE39B", "#FF8A4C",
    ),
)


# --- Light: ink on paper -----------------------------------------------------
# Not the dark palette inverted. Each semantic value is re-chosen against paper
# and measured: every one below clears 4.5:1 on the tile ground, which is the
# stricter of the two surfaces it has to sit on.

LIGHT = Palette(
    name="light",
    void="#FFFFFF",
    surface="#F7F9FB",
    raised="#EDF1F6",
    line="rgba(11,18,25,.11)",
    line_lit="rgba(11,18,25,.20)",
    line_edge="rgba(11,18,25,.46)",
    rule="rgba(11,18,25,.055)",
    tile_bg="rgba(11,18,25,.022)",
    tile_bg_hover="rgba(11,18,25,.055)",
    ink="#0B1219",           # 17.9:1
    ink_soft="#3D4A57",      #  8.6:1
    ink_mute="#5B6875",      #  5.4:1
    ink_mute_raised="#586572",  # 5.7:1
    accent=UF_BLUE,          # 11.3:1 -- the real UF blue, finally usable
    accent_dim="#4C7FFF",
    accent_alt="#C4360F",
    accent_wash="rgba(0,33,165,.07)",
    income="#0E7C4A",        #  5.0:1
    expense="#C4360F",       #  5.1:1
    budget=UF_BLUE,
    over="#C8102E",          #  5.6:1
    over_wash="rgba(200,16,46,.09)",
    approaching="#8A5B00",   #  5.6:1
    approaching_wash="rgba(138,91,0,.10)",
    on_track="#0E7C4A",
    on_track_wash="rgba(14,124,74,.10)",
    unbudgeted="#616C79",
    fill_scale=1.75,
    categorical=(
        UF_BLUE, "#C4360F", "#0E7C4A", "#8A5B00", "#6B3FA0",
        "#0F6E80", "#A8306A", "#5C6672", "#2E7D5B", "#B4521F",
    ),
)

PALETTES = {"dark": DARK, "light": LIGHT}


def active() -> Palette:
    """
    The palette for the browser rendering this script run.

    Keyed off `st.context.theme.type`, which is per-run rather than global, so
    two sessions on different themes cannot read each other's palette. That
    matters: the obvious implementation -- mutating module-level constants when
    the theme changes -- would have one user's toggle repaint another user's
    charts, and `pio.templates.default` has exactly the same problem, which is
    why the template is attached per figure in `shell` instead of registered
    globally.

    Falls back to dark outside a Streamlit runtime, which is where the tests
    call it from.
    """
    try:
        import streamlit as st

        return LIGHT if st.context.theme.type == "light" else DARK
    except Exception:
        return DARK


# REMOVED: 24 module-level constants (VOID, ACCENT, INCOME, OVER, ...) that
# exposed the DARK palette under its original names, described as
# "backwards-compatible" for callers importing a colour at import time.
#
# Nothing imported them -- checked across the app, the tests and the scripts.
# They were also a live hazard rather than dead weight: every one hardcoded the
# dark value, so a caller reaching for `theme.ACCENT` in light mode got a colour
# from the wrong palette with no error anywhere. Removing them means that
# mistake is now an AttributeError at the point of use.
#
# `active()` is the only correct way to get a colour, and it is what every
# renderer already calls.


def build_template(palette: Palette | None = None) -> go.layout.Template:
    """
    The drawing conventions, applied to every figure.

    Axes are drawn as a single hairline with outward ticks and no surrounding
    box; the grid is dotted and faint enough to read as construction ruling
    rather than as content. Tick labels are monospaced so columns of figures
    align down the axis.
    """
    p = palette or active()
    axis = dict(
        gridcolor=p.line,
        griddash="dot",
        zerolinecolor=p.line_edge,
        zerolinewidth=1,
        linecolor=p.line_edge,
        linewidth=1,
        showline=True,
        ticks="outside",
        ticklen=4,
        tickwidth=1,
        tickcolor=p.line_edge,
        tickfont=dict(family=_MONO, color=p.ink_mute, size=10),
        title=dict(font=dict(family=_MONO, color=p.ink_mute, size=10), standoff=8),
        automargin=True,
    )
    return go.layout.Template(
        layout=go.Layout(
            font=dict(family=_FONT, size=12, color=p.ink_soft),
            title=dict(
                font=dict(family=_MONO, size=11, color=p.ink_mute),
                x=0,
                xanchor="left",
                y=0.98,
                yanchor="top",
            ),
            # Transparent grounds let a chart sit on the drawing surface instead
            # of punching a differently-coloured rectangle into it.
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=list(p.categorical),
            xaxis=axis,
            yaxis=axis,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.03,
                xanchor="left",
                x=0,
                font=dict(family=_MONO, color=p.ink_mute, size=10),
                bgcolor="rgba(0,0,0,0)",
                itemsizing="constant",
            ),
            hoverlabel=dict(
                bgcolor=p.surface,
                bordercolor=p.line_edge,
                font=dict(family=_MONO, size=11, color=p.ink),
                align="left",
            ),
            margin=dict(l=8, r=8, t=34, b=8),
            separators=".,",
            bargap=0.42,
            bargroupgap=0.12,
        )
    )


# REMOVED: `register()`, which existed only "for callers that expect it" and
# was called by nothing. The reasoning it carried is worth keeping, so it lives
# on `shell._transparent` instead: the template is deliberately not installed as
# `pio.templates.default`, because that is process-global and with two palettes
# in play whichever session rendered last would decide what every other
# session's charts looked like.


def _tokens(p: Palette) -> str:
    return f"""
  :root {{
    --void: {p.void};
    --surface: {p.surface};
    --raised: {p.raised};
    --line: {p.line};
    --line-lit: {p.line_lit};
    --line-edge: {p.line_edge};
    --rule: {p.rule};
    --tile-bg: {p.tile_bg};
    --tile-bg-hover: {p.tile_bg_hover};
    --ink: {p.ink};
    --ink-soft: {p.ink_soft};
    --ink-mute: {p.ink_mute};
    --ink-mute-raised: {p.ink_mute_raised};
    --accent: {p.accent};
    --accent-alt: {p.accent_alt};
    --accent-wash: {p.accent_wash};
    --green: {p.on_track};
    --green-wash: {p.on_track_wash};
    --over: {p.over};
    --over-wash: {p.over_wash};
    --approaching: {p.approaching};
    --approaching-wash: {p.approaching_wash};
    --font: {_FONT};
    --mono: {_MONO};
  }}
"""


_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@400;500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap');"
)

_RULES = """
  /* ================================================================= ground
     A drawing surface, not a dashboard background. The ruling is present
     enough to give the page a sense of measure, far too faint to compete with
     a data mark. */
  [data-testid="stMain"] {
    background-color: var(--void);
    background-image:
      linear-gradient(var(--rule) 1px, transparent 1px),
      linear-gradient(90deg, var(--rule) 1px, transparent 1px);
    background-size: 32px 32px;
    background-position: -1px -1px;
  }
  [data-testid="stAppViewContainer"], body { background-color: var(--void); }
  html, body, [data-testid="stAppViewContainer"] { font-family: var(--font); }

  .block-container { padding-top: 2.4rem; padding-bottom: 5rem; max-width: 1480px; }

  /* Streamlit's own top bar sits over the drawing; let it disappear into it. */
  [data-testid="stHeader"] { background: transparent; }

  /* ============================================================ type scale
     FINDING (visual). `.ais-head h1` was styled, but the Streamlit headings
     underneath it never were, and their stock sizes are tuned for prose. The
     page title rendered at 29.6px, `st.subheader` at 28px and `#### ` at 24px
     -- three levels of the hierarchy within five pixels of each other. The eye
     had nothing to rank, so a section heading carried the same weight as the
     name of the page.

     Section headings are now set as drawing callouts: monospaced, uppercase,
     tracked wide, and small. A callout names a region of the drawing instead
     of shouting a title, which is what lets the figures stay the loudest thing
     on the page. */
  .block-container h2 {
    font-size: 1.3rem; font-weight: 600; letter-spacing: -.01em;
    color: var(--ink); margin: 1.6rem 0 .6rem; padding: 0;
  }
  .block-container h3 {
    font-family: var(--mono);
    font-size: .78rem; font-weight: 500; letter-spacing: .18em;
    text-transform: uppercase; color: var(--ink-mute);
    margin: .2rem 0 1rem; padding: 0 0 .55rem;
    border-bottom: 1px solid var(--line-lit);
    display: flex; align-items: center; gap: .6rem;
  }
  /* The tick that turns a heading into a callout. */
  .block-container h3::before {
    content: ''; width: 5px; height: 5px; flex: 0 0 5px;
    background: var(--accent); transform: rotate(45deg);
  }
  .block-container h4 {
    font-family: var(--mono);
    font-size: .72rem; font-weight: 500; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-mute);
    margin: 1.2rem 0 .55rem; padding: 0;
  }
  .block-container h5, .block-container h6 {
    font-family: var(--mono);
    font-size: .68rem; font-weight: 500; text-transform: uppercase;
    letter-spacing: .14em; color: var(--ink-mute); margin: 1rem 0 .4rem; padding: 0;
  }

  /* =============================================================== banner */
  .ais-banner {
    display: flex; align-items: center; gap: .7rem;
    border: 1px solid var(--line-lit);
    border-left: 2px solid var(--accent);
    background: linear-gradient(90deg, var(--accent-wash), transparent 60%);
    color: var(--ink-soft);
    padding: .55rem .9rem;
    border-radius: 0;
    font-size: .8rem;
    margin-bottom: 1.4rem;
  }
  .ais-banner-prod {
    border-left-color: var(--over);
    background: linear-gradient(90deg, var(--over-wash), transparent 60%);
  }
  .ais-banner b {
    font-family: var(--mono); font-size: .7rem; font-weight: 600;
    color: var(--accent); letter-spacing: .16em;
  }
  .ais-banner-prod b { color: var(--over); }

  /* ========================================================== page header */
  .ais-head { margin-bottom: .3rem; }
  .ais-head h1 {
    font-size: 2.1rem; font-weight: 600; letter-spacing: -.028em;
    margin: 0 0 .35rem; color: var(--ink); line-height: 1.1;
  }
  .ais-head p {
    color: var(--ink-mute); font-size: .88rem; margin: 0; max-width: 74ch;
    line-height: 1.55;
  }
  .ais-rule {
    height: 1px; border: 0; margin: 1.1rem 0 1.5rem;
    background: linear-gradient(90deg, var(--line-edge), var(--line) 42%, transparent);
  }

  /* ============================================================= KPI tiles
     FINDING (visual). The KPI row is the first thing on every page and had no
     visual treatment whatsoever: a transparent ground, no border, no padding,
     and -- the part that actually cost comprehension -- a label rendered in
     exactly the same colour and weight as its value. Four numbers floated in a
     row with nothing binding a label to its figure or separating one tile from
     the next, so "Expenses $10,668.55 Net -$4,301.22" read as one run of text.

     The tile wraps the *vertical block* rather than the metric element itself,
     because `shell.metric` renders a sparkline as a sibling of the metric
     rather than a child of it; carding the metric alone would have cut the
     trend line out of the tile it belongs to. Every metric in the app is built
     by `shell.metric_row`, which puts nothing else in the column, so this
     cannot swallow unrelated content -- verified: no view calls `st.metric` or
     `shell.metric` directly.

     The tile is built as a technical readout rather than a card, which is the
     distinction the blueprint idiom turns on: framing comes from corner
     brackets and a rule, not from a filled box with a rounded edge. So there
     is no continuous border. Four brackets mark the corners, a hairline sits
     under the label, and the ground is barely lifted off the page -- the tile
     is a region of the drawing that has been marked out, not an object resting
     on top of it.

     The brackets are drawn with background gradients rather than pseudo-
     elements, because ::before and ::after are only two and a bracket needs
     four corners. Each gradient paints one arm; the background-size list gives
     each its length and orientation. A ninth gradient lays a short
     registration mark along the top edge in the secondary brand colour -- the
     one place it appears in the page chrome, which is what keeps it reading as
     a mark rather than as decoration. */
  [data-testid="stColumn"] > [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]) {
    position: relative;
    background-color: var(--tile-bg);
    border: 0;
    border-radius: 0;
    padding: .9rem 1.05rem 1rem;
    gap: .1rem;
    background-image:
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--line-edge), var(--line-edge)),
      linear-gradient(var(--accent-alt), var(--accent-alt));
    background-repeat: no-repeat;
    background-size:
      13px 1px, 1px 13px,
      13px 1px, 1px 13px,
      13px 1px, 1px 13px,
      13px 1px, 1px 13px,
      26px 2px;
    background-position:
      left top, left top,
      right top, right top,
      left bottom, left bottom,
      right bottom, right bottom,
      left top;
    transition: background-color .18s ease;
  }
  [data-testid="stColumn"] > [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] > [data-testid="stMetric"]):hover {
    background-color: var(--tile-bg-hover);
  }
  /* The label sits in its own register above a rule, the way a field on a
     drawing is titled. `display:block` is needed because Streamlit renders it
     as a <label>, which is inline by default and so would not carry a rule
     across the full width of the tile. */
  [data-testid="stMetricLabel"] {
    display: block; width: 100%;
    border-bottom: 1px solid var(--line);
    padding-bottom: .5rem; margin-bottom: .6rem;
  }
  [data-testid="stMetricLabel"] p {
    font-family: var(--mono);
    font-size: .64rem; font-weight: 500; letter-spacing: .2em;
    text-transform: uppercase; color: var(--ink-mute-raised); margin: 0;
  }
  [data-testid="stMetricValue"] {
    font-family: var(--mono);
    font-variant-numeric: tabular-nums;
    font-size: 1.62rem; font-weight: 500; letter-spacing: -.04em;
    color: var(--ink); line-height: 1.2;
  }
  [data-testid="stMetricDelta"] {
    font-family: var(--mono);
    font-variant-numeric: tabular-nums; font-size: .72rem; font-weight: 500;
    letter-spacing: -.01em; padding-top: .15rem;
  }
  [data-testid="stMetricDelta"] svg { width: .85em; height: .85em; }

  /* ======================================================= markdown tables
     FINDING (visual). A markdown table sized itself to its content -- the
     "Where things are" table on the Home page occupied 631px of a 1270px
     column and sat stranded against the left edge -- and rendered its body at
     16px, larger than the 15.2px page prose it was explaining. Its rules were
     drawn at 10% white rather than the line token every other divider uses.

     Scoped to stMarkdownContainer so it styles prose tables only. st.dataframe
     renders its own grid, not an HTML table, and is untouched by this. */
  .block-container [data-testid="stMarkdownContainer"] table {
    width: 100%; border-collapse: collapse; font-size: .84rem;
    margin: .2rem 0 .6rem;
  }
  .block-container [data-testid="stMarkdownContainer"] thead th {
    text-align: left; font-family: var(--mono);
    font-size: .64rem; font-weight: 500;
    text-transform: uppercase; letter-spacing: .16em; color: var(--ink-mute);
    border-bottom: 1px solid var(--line-edge); padding: .5rem .8rem; background: none;
  }
  .block-container [data-testid="stMarkdownContainer"] tbody td {
    border-bottom: 1px solid var(--line); padding: .55rem .8rem;
    color: var(--ink-soft); font-variant-numeric: tabular-nums; vertical-align: top;
  }
  .block-container [data-testid="stMarkdownContainer"] tbody tr:last-child td {
    border-bottom: 0;
  }
  .block-container [data-testid="stMarkdownContainer"] tbody tr:hover td {
    background: var(--tile-bg-hover);
  }
  .block-container [data-testid="stMarkdownContainer"] tbody strong {
    color: var(--ink); font-weight: 600;
  }

  /* ============================================================ dataframes
     The grid paints its own interior from Streamlit's theme, so this is
     limited to seating it in the same frame as everything else. */
  [data-testid="stDataFrame"] { border: 1px solid var(--line-lit); }

  /* ================================================================= pills */
  .ais-pill {
    display: inline-block; font-family: var(--mono);
    font-size: .6rem; letter-spacing: .16em; font-weight: 500;
    text-transform: uppercase; padding: .22em .55em; border-radius: 0;
    border: 1px solid currentColor; line-height: 1.5;
  }
  .ais-over { color: var(--over); background: var(--over-wash); }
  .ais-approaching { color: var(--approaching); background: var(--approaching-wash); }
  .ais-ontrack { color: var(--green); background: var(--green-wash); }
  .ais-muted { color: var(--ink-mute); }

  /* ========================================================= empty states */
  .ais-empty {
    border: 1px dashed var(--line-lit); border-radius: 0;
    padding: 1.7rem; text-align: center; color: var(--ink-mute);
    font-size: .85rem; background: var(--tile-bg);
  }
  .ais-empty strong {
    display: block; color: var(--ink-soft); margin-bottom: .3rem;
    font-family: var(--mono); font-size: .72rem;
    text-transform: uppercase; letter-spacing: .14em; font-weight: 500;
  }

  /* =============================================================== sidebar */
  [data-testid="stSidebar"] { border-right: 1px solid var(--line-lit); }

  /* The mode switch reads as an instrument control rather than a button. */
  [data-testid="stSidebar"] [data-testid="stButton"] button {
    font-family: var(--mono); font-size: .64rem; font-weight: 500;
    letter-spacing: .16em; text-transform: uppercase;
    border-radius: 0; border: 1px solid var(--line-lit);
    color: var(--ink-mute);
  }
  [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
    border-color: var(--accent); color: var(--accent);
  }

  /* ============================================================= animation
     Entrance only, and deliberately brief. Streamlit re-runs the whole script
     on every widget interaction, so anything long or theatrical here replays
     in full each time a filter moves -- the same trap the old per-character
     title animation fell into. 380ms with a short stagger reads as the drawing
     being plotted; anything more reads as a wait.

     prefers-reduced-motion is honoured, which is not decoration either: motion
     sensitivity is a real accessibility need, and this is a tool people have
     to use rather than a page they choose to visit. */
  @keyframes ais-plot {
    from { opacity: 0; transform: translateY(7px); }
    to   { opacity: 1; transform: none; }
  }
  @keyframes ais-sweep {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
  }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    animation: ais-plot .38s cubic-bezier(.22,.7,.3,1) both;
  }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) { animation-delay: 0s; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) { animation-delay: .05s; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) { animation-delay: .10s; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4) { animation-delay: .15s; }
  .js-plotly-plot { animation: ais-plot .42s cubic-bezier(.22,.7,.3,1) both .06s; }
  .ais-rule { animation: ais-sweep .5s cubic-bezier(.22,.7,.3,1) both; transform-origin: left center; }
  .ais-head h1 { animation: ais-plot .4s cubic-bezier(.22,.7,.3,1) both; }
  .block-container h3 { animation: ais-plot .4s cubic-bezier(.22,.7,.3,1) both .04s; }

  @media (prefers-reduced-motion: reduce) {
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    .js-plotly-plot, .ais-rule, .ais-head h1, .block-container h3 {
      animation: none !important;
    }
  }
"""


def app_css(palette: Palette | None = None) -> str:
    """The stylesheet for one palette."""
    return "<style>\n" + _FONT_IMPORT + "\n" + _tokens(palette or active()) + _RULES + "</style>\n"


# Kept so that anything still importing the constant renders in dark.
APP_CSS = app_css(DARK)
