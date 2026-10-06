#!/usr/bin/python3
"""Generate the Nav2 occupancy image matching worlds/rm_arena.sdf."""

from pathlib import Path
import sys

from PIL import Image, ImageDraw


RESOLUTION = 0.10
WIDTH_METERS = 28.0
HEIGHT_METERS = 15.0


def pixel(x, y):
    return (int(round(x / RESOLUTION)), int(round((HEIGHT_METERS - y) / RESOLUTION)))


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1] / "maps/arena.pgm"
    output.parent.mkdir(parents=True, exist_ok=True)
    width = int(round(WIDTH_METERS / RESOLUTION))
    height = int(round(HEIGHT_METERS / RESOLUTION))
    image = Image.new("L", (width, height), 254)
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=2)
    for x, y, radius in ((1.0, 7.5, 0.72), (8.0, 7.5, 0.52),
                         (20.0, 7.5, 0.52), (27.0, 7.5, 0.72)):
        cx, cy = pixel(x, y)
        r = int(round(radius / RESOLUTION))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)

    enemy_positions = (
        (26.931, 6.945), (25.796, 8.755), (24.961, 9.131),
        (24.616, 8.549), (26.658, 2.094), (25.186, 6.675),
    )
    half_x = int(round(0.325 / RESOLUTION))
    half_y = int(round(0.250 / RESOLUTION))
    for x, y in enemy_positions:
        cx, cy = pixel(x, y)
        draw.rectangle((cx - half_x, cy - half_y, cx + half_x, cy + half_y), fill=0)

    image.save(output, format="PPM")
    print(f"generated {output} ({width}x{height}, {RESOLUTION:.2f} m/cell)")


if __name__ == "__main__":
    main()
