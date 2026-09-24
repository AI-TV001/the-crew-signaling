"""
Europe map assembly animation.

Every country drops in from above the frame and settles smoothly into its
true position on an accurate map of Europe.

  Canvas     1920x1080, 25 fps, 6.0 s (150 frames)
  Background solid #112C4D
  Countries  map-wide gradient #FD0100 -> #C55085 -> #00F0FF
             (the gradient is locked to each country's final map position,
             so it travels with the country as it falls and lines up
             seamlessly once everything has landed)
  Borders    #112C4D outline on every country
  Data       Natural Earth 1:10m admin-0 countries, German point-of-view
             edition (ne_10m_admin_0_countries_deu), which follows the
             internationally recognised (UN / EU) position: Crimea is part
             of Ukraine, the Golan Heights are Syrian (not drawn), Cyprus is
             one country, Kosovo is shown. Map subunits supply England,
             Scotland, Wales and Northern Ireland.
  Projection ETRS89 Lambert Azimuthal Equal-Area (EPSG:3035), the EU's
             standard projection for pan-European maps

Usage: python3 render.py <ne_10m_admin_0_countries_deu.geojson> \
                        <ne_10m_admin_0_map_subunits.geojson> <out.mp4>
"""
import json
import math
import random
import subprocess
import sys

import cairo
import imageio_ffmpeg
import numpy as np
from pyproj import Transformer
from shapely.geometry import box, shape, MultiPolygon, Polygon
from shapely.ops import transform as shp_transform, unary_union

W, H, FPS, SECONDS = 1920, 1080, 25, 6.0
N_FRAMES = int(FPS * SECONDS)
BG = (0x11 / 255, 0x2C / 255, 0x4D / 255)
BORDER = BG
BORDER_PX = 2.2
STOPS = [(0.0, "#FD0100"), (0.5, "#C55085"), (1.0, "#00F0FF")]

# Timing: countries start falling between 0.0s and START_SPREAD, each fall
# lasts FALL_DUR, so the final country lands at ~5.7s and the finished map
# holds for the last ~0.3s of the 6s clip.
FALL_DUR = 2.3
START_SPREAD = 3.4
SHUTTER = 0.5                 # 180-degree shutter
BLUR_STEP_PX = 1.5            # max travel between motion-blur sub-samples
MAX_BLUR_SAMPLES = 48

# Gentle continuous push-in so the camera is never locked-off.
PUSH_START, PUSH_END = 1.0, 1.045

# Every country visible in the frame is drawn. This checklist is the set
# that must be present (the load fails otherwise): every European
# sovereign state plus all 55 UEFA member associations
# (which adds Israel and Kazakhstan, and counts England, Scotland, Wales and
# Northern Ireland as separate countries). Names are Natural Earth ADMIN
# names; the UK home nations come from the map-subunits file.
COUNTRIES = {
    "Albania", "Andorra", "Armenia", "Austria", "Azerbaijan", "Belarus",
    "Belgium", "Bosnia and Herzegovina", "Bulgaria", "Croatia", "Cyprus",
    "Czechia", "Denmark", "Estonia", "Faroe Islands", "Finland", "France",
    "Georgia", "Germany", "Gibraltar", "Greece", "Hungary", "Iceland",
    "Ireland", "Israel", "Italy", "Kazakhstan", "Kosovo", "Latvia",
    "Liechtenstein", "Lithuania", "Luxembourg", "Malta", "Moldova", "Monaco",
    "Montenegro", "Netherlands", "North Macedonia", "Norway", "Poland",
    "Portugal", "Republic of Serbia", "Romania", "Russia", "San Marino",
    "Slovakia", "Slovenia", "Spain", "Sweden", "Switzerland", "Turkey",
    "Ukraine", "Vatican",
    "England", "Scotland", "Wales", "Northern Ireland",
}
UK_NATIONS = {"England", "Scotland", "Wales", "Northern Ireland"}
# Filled with the gradient: the checklist plus the Crown Dependencies.
# Every other country in the frame (North Africa, the Middle East, Central
# Asia, Greenland, Palestine...) is drawn as a gradient outline only.
FILLED = COUNTRIES | {"Isle of Man", "Jersey", "Guernsey"}
OUTLINE_PX = 1.5
OUTLINE_ALPHA = 0.7
# Small areas merged into the country they belong to.
MERGE = {
    "Aland": "Finland",
    "Akrotiri Sovereign Base Area": "Cyprus",
    "Dhekelia Sovereign Base Area": "Cyprus",
    "Cyprus No Mans Area": "Cyprus",
    "Baykonur Cosmodrome": "Kazakhstan",
}

# Every country is drawn at its true outline and scale. Small ones get a
# proportionally thinner border so the outline never swallows the country
# (Andorra, Liechtenstein, Malta, the Faroes...); sub-pixel states
# (Vatican, Monaco, Gibraltar, San Marino) are filled with no border at all.
SMALL_BORDER_REF_PX = 30       # countries narrower than this get thinner borders
MIN_BORDER_SCALE = 0.3
NO_BORDER_BELOW_PX2 = 4

# Map framing in EPSG:3035 metres (x = easting, y = northing).
# Iceland on the left, Russia / Kazakhstan running off the right edge,
# North Cape at the top, Israel (Eilat) at the bottom.
CENTER_X, CENTER_Y = 5_000_000, 3_280_000
MAP_HEIGHT_M = 4_750_000
SCALE = H / MAP_HEIGHT_M       # px per metre


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_out_sine(t):
    return -(math.cos(math.pi * t) - 1) / 2


def load_countries(path, subunits_path):
    feats = [f for f in json.load(open(path))["features"]
             if f["properties"]["ADMIN"] != "United Kingdom"]
    feats += [dict(f, properties=dict(f["properties"],
                                      ADMIN=f["properties"]["SUBUNIT"]))
              for f in json.load(open(subunits_path))["features"]
              if f["properties"]["SUBUNIT"] in UK_NATIONS]
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    to_px = lambda x, y: ((np.asarray(x) - CENTER_X) * SCALE + W / 2,
                          H / 2 - (np.asarray(y) - CENTER_Y) * SCALE)
    # Clip a little beyond the frame so clipped edges never show a border,
    # even at the widest point of the push-in.
    clip = box(-60, -60, W + 60, H + 60)

    groups = {}
    for f in feats:
        name = MERGE.get(f["properties"]["ADMIN"], f["properties"]["ADMIN"])
        g = shape(f["geometry"])
        # Every country that appears anywhere in the frame is drawn, so the
        # map is complete to the edges (North Africa, the Middle East,
        # Central Asia, the Atlantic islands). Pre-clip to a generous
        # lon/lat window before projecting so far-away land (the Americas,
        # East Asia, overseas territories) never wraps into view.
        g = g.intersection(box(-80, -5, 150, 90))
        if g.is_empty:
            continue
        g = shp_transform(lambda x, y, z=None: tr.transform(x, y), g)
        g = shp_transform(lambda x, y, z=None: to_px(x, y), g)
        g = g.intersection(clip)
        if g.is_empty:
            continue
        groups.setdefault(name, []).append(g)

    countries = []
    for name, geoms in groups.items():
        g = unary_union(geoms).simplify(0.35, preserve_topology=True)
        polys = [g] if isinstance(g, Polygon) else list(getattr(g, "geoms", []))
        # Drop specks smaller than ~2 px^2 (but keep micro-states whole).
        keep = [q for q in polys if isinstance(q, Polygon) and q.area > 2.0]
        if not keep:
            keep = [max((q for q in polys if isinstance(q, Polygon)),
                        key=lambda q: q.area)]
        geom = MultiPolygon(keep)
        size = math.sqrt(g.area)
        border = 0.0 if g.area < NO_BORDER_BELOW_PX2 else BORDER_PX * min(
            1.0, max(MIN_BORDER_SCALE, size / SMALL_BORDER_REF_PX))
        countries.append({"name": name, "geom": geom, "border": border,
                          "filled": name in FILLED})
    missing = COUNTRIES - {c["name"] for c in countries}
    assert not missing, f"countries missing from the map: {missing}"
    return countries


def to_px(x, y):
    return (x - CENTER_X) * SCALE + W / 2, H / 2 - (y - CENTER_Y) * SCALE


def build_gradient():
    # Diagonal sweep across the whole map: red in the south-west (Iberia),
    # magenta through central Europe, pure cyan across Russia / Kazakhstan.
    # Endpoints are geographic and span the land, not the frame, so the
    # full red -> cyan range is visible on the countries themselves.
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    (x0, y0), (x1, y1) = [to_px(*tr.transform(lon, lat))
                          for lon, lat in ((-9.0, 37.0), (80.0, 58.0))]
    g = cairo.LinearGradient(x0, y0, x1, y1)
    for off, hx in STOPS:
        g.add_color_stop_rgb(off, *hex_rgb(hx))
    return g


def plan_motion(countries):
    rnd = random.Random(7)
    for c in countries:
        minx, miny, maxx, maxy = c["geom"].bounds
        c["cx"], c["cy"] = (minx + maxx) / 2, (miny + maxy) / 2
    # Cascade roughly west -> east with organic jitter so it reads as a wave
    # of countries raining in rather than a mechanical sweep.
    order = sorted(countries, key=lambda c: c["cx"] + rnd.uniform(-420, 420))
    n = len(order)
    for i, c in enumerate(order):
        c["t0"] = START_SPREAD * (i / max(1, n - 1)) ** 0.9
        maxy = c["geom"].bounds[3]
        # Start fully above the top edge (bottom of the shape off-screen),
        # plus extra height so everything travels a satisfying distance.
        c["drop"] = maxy + 80 + rnd.uniform(0, 220)
        c["rot0"] = math.radians(rnd.uniform(-9, 9))
        c["drift"] = rnd.uniform(-40, 40)
    return countries


def country_offset(c, t):
    p = min(1.0, max(0.0, (t - c["t0"]) / FALL_DUR))
    e = ease_out_cubic(p)
    return c["drift"] * (1 - e), -c["drop"] * (1 - e)


def max_travel(countries, t):
    a, b = t - SHUTTER / FPS / 2, t + SHUTTER / FPS / 2
    best = 0.0
    for c in countries:
        (x0, y0), (x1, y1) = country_offset(c, a), country_offset(c, b)
        best = max(best, math.hypot(x1 - x0, y1 - y0))
    return best


def geom_path(ctx, geom):
    for poly in geom.geoms:
        for ring in [poly.exterior, *poly.interiors]:
            pts = ring.coords
            ctx.move_to(*pts[0])
            for x, y in pts[1:]:
                ctx.line_to(x, y)
            ctx.close_path()


def render_frame(countries, gradient, t):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(*BG)
    ctx.paint()

    # Camera push-in, eased over the whole clip, centred on the map.
    k = PUSH_START + (PUSH_END - PUSH_START) * ease_in_out_sine(t / SECONDS)
    ctx.translate(W / 2, H / 2)
    ctx.scale(k, k)
    ctx.translate(-W / 2, -H / 2)

    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    # Paint landed countries first, then everything still in the air on top,
    # so a falling country always passes over the countries already in place.
    # Among landed countries, outline-only ones paint first so the filled
    # countries' navy borders cover the shared edges cleanly; then large
    # before small so enclaves (Vatican, San Marino) sit on top of Italy.
    for c in sorted(countries, key=lambda c: (-min(1.0, (t - c["t0"]) / FALL_DUR),
                                              c["filled"], -c["geom"].area)):
        p = (t - c["t0"]) / FALL_DUR
        if p <= 0:
            continue
        p = min(1.0, p)
        dx, dy = country_offset(c, t)
        rot = c["rot0"] * (1 - ease_out_cubic(p)) ** 1.5
        ctx.save()
        ctx.translate(c["cx"] + dx, c["cy"] + dy)
        ctx.rotate(rot)
        ctx.translate(-c["cx"], -c["cy"])
        geom_path(ctx, c["geom"])
        # Gradient is defined in final map space, so it moves with the
        # country and stitches seamlessly once it lands.
        if not c["filled"]:
            ctx.push_group()
            ctx.set_source(gradient)
            ctx.set_line_width(OUTLINE_PX / k)
            ctx.stroke()
            ctx.pop_group_to_source()
            ctx.paint_with_alpha(OUTLINE_ALPHA)
            ctx.restore()
            continue
        ctx.set_source(gradient)
        if c["border"]:
            ctx.fill_preserve()
            ctx.set_source_rgb(*BORDER)
            ctx.set_line_width(c["border"] / k)
            ctx.stroke()
        else:
            ctx.fill()
        ctx.restore()

    buf = np.frombuffer(surf.get_data(), np.uint8).reshape(H, surf.get_stride() // 4, 4)
    return buf[:, :W, 2::-1].astype(np.float32)   # BGRx -> RGB


def main():
    src, sub, out = sys.argv[1], sys.argv[2], sys.argv[3]
    countries = plan_motion(load_countries(src, sub))
    print(f"{len(countries)} countries:", ", ".join(sorted(c['name'] for c in countries)))
    gradient = build_gradient()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv",
           "-c:v", "libx264", "-preset", "slow", "-crf", "12",
           "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-color_range", "tv",
           "-movflags", "+faststart", "-r", str(FPS), out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for f in range(N_FRAMES):
        t = f / FPS
        # Enough sub-samples that the fastest country moves <= BLUR_STEP_PX
        # between them, so the blur is a smooth smear with no ghost steps.
        n = max(1, min(MAX_BLUR_SAMPLES,
                       math.ceil(max_travel(countries, t) / BLUR_STEP_PX)))
        acc = np.zeros((H, W, 3), np.float32)
        for s in range(n):
            ts = t + ((s + 0.5) / n - 0.5) * SHUTTER / FPS if n > 1 else t
            acc += render_frame(countries, gradient, max(0.0, ts))
        frame = (acc / n + 0.5).astype(np.uint8)
        proc.stdin.write(frame.tobytes())
        if f in (0, 50, 100, N_FRAMES - 1) and len(sys.argv) > 4:
            from PIL import Image
            Image.fromarray(frame).save(f"{sys.argv[4]}/frame_{f:03d}.png")
    proc.stdin.close()
    proc.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
