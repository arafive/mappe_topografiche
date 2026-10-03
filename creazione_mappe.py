
from pyproj import Transformer
import contextily.plotting as _cp
import contextily as ctx
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import math
import re
import time
import requests
import matplotlib.patheffects as pe
from adjustText import adjust_text
import numpy as np
import matplotlib
matplotlib.use("Agg")
UA = "mappe_topografiche/1.0 (uso personale; lacaselladidaniele@gmail.com)"
ctx.tile.USER_AGENT = UA

if not getattr(requests.sessions.Session.request, "_ua_patched", False):
    _req_orig = requests.sessions.Session.request

    def _req_ua(self, method, url, **kw):
        h = dict(kw.get("headers") or {})
        h["User-Agent"] = UA
        kw["headers"] = h
        return _req_orig(self, method, url, **kw)

    _req_ua._ua_patched = True
    requests.sessions.Session.request = _req_ua


def _patch_bounds2img(orig):
    def wrapper(*a, **kw):
        kw.setdefault("n_connections", N_CONN)  # download paralleli
        if BASE == "osm":
            kw["use_cache"] = False
        return orig(*a, **kw)
    wrapper._patched = True
    return wrapper


if not getattr(_cp.bounds2img, "_patched", False):
    _cp.bounds2img = _patch_bounds2img(_cp.bounds2img)


def gp(s, asse):
    """Legge "38°06'N", "13°31'E", "38 6 N", "13°18.6'E" -> gradi decimali (S e W negativi)."""
    m = re.fullmatch(r"\s*(\d{1,3})\s*[°:\s]\s*(?:(\d{1,2}(?:[.,]\d+)?)\s*['′’:\s]?\s*"
                     r"(?:(\d{1,2}(?:[.,]\d+)?)\s*(?:\"|″|”|'')?)?)?\s*([NSEWnsew])\s*", s)
    if not m:
        raise SystemExit(
            f"Formato non valido: {s!r} (usa es. \"38°06′22.71″N\")")
    g = int(m.group(1))
    p = float((m.group(2) or "0").replace(",", "."))
    sec = float((m.group(3) or "0").replace(",", "."))
    h = m.group(4).upper()
    if p >= 60 or sec >= 60 or h not in ("NS" if asse == "lat" else "EW"):
        raise SystemExit(f"Valore non valido per {asse}: {s!r}")
    v = g + p / 60 + sec / 3600
    return -v if h in "SW" else v


def gps_file(v, asse):
    """Coordinate in gradi primi secondi adatte a un nome di file, es. 45d08m10sN."""
    h = ("N" if v >= 0 else "S") if asse == "lat" else ("E" if v >= 0 else "W")
    tot = round(abs(v) * 3600)
    return f"{tot // 3600}d{tot % 3600 // 60:02d}m{tot % 60:02d}s{h}"


# ============================================================
# CONFIGURAZIONE
# ============================================================
# 45°08'10.86"N 7°03'21.74"E
# -> Trovali con Google Earth
LAT = gp("46°30′25.00″N", "lat")    # centro mappa, gradi primi secondi; N | S
LON = gp("11°34′30.00″E", "lon")    # centro mappa, gradi primi secondi; E | W
BASE = "opentopomap"                # opentopomap | osm | cyclosm | satellite
# lista, anche vuota []: hillshade | sentieri
OVERLAY = ["hillshade", "sentieri"]
PAGINA = "A4"                       # A4 | A3
NOMI = True                         # scrive città, paesi e montagne in evidenza
VERTICALE = False                   # True = pagina in verticale
DPI = 500
# zoom del layer base: 14 = testi grandi, 15 = compromesso, 16 = molto dettagliato; None = automatico
ZOOM_TILE = 15
# declinazione magnetica in gradi (est positiva); None per non disegnarla
DEC = 3.5
BN = True                           # True = tutto in scala di grigi/nero, nessun colore
COL_GRAT = "black" if BN else "#1f4e9c"
LS_GRAT = "--" if BN else "-"       # in B/N la graticola è tratteggiata
N_CONN = 2 if BASE == "osm" else 4  # OSM consente al massimo 2 connessioni
OUT = f"test_{PAGINA}_{BASE}_{gps_file(LAT, 'lat')}_{gps_file(LON, 'lon')}.pdf"
SCALA = 25_000                       # denominatore della scala
# ============================================================

PAGINE = {"A4": (297, 210), "A3": (420, 297)}  # mm, orizzontale

LAYER = {
    "opentopomap": dict(
        url="https://tile.opentopomap.org/{z}/{x}/{y}.png",
        maxzoom=17, alpha=1.0,
        attr="© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors"),
    "osm": dict(
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        maxzoom=19, alpha=1.0,
        attr="© OpenStreetMap contributors"),
    "cyclosm": dict(
        url="https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
        maxzoom=18, alpha=1.0,
        attr="© CyclOSM, © OpenStreetMap contributors"),
    "satellite": dict(
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        maxzoom=19, alpha=1.0,
        attr="Esri World Imagery"),
    "hillshade": dict(
        url="https://services.arcgisonline.com/arcgis/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
        maxzoom=16, alpha=0.45,
        attr="Esri World Hillshade"),
    "sentieri": dict(
        url="https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png",
        maxzoom=18, alpha=0.9,
        attr="© Waymarked Trails"),
}


def epsg_utm(lat, lon):
    zona = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zona, zona


def zoom_per_scala(lat, dpi):
    risoluzione = SCALA * 0.0254 / dpi  # metri per pixel sulla stampa
    z = math.ceil(
        math.log2(156543.03 * math.cos(math.radians(lat)) / risoluzione))
    return max(1, z)


def fmt_gp(v, asse):
    h = ("N" if v >= 0 else "S") if asse == "lat" else ("E" if v >= 0 else "W")
    tot = round(abs(v) * 60)
    return f"{tot // 60}°{tot % 60:02d}'{h}"


def disegna_reticolato(ax, cx, cy, xmin, xmax, ymin, ymax, k):
    """Reticolato quadrato con maglia 1 km, centrato sul punto (cx, cy). Etichette: km dal centro."""
    s = 1000 * k  # 1 km sul terreno in unità Web Mercator
    col = "#000000"

    for i in range(math.ceil((xmin - cx) / s), math.floor((xmax - cx) / s) + 1):
        x = cx + i * s
        ax.plot([x, x], [ymin, ymax], color=col, lw=0.4, alpha=0.7, zorder=9)

    for j in range(math.ceil((ymin - cy) / s), math.floor((ymax - cy) / s) + 1):
        y = cy + j * s
        ax.plot([xmin, xmax], [y, y], color=col, lw=0.4, alpha=0.7, zorder=9)


def disegna_graticola(ax, epsg, xmin, xmax, ymin, ymax):
    """Meridiani e paralleli ogni 1', con etichette in gradi e primi sui bordi."""
    inv = Transformer.from_crs(epsg, 4326, always_xy=True)
    fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    lons, lats = inv.transform([xmin, xmax, xmin, xmax], [
                               ymin, ymin, ymax, ymax])
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    kw = dict(fontsize=9, annotation_clip=False, textcoords="offset points")

    def et(m):
        return f"{abs(m) // 60}°{abs(m) % 60:02d}'"

    # meridiani (lon costante)
    la = np.linspace(lat0 - 0.01, lat1 + 0.01, 60)
    for m in range(math.ceil(lon0 * 60), math.floor(lon1 * 60) + 1):
        x, y = fwd.transform(np.full_like(la, m / 60), la)
        ax.plot(x, y, color=COL_GRAT, ls=LS_GRAT, lw=0.35, alpha=0.8, zorder=9)
        xb = np.interp(ymin, y, x)
        if xmin < xb < xmax:
            ax.annotate(et(m), (xb, ymin), xytext=(
                0, -3), ha="center", va="top", **kw)

    # paralleli (lat costante)
    lo = np.linspace(lon0 - 0.01, lon1 + 0.01, 60)
    for m in range(math.ceil(lat0 * 60), math.floor(lat1 * 60) + 1):
        x, y = fwd.transform(lo, np.full_like(lo, m / 60))
        ax.plot(x, y, color=COL_GRAT, ls=LS_GRAT, lw=0.35, alpha=0.8, zorder=9)
        yl = np.interp(xmin, x, y)
        if ymin < yl < ymax:
            ax.annotate(et(m), (xmin, yl), xytext=(-3, 0),
                        ha="right", va="center", rotation=90, **kw)


# categoria: (corpo in pt, peso, colore)  <- qui regoli le dimensioni
STILI = {
    "city":    (10, "bold",   "black"),
    "town":    (9, "bold",   "black"),
    "village": (6.5, "normal", "black"),
    "hamlet":  (5.5, "normal",  "black"),
    "peak":    (5.5, "bold", "black" if BN else "#6b2e0a"),
}


def scarica_nomi(xmin, xmax, ymin, ymax):
    inv = Transformer.from_crs(3857, 4326, always_xy=True)
    lon0, lat0 = inv.transform(xmin, ymin)
    lon1, lat1 = inv.transform(xmax, ymax)
    bbox = f"{lat0},{lon0},{lat1},{lon1}"
    q = f"""[out:json][timeout:30];
(
  nwr["natural"="peak"]["name"]({bbox});
  nwr["place"~"^(city|town|village|hamlet)$"]["name"]({bbox});
);
out center tags;"""
    server = ["https://overpass-api.de/api/interpreter",
              "https://overpass.private.coffee/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter"]
    for tentativo in range(3):
        for url in server:
            try:
                r = requests.post(url, data={"data": q},
                                  headers={"User-Agent": "mappa_25k/1.0"}, timeout=60)
                r.raise_for_status()
                return r.json()["elements"]
            except Exception as e:
                print(f"Overpass {url.split('/')[2]}: {e}")
        time.sleep(5 * (tentativo + 1))
    print("Nomi non scaricati")
    return []


def disegna_nomi(ax, elementi, xmin, xmax, ymin, ymax, k, dmin=250, massimo=60):
    fwd = Transformer.from_crs(4326, 3857, always_xy=True)
    ordine = {"city": 0, "peak": 1, "town": 2, "village": 3, "hamlet": 4}
    voci = []
    for e in elementi:
        t = e.get("tags", {})
        la = e.get("lat", e.get("center", {}).get("lat"))
        lo = e.get("lon", e.get("center", {}).get("lon"))
        if la is None or lo is None or "name" not in t:
            continue
        cat = "peak" if t.get("natural") == "peak" else t.get("place")
        if cat not in STILI:
            continue
        x, y = fwd.transform(lo, la)
        if not (xmin < x < xmax and ymin < y < ymax):
            continue
        try:
            q = float(str(t.get("ele", "")).replace(",", ".").split()[0])
        except (ValueError, IndexError):
            q = None
        voci.append((ordine[cat], -(q or 0), cat, t["name"], q, x, y))
    voci.sort(key=lambda v: (v[0], v[1]))

    messi = []
    testi, xs, ys = [], [], []
    for _, _, cat, nome, q, x, y in voci:
        if len(messi) >= massimo:
            break
        if any((x - a) ** 2 + (y - b) ** 2 < (dmin * k) ** 2 for a, b in messi):
            # evita sovrapposizioni (le categorie maggiori hanno la precedenza)
            continue
        messi.append((x, y))
        pt, peso, col = STILI[cat]
        if cat == "peak":
            ax.plot(x, y, "^", color=col, ms=4, zorder=12)
            nome = f"{nome}\n{q:.0f} m" if q else nome
        t = ax.text(x + 60 * k, y + 40 * k, nome, fontsize=pt, weight=peso, color=col,
                    zorder=13, clip_on=True,
                    path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
        testi.append(t)
        xs.append(x)
        ys.append(y)

    if testi:
        adjust_text(testi, x=xs, y=ys, ax=ax,
                    expand=(1.3, 1.6),
                    arrowprops=dict(arrowstyle="-", color="black", lw=0.4))


def crea_mappa(lat, lon, base, overlays, pagina, verticale, dpi, dec, out):
    epsg = 3857
    k = 1 / math.cos(math.radians(lat))  # correzione di scala del Web Mercator
    cx, cy = Transformer.from_crs(
        4326, epsg, always_xy=True).transform(lon, lat)

    w_mm, h_mm = PAGINE[pagina]
    if verticale:
        w_mm, h_mm = h_mm, w_mm
    m_lat, m_alto, m_basso = 8, 12, 8
    map_w, map_h = w_mm - 2 * m_lat, h_mm - m_alto - m_basso

    # estensione in metri sul terreno (1 mm sulla carta = 25 m)
    half_w = map_w / 1000 * SCALA / 2 * k
    half_h = map_h / 1000 * SCALA / 2 * k
    xmin, xmax, ymin, ymax = cx - half_w, cx + half_w, cy - half_h, cy + half_h

    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4))
    ax = fig.add_axes([m_lat / w_mm, m_basso / h_mm,
                      map_w / w_mm, map_h / h_mm])
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    z = zoom_per_scala(lat, dpi)
    attribuzioni = []
    for nome in [base] + list(overlays):
        L = LAYER[nome]
        zz = ZOOM_TILE if (nome == base and ZOOM_TILE) else z
        ctx.add_basemap(ax, source=L["url"], crs=f"EPSG:{epsg}",
                        zoom=min(zz, L["maxzoom"]), attribution=False,
                        alpha=L["alpha"])
        attribuzioni.append(L["attr"])

    if BN:
        for im in ax.images:
            a = np.asarray(im.get_array())
            if a.ndim == 3 and a.shape[2] >= 3:
                g = (0.299 * a[..., 0] + 0.587 * a[..., 1] +
                     0.114 * a[..., 2]).astype(a.dtype)
                b = a.copy()
                b[..., 0] = b[..., 1] = b[..., 2] = g
                im.set_data(b)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")

    # graticola geografica 1' (con etichette) + reticolato quadrato 1 km (senza etichette)
    ax.set_xticks([])
    ax.set_yticks([])
    disegna_graticola(ax, epsg, xmin, xmax, ymin, ymax)
    disegna_reticolato(ax, cx, cy, xmin, xmax, ymin, ymax, k)

    if NOMI:
        disegna_nomi(ax, scarica_nomi(xmin, xmax, ymin, ymax),
                     xmin, xmax, ymin, ymax, k)

    # barra della scala fuori dal plot, in alto a destra (1 km = 40 mm sulla carta)
    bar_w, bar_h = 40, 2.5                       # mm
    axb = fig.add_axes([(w_mm - m_lat - bar_w - 4) / w_mm, (h_mm - 11) / h_mm,
                        bar_w / w_mm, bar_h / h_mm])
    axb.set_xlim(0, bar_w)
    axb.set_ylim(0, bar_h)
    axb.axis("off")
    for i in range(5):
        axb.add_patch(Rectangle((i * 8, 0), 8, bar_h,
                                fc="black" if i % 2 == 0 else "white",
                                ec="black", lw=0.5, clip_on=False))
    L_m = bar_w * SCALA / 1000          # metri sul terreno rappresentati dalla barra

    def fm(m):
        return f"{m / 1000:g} km" if m >= 1000 else f"{m:g} m"

    axb.text(0, bar_h + 0.8, "0", fontsize=9, ha="center", va="bottom")
    axb.text(20, bar_h + 0.8, fm(L_m / 2), fontsize=9, ha="center", va="bottom")
    axb.text(40, bar_h + 0.8, fm(L_m), fontsize=9, ha="center", va="bottom")

    # nord magnetico nel titolo: NM = N + declinazione (segno incluso)
    nm = ""
    if dec is not None:
        nm = f"   |   NM = N {'+' if dec >= 0 else '-'} {abs(dec):.1f}°"

    fig.text(m_lat / w_mm, 1 - 7 / h_mm,
             f"Mercatore WGS84   |   Scala 1:{SCALA} (1 cm = {SCALA / 100:g} m)   |   Graticola 1' ({'tratteggio' if BN else 'blu'})   |   Reticolato 1 km (nero){nm}",
             fontsize=10, va="center")

    fig.savefig(out, dpi=dpi)
    print(
        f"Salvato {out} (area {2 * half_w / k / 1000:.2f} x {2 * half_h / k / 1000:.2f} km)")


if __name__ == "__main__":
    if BASE not in ("opentopomap", "osm", "cyclosm", "satellite"):
        raise SystemExit(f"BASE non valida: {BASE!r}")
    for o in OVERLAY:
        if o not in ("hillshade", "sentieri"):
            raise SystemExit(f"OVERLAY non valido: {o!r}")
    if PAGINA not in PAGINE:
        raise SystemExit(f"PAGINA non valida: {PAGINA!r}")
    crea_mappa(LAT, LON, BASE, OVERLAY, PAGINA, VERTICALE, DPI, DEC, OUT)

