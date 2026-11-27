"""The share card, site/og.png (1200 x 630): the response curve and the headline number. Needs Google Chrome.

    python tools/og.py
"""
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main():
    d = json.loads((SITE / "data" / "release.json").read_text())
    res = json.loads((ROOT / "data" / "out" / "results.json").read_text())["2026"]
    g, b = d["grid"], d["seasons"]["2026"]["beta_all"]["est"]
    x0, x1, y0, y1 = 640, 1130, 470, 170
    X = lambda t: x0 + (t + 5) / 35 * (x1 - x0)  # noqa: E731  (-5 s .. +30 s)
    Y = lambda v: y0 + v * (y1 - y0)  # noqa: E731
    pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(g, b) if -5 <= t <= 30 and v is not None)
    ticks = "".join(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y0 + 14}" y2="{y0 + (22 if t % 5 == 0 else 18)}" '
                    f'stroke="#847a6c"/>' for t in range(-5, 31))
    labels = "".join(f'<text x="{X(t):.1f}" y="{y0 + 44}" text-anchor="middle" class="t">{"+" if t > 0 else ""}{t} s</text>'
                     for t in (0, 10, 20, 30))
    half = res["speed"]["half_time"]["median"]
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&family=Instrument+Sans:wght@500;600&display=block" rel="stylesheet">
<style>
html, body {{ margin: 0; }}
body {{ width: 1200px; height: 630px; background: #f4efe4; color: #1d1a16; position: relative; overflow: hidden;
  font-family: "Instrument Sans", sans-serif; }}
.k {{ position: absolute; left: 70px; top: 64px; font-weight: 600; font-size: 17px; letter-spacing: .2em;
  text-transform: uppercase; color: #b4432c; }}
h1 {{ position: absolute; left: 66px; top: 96px; width: 540px; margin: 0; font: 500 74px/1.0 "Cormorant Garamond", serif; }}
.n {{ position: absolute; left: 70px; bottom: 70px; width: 500px; font-size: 21px; line-height: 1.4; color: #554d42; }}
.n b {{ color: #1d1a16; font-size: 46px; display: block; letter-spacing: -.02em; }}
.rule {{ position: absolute; left: 0; right: 0; height: 1px; background: #1d1a16; }}
svg {{ position: absolute; left: 0; top: 0; }}
.t {{ font: 500 15px "Instrument Sans"; fill: #847a6c; }}
</style></head><body>
<div class="rule" style="top:28px"></div><div class="rule" style="top:32px;background:#cfc3ad"></div>
<div class="rule" style="bottom:28px"></div><div class="rule" style="bottom:32px;background:#cfc3ad"></div>
<div class="k">Release Point</div>
<h1>How fast does a market price a pitch?</h1>
<div class="n"><b>{half:.1f} seconds</b>median time from a big pitch to the first trade more than halfway to its new price</div>
<svg width="1200" height="630">
  <line x1="{x0}" x2="{x1}" y1="{Y(1):.1f}" y2="{Y(1):.1f}" stroke="#cfc3ad"/>
  <line x1="{x0}" x2="{x1}" y1="{y0}" y2="{y0}" stroke="#847a6c"/>
  <line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{y1 - 20}" y2="{y0}" stroke="#847a6c"/>
  <text x="{X(0) + 8:.1f}" y="{y1 - 6}" class="t">pitch</text>
  <line x1="{x0}" x2="{x1}" y1="{y0 + 14}" y2="{y0 + 14}" stroke="#847a6c"/>{ticks}{labels}
  <polyline points="{pts}" fill="none" stroke="#2a5d9e" stroke-width="4" stroke-linejoin="round"/>
  <text x="{x1}" y="{Y(1) - 10:.1f}" text-anchor="end" class="t">the whole fair move</text>
</svg></body></html>"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "og.html"
        page.write_text(html)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,630",
                        "--virtual-time-budget=4000", f"--screenshot={SITE / 'og.png'}", page.as_uri()],
                       check=True, capture_output=True)
    print("site/og.png written")


if __name__ == "__main__":
    main()
