from functools import lru_cache

from PIL import Image, ImageDraw

SIZE = 160
BACKING = (48, 54, 61, 255)
RING = (110, 118, 129, 255)
RING_WIDTH = 5


def _disc(fill_alpha, size):
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=fill_alpha)
    return mask.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def circle(path):
    img = Image.open(path).convert("RGBA")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), BACKING)
    out.alpha_composite(img)
    ring = Image.new("RGBA", (SIZE, SIZE), RING)
    inner = Image.new("L", (SIZE, SIZE), 0)
    inner.paste(_disc(255, SIZE - RING_WIDTH * 2), (RING_WIDTH, RING_WIDTH))
    out = Image.composite(out, ring, inner)
    out.putalpha(_disc(255, SIZE))
    return out
