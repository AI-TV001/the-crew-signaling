# Europe map – falling countries

`europe_map_fall.mp4` — 1920×1080, 25 fps, 6.00 s (150 frames), H.264 High, BT.709.

- **Background:** solid `#112C4D`
- **Countries:** one map-wide diagonal gradient `#FD0100` → `#C55085` → `#00F0FF`
  (red over Iberia, magenta through central Europe with Poland at the midpoint,
  cyan over western Russia). The gradient is locked to each country's final map
  position, so it rides along with the country as it falls and stitches
  seamlessly once everything has landed.
- **Borders:** 2.2 px `#112C4D` outline on every country.
- **Motion:** each of the 56 countries starts fully above the frame with a
  slight tilt (±9°) and sideways drift, then drops in with an ease-out-cubic
  curve over 2.3 s, straightening as it settles. Countries cascade in roughly
  west → east (with jitter) from 0.0 s to 3.4 s; the last lands at ~5.7 s and
  the finished map holds to 6.0 s. Landed countries always sit on top:
  anything still falling passes behind them. A slow eased 4.5 % push-in runs across the
  whole clip so the camera is never locked off. Adaptive 180° motion blur.
- **Accuracy:** Natural Earth 1:10m admin-0 boundaries, projected in
  ETRS89-LAEA (EPSG:3035), the EU's standard pan-European projection.

`europe_map_final_frame.png` is the lossless final frame.

## Re-render

```bash
pip install numpy pillow shapely pyproj pycairo imageio-ffmpeg
curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson
python3 render.py ne_10m_admin_0_countries.geojson europe_map_fall.mp4
```

Timing, colours, border width, push-in amount and framing are constants at the
top of `render.py`.
