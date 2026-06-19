"""Build freeport-global-mining-network.png: conservative cleanup (no KPI smearing)."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# Latest user asset (PNG in Cursor workspace assets)
SRC_DEFAULT = Path(
    r"C:\Users\2000137443\.cursor\projects\c-Users-2000137443-Desktop-MiNe\assets\c__Users_2000137443_AppData_Roaming_Cursor_User_workspaceStorage_0857666d882847fddcad502a2a764c0c_images_image-6d8b554e-1431-49f6-86c9-3a7f69b1af4e.png"
)


def _dilate_bool(m: np.ndarray, size: int = 5) -> np.ndarray:
    im = Image.fromarray(m.astype(np.uint8) * 255, mode="L")
    k = size if size % 2 == 1 else size + 1
    return np.array(im.filter(ImageFilter.MaxFilter(k))) > 127


def _crop_frame(a):
    """Trim top white strip (e.g. screenshot heading) and trailing white padding."""
    h, w = a.shape[:2]
    L = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    mid = slice(min(200, w // 5), max(w - 200, (4 * w) // 5))

    yt = 0
    for y in range(28, min(h - 4, 120)):
        blk = L[y : y + 3, mid]
        if blk.size and float(blk.mean()) < 251.85:
            yt = max(0, y - 2)
            break

    yb = h
    while yb > yt + 160 and float(L[yb - 1].mean()) > 252.9 and float(L[yb - 1].min()) > 251.0:
        yb -= 1
    cropped = np.array(a[yt:yb], copy=True)
    return cropped, yt, yb


def _americas_footer_mask(L, X, Y, h, w):
    """One dense caption line only (avoids eating the body paragraph)."""
    m = np.zeros((h, w), dtype=bool)
    x0, x1 = 40, min(384, w - 8)
    best_y = -1
    best_c = 0
    for y in range(int(h * 0.78), min(h - 5, int(h * 0.94))):
        c = int(((L[y, x0:x1] < 93) & (L[y, x0:x1] > 10)).sum())
        if 40 < c < 200 and c > best_c:
            best_c = c
            best_y = y
    if best_y < 0:
        return m
    y0 = max(0, best_y - 2)
    y1 = min(h, best_y + 6)
    m |= (
        (Y >= y0)
        & (Y < y1)
        & (X > x0)
        & (X < x1)
        & (L > 10)
        & (L < 98)
    )
    return m


def process_array(raw: np.ndarray) -> np.ndarray:
    """Remove only overlays/watermarks; avoid broad grey KPI masks."""
    out, _yt, _yb = _crop_frame(raw)
    h, w = out.shape[:2]
    R, G, B = out[..., 0], out[..., 1], out[..., 2]
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)
    chroma = np.zeros_like(mx)
    ok = mx > 1e-3
    chroma[ok] = (mx - mn)[ok] / mx[ok]
    L = 0.299 * R + 0.587 * G + 0.114 * B
    Y, X = np.indices((h, w))

    mask = np.zeros((h, w), dtype=bool)

    # Grasberg corner: saturated red label only
    red = (
        (R > 142)
        & (R > G + 21)
        & (R > B + 21)
        & (Y > 45)
        & (Y < min(h // 2, 220))
        & (X > w // 2 - 80)
    )
    mask |= _dilate_bool(red, 5)

    # Americas "Operational" chip (narrow green/teal badge, detection-based)
    chip = (
        (G > 92)
        & (G > R)
        & (R > 50)
        & (B < G - 12)
        & (Y < h * 58 // 100)
        & (X < w * 43 // 100)
    )
    mask |= _dilate_bool(chip, 3)

    mask |= _americas_footer_mask(L, X, Y, h, w)

    # Footer ribbon: "Dynamic data feed" + "Efficiency" + icons (keep Global scale on the right)
    y_lo = max(0, h - 36)
    bar = (
        (Y >= y_lo)
        & (X >= 72)
        & (X < int(w * 0.765))
        & (L > 14)
        & (L < 152)
    )
    mask |= bar

    # NotebookLM blobs (muted grey-on-light)
    mask |= (
        (Y < min(50, int(h * 0.095)))
        & (X > int(w * 0.942))
        & (chroma < 0.48)
        & (L > 110)
        & (L < 242)
    )
    nook_h = max(36, min(48, int(h * 0.074)))
    mask |= (
        (Y >= h - nook_h)
        & (X > int(w * 0.954))
        & (chroma < 0.48)
        & (L > 65)
        & (L < 235)
    )

    for yy in range(h):
        row = mask[yy]
        if not row.any():
            continue
        if yy >= int(h * 0.895):
            r0, r1 = max(0, int(w * 0.758)), min(w, int(w * 0.868))
        elif int(h * 0.70) <= yy < int(h * 0.92):
            r0, r1 = int(w * 0.50), int(w * 0.70)
        elif yy < int(h * 0.62):
            r0, r1 = max(0, int(w * 0.452)), min(w, int(w * 0.628))
        else:
            r0, r1 = max(0, int(w * 0.392)), min(w, int(w * 0.512))
        r0 = max(0, min(r0, w - 2))
        r1 = max(r0 + 2, min(r1, w))
        ref = out[yy, r0:r1]
        rm = mask[yy, r0:r1]
        if ref.size == 0:
            continue
        safe = ~rm
        if safe.any():
            fill = np.clip(np.median(ref[safe], axis=0), 0, 255)
        else:
            fill = np.clip(np.median(ref, axis=0), 0, 255)
        out[yy][row] = fill

    # Erase residual Notebook corner (hard corner only — map is open ocean there)
    tr_y1 = min(48, h)
    x0, x1 = int(w * 0.944), min(w, int(w * 0.975))
    rg0, rg1 = max(0, int(w * 0.858)), max(4, min(int(w * 0.936), x0))
    if rg1 > rg0 + 12 and x1 > x0 + 8:
        for yy in range(8, tr_y1):
            fill = np.clip(np.median(out[yy, rg0:rg1], axis=0), 0, 255)
            out[yy, x0:x1] = fill

    return out


def main() -> None:
    if not SRC_DEFAULT.exists():
        raise SystemExit(f"Source not found: {SRC_DEFAULT}")

    im = Image.open(SRC_DEFAULT).convert("RGB")
    a = np.asarray(im, dtype=np.float32)
    out_u8 = np.round(process_array(a)).astype(np.uint8)

    root = Path(__file__).resolve().parents[1]
    for folder in ("static/img", "static_site/img"):
        dest = root / folder / "freeport-global-mining-network.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out_u8, mode="RGB").save(dest, optimize=True)
        print("wrote", dest, out_u8.shape[1], "x", out_u8.shape[0])


if __name__ == "__main__":
    main()
