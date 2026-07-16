"""Apply rounded corners to the app icon and regenerate ICO.

Reads src/icon/icon.jpg (1024x1024 RGB), applies a rounded-rectangle mask so
corners become transparent, then writes:

- src/icon/icon.png    — 1024x1024 master with transparency
- src/icon/icon.ico    — multi-resolution ICO (16..256) for Windows

The ICO is built manually (binary format with embedded PNGs) because Pillow
12.x's ``sizes`` kwarg for ICO save doesn't reliably produce multi-frame ICOs.

Usage:
    python scripts/round_icon_corners.py [--radius R]
"""

from __future__ import annotations

import argparse
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "src" / "icon"
SRC = ICON_DIR / "icon.jpg"
DST_PNG = ICON_DIR / "icon.png"
DST_ICO = ICON_DIR / "icon.ico"

# Typical ICO resolutions Windows uses in various contexts.
SIZES = [16, 24, 32, 48, 64, 128, 256]


# ---------------------------------------------------------------------------
# ICO binary writer
# ---------------------------------------------------------------------------

def _png_bytes(img: Image.Image) -> bytes:
    """Encode *img* (RGBA) as PNG bytes in memory."""
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def write_ico(images: list[Image.Image], path: Path) -> None:
    """Write a multi-resolution ICO file.

    Each image in *images* is embedded as a PNG frame (32-bit RGBA).  The
    images should already have the desired sizes.
    """
    frames: list[bytes] = [_png_bytes(im) for im in images]

    # ICO header: reserved(2) + type(2, 1=ICO) + count(2)
    header = struct.pack("<HHH", 0, 1, len(frames))

    # Build the directory entries *and* compute data offsets.
    dir_entries: list[bytes] = []
    # offset starts after header + directory
    offset = 6 + 16 * len(frames)

    for im, data in zip(images, frames):
        w, h = im.size
        # 0 means 256 in ICO directory fields (both width and height)
        w_byte = w if w < 256 else 0
        h_byte = h if h < 256 else 0
        entry = struct.pack(
            "<BBBBHHII",
            w_byte,  # bWidth
            h_byte,  # bHeight
            0,        # bColorCount (0 = no palette)
            0,        # bReserved
            1,        # wPlanes
            32,       # wBitCount
            len(data), # dwBytesInRes
            offset,   # dwImageOffset
        )
        dir_entries.append(entry)
        offset += len(data)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(header)
        for entry in dir_entries:
            f.write(entry)
        for data in frames:
            f.write(data)


# ---------------------------------------------------------------------------
# Rounded-corners logic
# ---------------------------------------------------------------------------

def make_rounded_icon(
    src: Path,
    dst_png: Path,
    dst_ico: Path,
    radius: int = 120,
) -> None:
    """Create a rounded-corner PNG master + multi-size ICO."""
    img = Image.open(src).convert("RGBA")

    # Build mask with Pillow's rounded_rectangle (available since Pillow 8.2)
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (0, 0, img.width - 1, img.height - 1),
        radius=radius,
        fill=255,
    )

    # Apply mask to alpha channel
    r, g, b, a = img.split()
    a = Image.composite(a, Image.new("L", img.size, 0), mask)
    rounded = Image.merge("RGBA", (r, g, b, a))

    # Save PNG master (1024x1024)
    rounded.save(dst_png, "PNG", optimize=True)
    print(f"OK  Wrote {dst_png}")

    # Build multi-size ICO
    ico_images = [
        rounded.resize((s, s), Image.LANCZOS) for s in SIZES
    ]
    write_ico(ico_images, dst_ico)
    sizes_str = ", ".join(f"{s}x{s}" for s in SIZES)
    print(f"OK  Wrote {dst_ico}  ({sizes_str})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Round icon corners")
    parser.add_argument(
        "--radius",
        type=int,
        default=120,
        help="Corner radius in pixels (default: 120 for 1024x1024 canvas)",
    )
    args = parser.parse_args()

    make_rounded_icon(SRC, DST_PNG, DST_ICO, radius=args.radius)
    print("Done.")


if __name__ == "__main__":
    main()
