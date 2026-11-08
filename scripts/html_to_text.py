"""Convert a saved HTML page of code text to plain text for the source snapshots.

One line per block element, whitespace collapsed, and each table row kept on a single
line with cells separated by " | " so that table values can be quoted.

    python scripts/html_to_text.py page.html out.txt
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser

BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "table", "section"}
BLOCK |= {"figcaption", "caption", "dt", "dd", "ul", "ol"}
SKIP = {"script", "style", "nav", "svg", "noscript"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.row = 0

    def _break(self, tag: str) -> None:
        # Inside a table row only the row itself starts a new line.
        if tag in BLOCK and (self.row == 0 or tag == "tr"):
            self.out.append("\n")
        elif tag in BLOCK:
            self.out.append(" ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP:
            self.skip += 1
        self._break(tag)
        if tag == "tr":
            self.row += 1
        if tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP and self.skip:
            self.skip -= 1
        if tag == "tr" and self.row:
            self.row -= 1
        self._break(tag)

    def handle_data(self, data: str) -> None:
        if not self.skip:
            # Line breaks in the HTML source are not line breaks in the text.
            self.out.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(parser.out).split("\n"))
    return "\n".join(line for line in lines if line) + "\n"


if __name__ == "__main__":
    source, target = sys.argv[1], sys.argv[2]
    with open(source, encoding="utf-8") as f:
        text = html_to_text(f.read())
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
