"""Inject assets into the page template. Writes biohack/index.html (a full page for GitHub Pages)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
body = (ROOT / "app" / "template.html").read_text().replace(
    "/*ASSETS*/null", (ROOT / "data" / "assets.json").read_text())
head, rest = body.split("<style>", 1)
page = ("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        + head + "<style>" + rest.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")
(ROOT / "index.html").write_text(page)
if len(sys.argv) > 1:  # optional: bare fragment for hosts that add their own <html> skeleton
    Path(sys.argv[1]).write_text(body)
print("wrote", ROOT / "index.html")
