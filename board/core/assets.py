from .config import ASSETS_DIR

EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def repo_images():
    """Map a lowercase repo name to its image file in board/assets, e.g. {"pikachu": Path(...)}."""
    if not ASSETS_DIR.is_dir():
        return {}
    return {f.stem.lower(): f for f in sorted(ASSETS_DIR.iterdir()) if f.suffix.lower() in EXTENSIONS}
