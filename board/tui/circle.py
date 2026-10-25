from functools import lru_cache

from PIL import Image, ImageDraw

SIZE = 160


@lru_cache(maxsize=None)
def circle(path):
    img = Image.open(path).convert("RGBA")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.LANCZOS)
    mask = Image.new("L", (SIZE * 4, SIZE * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, SIZE * 4 - 1, SIZE * 4 - 1), fill=255)
    img.putalpha(mask.resize((SIZE, SIZE), Image.LANCZOS))
    return img
