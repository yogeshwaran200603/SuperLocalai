"""
Generate SuperLocal application icon (ICO & PNG).
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def generate_icons():
    assets_dir = Path("assets")
    assets_dir.mkdir(parents=True, exist_ok=True)

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer circle with Fluent Blue gradient-like aesthetic
    margin = 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(0, 120, 212, 255), outline=(255, 255, 255, 220), width=6)

    # Inner decorative accent ring
    draw.ellipse([margin + 16, margin + 16, size - margin - 16, size - margin - 16], outline=(16, 185, 129, 180), width=3)

    # Draw "SL" text in center
    try:
        font = ImageFont.truetype("arialbd.ttf", 100)
    except Exception:
        font = ImageFont.load_default()

    # Draw centered text "SL"
    bbox = draw.textbbox((0, 0), "SL", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) / 2
    ty = (size - th) / 2 - 12
    draw.text((tx, ty), "SL", fill=(255, 255, 255, 255), font=font)

    # Save PNG
    png_path = assets_dir / "icon.png"
    img.save(png_path, "PNG")
    print(f"Saved {png_path}")

    # Save multi-size ICO
    ico_path = assets_dir / "icon.ico"
    img.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Saved {ico_path}")

if __name__ == "__main__":
    generate_icons()
