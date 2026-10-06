"""Regenerate the small original Little Atlas book-and-leaf icon."""

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    assets = Path(__file__).resolve().parent.parent / "dictionary_app" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 492, 492), radius=110, fill="#476b52")
    draw.rounded_rectangle((44, 44, 468, 468), radius=88, outline="#759980", width=8)

    # Two open pages, with a narrow center seam.
    draw.polygon([(97, 159), (238, 179), (256, 198), (256, 390), (237, 373),
                  (97, 351)], fill="#fbf8e9")
    draw.polygon([(256, 198), (274, 179), (415, 159), (415, 351), (275, 373),
                  (256, 390)], fill="#f4f0dc")
    draw.line([(256, 198), (256, 390)], fill="#93a798", width=8)
    draw.line([(119, 209), (221, 224)], fill="#b0c5b5", width=9)
    draw.line([(119, 245), (221, 260)], fill="#b0c5b5", width=9)
    draw.line([(291, 224), (393, 209)], fill="#b0c5b5", width=9)
    draw.line([(291, 260), (393, 245)], fill="#b0c5b5", width=9)

    # A single leaf indicates small discoveries growing over time.
    draw.ellipse((184, 81, 318, 185), fill="#d7b675")
    draw.line([(251, 186), (251, 124)], fill="#466b50", width=8)
    draw.arc((186, 85, 315, 190), 208, 330, fill="#eed7a0", width=7)

    image.save(assets / "little-atlas.png")
    image.save(assets / "little-atlas.ico", sizes=[(16, 16), (24, 24), (32, 32),
                                                   (48, 48), (64, 64), (128, 128),
                                                   (256, 256)])


if __name__ == "__main__":
    main()
