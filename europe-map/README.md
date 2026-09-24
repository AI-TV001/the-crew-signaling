# Europe map – falling countries

`europe_map_fall.mp4` — 1920×1080, 25 fps, 6.00 s (150 frames), H.264 High, BT.709.

- **Background:** solid `#112C4D`
- **Countries:** one map-wide diagonal gradient `#FD0100` → `#C55085` → `#00F0FF`
  (red over Iberia, magenta through central and south-east Europe, cyan over
  Russia and Kazakhstan). The gradient is locked to each country's final map
  position, so it rides along with the country as it falls and stitches
  seamlessly once everything has landed.
- **Borders:** 2.2 px `#112C4D` outline on every country (thinner on very small ones).
- **Motion:** each country starts fully above the frame with a slight tilt
  (±9°) and sideways drift, then drops in with an ease-out-cubic curve over
  2.3 s, straightening as it settles. Countries cascade in roughly west → east
  (with jitter) from 0.0 s to 3.4 s; the last lands at ~5.7 s and the finished
  map holds to 6.0 s. A falling country always passes **over** countries that
  have already landed. A slow eased 4.5 % push-in runs across the whole clip.
  Adaptive 180° motion blur.
- **Countries (57, checked by an assert in `render.py`):** every European
  sovereign state plus all 55 UEFA members — Albania, Andorra, Armenia,
  Austria, Azerbaijan, Belarus, Belgium, Bosnia and Herzegovina, Bulgaria,
  Croatia, Cyprus, Czechia, Denmark, England, Estonia, Faroe Islands, Finland,
  France, Georgia, Germany, Gibraltar, Greece, Hungary, Iceland, Ireland,
  Israel, Italy, Kazakhstan, Kosovo, Latvia, Liechtenstein, Lithuania,
  Luxembourg, Malta, Moldova, Monaco, Montenegro, Netherlands, North
  Macedonia, Northern Ireland, Norway, Poland, Portugal, Romania, Russia,
  San Marino, Scotland, Serbia, Slovakia, Slovenia, Spain, Sweden,
  Switzerland, Turkey, Ukraine, Vatican, Wales. Isle of Man, Jersey, Guernsey
  and Palestine are also drawn so the map has no holes.
- **Accuracy:** Natural Earth 1:10m boundaries, German point-of-view edition,
  which follows the internationally recognised (UN / EU) position: Crimea is
  Ukrainian, the Golan Heights are Syrian (not drawn), Cyprus is one country,
  Kosovo is shown. Projected in ETRS89-LAEA (EPSG:3035), the EU's standard
  pan-European projection. Every country is at its true outline and scale; small
  countries get a proportionally thinner border so it never swallows them, and
  Vatican, Monaco, Gibraltar and San Marino (under 3 px² at this scale) are
  filled with no border.

`europe_map_final_frame.png` is the lossless final frame.

## Re-render

```bash
pip install numpy pillow shapely pyproj pycairo imageio-ffmpeg
curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries_deu.geojson
curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_map_subunits.geojson
python3 render.py ne_10m_admin_0_countries_deu.geojson ne_10m_admin_0_map_subunits.geojson europe_map_fall.mp4
```

Timing, colours, border width, push-in amount and framing are constants at the
top of `render.py`.
