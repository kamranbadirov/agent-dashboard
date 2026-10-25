AQUA = "#2dd4bf"
RED = "#f0525a"
BLUE = "#5b8def"
GREEN = "#3fb950"
GRAY = "#8b949e"
INK = "#e6edf3"
MUTED = "#8b949e"

SECTIONS = [
    ("your_move", "Needs you", AQUA),
    ("working", "Running", RED),
    ("reviewing", "Reviewing PRs", BLUE),
    ("in_review", "Waiting on reviewers", GREEN),
    ("done", "Done", GRAY),
    ("ended", "Inactive", GRAY),
]

COLOR = {k: c for k, _, c in SECTIONS}
NAME = {k: n for k, n, _ in SECTIONS}
