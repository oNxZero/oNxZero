#!/usr/bin/env python3
"""Compile the checked-in fonts into outlines used by the SVG renderer.

Requires fonttools for this one-time build. Daily profile refreshes use only the
generated atlas and the Python standard library.
"""
import json
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = "".join(chr(code) for code in range(32, 127)) + "·•→–—’‘“”×©®"
FONTS = {
    "sans-regular": ("SpaceGrotesk.ttf", "Space Grotesk", 400),
    "sans-semibold": ("SpaceGrotesk.ttf", "Space Grotesk", 600),
    "sans-bold": ("SpaceGrotesk.ttf", "Space Grotesk", 700),
    "mono-medium": ("JetBrainsMono.ttf", "JetBrains Mono", 500),
}


def number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def main():
    atlas = {}
    for key, (filename, family, weight) in FONTS.items():
        source = TTFont(ROOT / "assets" / "fonts" / filename)
        font = instantiateVariableFont(source, {"wght": weight})
        glyphs = font.getGlyphSet()
        cmap = font.getBestCmap()
        outlines = {}
        for character in CHARACTERS:
            name = cmap.get(ord(character))
            if name is None:
                continue
            pen = SVGPathPen(glyphs, ntos=number)
            glyphs[name].draw(pen)
            outlines[character] = {"path": pen.getCommands(), "advance": glyphs[name].width}
        atlas[key] = {"family": family, "weight": weight,
                      "units": font["head"].unitsPerEm, "glyphs": outlines}
    target = ROOT / "assets" / "fonts" / "atlas.json"
    target.write_text(json.dumps(atlas, separators=(",", ":"))+"\n")
    print(f"Compiled {len(atlas)} font styles into {target.name}.")


if __name__ == "__main__":
    main()
