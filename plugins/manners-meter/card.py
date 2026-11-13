"""Share card for manners-meter: one self-contained HTML file, 1080 x 1920 (story format).

No external fonts, scripts or images, so the file works offline and leaks nothing.
Open it in a browser and take a screenshot, or render it headless.
Layout keeps the top 150 px and bottom 170 px free of key content (story app overlays).
"""
from __future__ import annotations

import html

from .meter import Report, fmt_int, fmt_money, fmt_tokens, rank

LABELS = {
    "en": {
        "kicker": "Manners meter", "said": "you said", "jar": "Swear jar", "coins": "coins",
        "owe": "you owe the jar", "clean": "Empty.", "clean2": "Suspiciously clean.",
        "typed": "politeness tokens typed", "carried": "re-sent with later calls",
        "welcome": "\"you're welcome\" back", "rank": "Your rank", "local": "Counted locally. Nothing uploaded.",
        "top": "top word",
    },
    "de": {
        "kicker": "Manners Meter", "said": "hast du gesagt", "jar": "Schimpfglas", "coins": "Münzen",
        "owe": "schuldest du dem Glas", "clean": "Leer.", "clean2": "Verdächtig sauber.",
        "typed": "getippte Höflichkeits-Tokens", "carried": "bei späteren Aufrufen mitgeschickt",
        "welcome": "mal \"gern geschehen\" zurück", "rank": "Dein Rang", "local": "Lokal gezählt. Nichts hochgeladen.",
        "top": "Lieblingswort",
    },
}

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden}
body{font-family:-apple-system,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#2b1600;
background:radial-gradient(circle at 85% 8%,#fff6e2 0,transparent 38%),
linear-gradient(170deg,#ffe3b3 0%,#ffbf6e 55%,#ff9a4a 100%);
padding:140px 72px 180px;display:flex;flex-direction:column;justify-content:space-between}
.mono{font-family:ui-monospace,'JetBrains Mono',Menlo,Consolas,monospace}
.pill{display:inline-block;background:#2b1600;color:#ffe3b3;font-weight:800;font-size:34px;letter-spacing:.16em;
text-transform:uppercase;padding:16px 30px;border-radius:999px}
.hero{display:flex;align-items:flex-end;gap:26px;margin-top:34px}
.num{font-size:200px;font-weight:900;letter-spacing:-.06em;line-height:.82}
.said{font-size:44px;font-weight:700;line-height:1.15;padding-bottom:22px}
.word{display:inline-block;background:#fff;border:6px solid #2b1600;border-radius:26px;padding:4px 26px 10px;
font-size:80px;font-weight:900;letter-spacing:-.03em;transform:rotate(-3deg);box-shadow:10px 10px 0 #2b1600;margin-top:18px}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.tile{background:#2b1600;color:#ffe3b3;border-radius:30px;padding:22px 26px 20px;hyphens:none}
.tile b{display:block;font-size:56px;font-weight:900;letter-spacing:-.04em;line-height:1;color:#fff}
.tile span{font-size:30px;font-weight:600;opacity:.85}
.wide{display:flex;gap:22px}
.wide .tile{flex:1}
.wide .tile b{font-size:52px}
.jarrow{display:flex;align-items:center;gap:36px}
.jartxt .k{font-size:34px;font-weight:800;letter-spacing:.16em;text-transform:uppercase}
.jartxt .n{font-size:112px;font-weight:900;letter-spacing:-.05em;line-height:.95;margin-top:6px}
.jartxt .s{font-size:40px;font-weight:700;line-height:1.2}
.jartxt .t{font-size:32px;font-weight:600;opacity:.75;margin-top:10px}
.rank{display:flex;align-items:center;gap:26px}
.stamp{border:7px solid #b3261e;color:#b3261e;border-radius:20px;padding:10px 26px 12px;transform:rotate(-4deg);
font-size:54px;font-weight:900;letter-spacing:-.02em;text-transform:uppercase;line-height:1;background:rgba(255,255,255,.35)}
.rank .lab{font-size:30px;font-weight:700;opacity:.75}
.rank .sub{font-size:36px;font-weight:800;margin-top:6px}
.foot{background:#2b1600;color:#ffe3b3;border-radius:28px;padding:24px 30px;display:flex;justify-content:space-between;
align-items:center;gap:20px}
.foot .cmd{font-size:29px;font-weight:700;color:#fff;white-space:nowrap}
.foot .loc{font-size:24px;opacity:.85;text-align:right;line-height:1.25}
"""

MAX_COINS = 33  # six full rows; a seventh row would touch the shoulder of the jar


def _jar_svg(coins: int) -> str:
    """A glass jar with a lid and a pile of coins, drawn inline (no image files)."""
    w, h = 400, 470
    parts = [f'<svg width="{int(w * .78)}" height="{int(h * .78)}" viewBox="0 0 {w} {h}">',
             '<defs><radialGradient id="c" cx="35%" cy="35%" r="70%"><stop offset="0" stop-color="#fff1a8"/>'
             '<stop offset=".6" stop-color="#f2b631"/><stop offset="1" stop-color="#b57b0c"/></radialGradient></defs>',
             '<rect x="92" y="18" width="216" height="46" rx="12" fill="#2b1600"/>',
             '<rect x="112" y="64" width="176" height="22" fill="#2b1600" opacity=".55"/>',
             '<path d="M112 86 Q60 110 60 170 L60 400 Q60 450 110 450 L290 450 Q340 450 340 400 L340 170 Q340 110 288 86 Z" '
             'fill="rgba(255,255,255,.42)" stroke="#2b1600" stroke-width="9"/>']
    shown = min(coins, MAX_COINS)
    r, gap = 20, 42
    per_row = 6
    x0, y = 200 - (per_row - 1) * gap / 2 - r, 422  # rows centred between the jar walls (x 69..331)
    i = 0
    row = 0
    while i < shown:
        n = min(per_row - (row % 2), shown - i)
        off = (row % 2) * gap / 2
        for k in range(n):
            cx = x0 + off + k * gap + r
            parts.append(f'<ellipse cx="{cx:.0f}" cy="{y}" rx="{r}" ry="{r - 3}" fill="url(#c)" stroke="#8a5a00" stroke-width="3"/>')
            i += 1
        y -= 38
        row += 1
    parts.append('<path d="M92 140 Q84 260 92 380" stroke="#fff" stroke-width="12" stroke-linecap="round" fill="none" opacity=".7"/>')
    if coins > MAX_COINS:
        parts.append(f'<text x="200" y="{max(y, 150)}" text-anchor="middle" font-size="44" font-weight="900" '
                     f'fill="#2b1600" font-family="Inter,Arial,sans-serif">+{coins - MAX_COINS}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_card(rep: Report, *, lang: str = "en", jar_price: float = 1.0, currency: str = "",
                year_label: str = "") -> str:
    t = LABELS.get(lang, LABELS["en"])
    e = html.escape
    cur = currency or ("€" if lang == "de" else "$")
    if rep.polite_total:
        top_word, top_n = rep.polite.most_common(1)[0]
    else:
        top_word, top_n = ("please" if lang == "en" else "bitte"), 0
    p_rank, s_rank = rank(rep, lang)
    kicker = t["kicker"] + ((" " + year_label) if year_label else "")

    head = (f'<div><span class="pill">{e(kicker)}</span>'
            f'<div class="hero"><div class="num">{fmt_int(top_n, lang)}×</div>'
            f'<div class="said">{e(t["said"])}</div></div>'
            f'<div class="word">{e(top_word)}</div></div>')

    others = rep.polite.most_common(4)[1:]
    tiles = "".join(f'<div class="tile"><b>{fmt_int(v, lang)}×</b><span>{e(k)}</span></div>' for k, v in others)
    tiles_html = f'<div class="tiles">{tiles}</div>' if others else ""

    wide = [f'<div class="tile"><b>{fmt_int(rep.polite_tokens, lang)}</b><span>{e(t["typed"])}</span></div>']
    if rep.carried_tokens:
        wide.append(f'<div class="tile"><b>{e(fmt_tokens(rep.carried_tokens, lang))}</b><span>{e(t["carried"])}</span></div>')
    elif rep.welcome_total:
        wide.append(f'<div class="tile"><b>{fmt_int(rep.welcome_total, lang)}×</b><span>{e(t["welcome"])}</span></div>')
    wide_html = '<div class="wide">' + "".join(wide) + "</div>"

    if rep.swear_total:
        top_swear = rep.swear.most_common(1)[0][0]
        jt = (f'<div class="k">{e(t["jar"])}</div><div class="n">{fmt_int(rep.swear_total, lang)}</div>'
              f'<div class="s">{e(t["coins"])}. {e(fmt_money(rep.swear_total * jar_price, cur, lang))}<br>{e(t["owe"])}.</div>'
              f'<div class="t">{e(t["top"])}: {e(top_swear)}</div>')
    else:
        jt = (f'<div class="k">{e(t["jar"])}</div><div class="n">0</div>'
              f'<div class="s">{e(t["clean"])}<br>{e(t["clean2"])}</div>')
    jar = f'<div class="jarrow">{_jar_svg(rep.swear_total)}<div class="jartxt">{jt}</div></div>'

    rank_html = (f'<div class="rank"><div class="stamp">{e(p_rank)}</div>'
                 f'<div><div class="lab">{e(t["rank"])}</div><div class="sub">{e(s_rank)}</div></div></div>')

    foot = (f'<div class="foot"><div class="cmd mono">hermes plugins install manners-meter</div>'
            f'<div class="loc">{e(t["local"])}</div></div>')

    body = head + tiles_html + wide_html + jar + rank_html + foot
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=1080">'
            f"<title>{e(kicker)}</title><style>{CSS}</style></head><body>{body}</body></html>")
