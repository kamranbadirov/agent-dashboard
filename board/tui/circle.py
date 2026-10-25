from functools import lru_cache

from PIL import Image, ImageDraw

DIAMETER = 192
BACKING = (48, 54, 61, 255)
RING = (110, 118, 129, 255)
RING_WIDTH = 6


def _disc(size):
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _badge(path):
    img = Image.open(path).convert("RGBA")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((DIAMETER, DIAMETER), Image.LANCZOS)
    out = Image.new("RGBA", (DIAMETER, DIAMETER), BACKING)
    out.alpha_composite(img)
    inner = Image.new("L", (DIAMETER, DIAMETER), 0)
    inner.paste(_disc(DIAMETER - RING_WIDTH * 2), (RING_WIDTH, RING_WIDTH))
    out = Image.composite(out, Image.new("RGBA", (DIAMETER, DIAMETER), RING), inner)
    out.putalpha(_disc(DIAMETER))
    return out


@lru_cache(maxsize=None)
def circle(path, box_w, box_h):
    """A round badge on a transparent canvas with the same pixel shape as the cell box.

    The terminal stretches the picture to fill the cells, so the canvas matches the
    box (width x height in pixels) and the badge stays a true circle.
    """
    k = DIAMETER / min(box_w, box_h)
    canvas = Image.new("RGBA", (round(box_w * k), round(box_h * k)), (0, 0, 0, 0))
    canvas.paste(_badge(path), ((canvas.width - DIAMETER) // 2, (canvas.height - DIAMETER) // 2))
    return canvas
