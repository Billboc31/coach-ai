"""Render the repository-owned Coach AI mark. Requires Pillow; no remote assets."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
base = Image.new("RGB", (1024, 1024), "#173f33")
draw = ImageDraw.Draw(base)
# Original pulse/barbell mark, with generous space for the iOS icon mask.
cream = "#eef3df"
draw.line([(184, 532), (328, 532), (410, 348), (506, 676), (602, 462), (666, 532), (840, 532)], fill=cream, width=44, joint="curve")
for x, y in [(184, 532), (840, 532)]:
    draw.ellipse((x-22, y-22, x+22, y+22), fill=cream)
draw.rounded_rectangle((180, 412, 226, 652), radius=20, fill=cream)
draw.rounded_rectangle((798, 412, 844, 652), radius=20, fill=cream)
web = ROOT / "frontend/public/assets/app"
for size in [180, 192, 512]:
    base.resize((size, size), Image.Resampling.LANCZOS).save(web / f"icon-{size}.png")
assets = ROOT / "ios/CoachAI/Assets.xcassets"
(assets / "Contents.json").write_text(json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2)+"\n")
images = []
for points, scale in [(20, 2), (20, 3), (29, 2), (29, 3), (40, 2), (40, 3), (60, 2), (60, 3)]:
    size = points * scale
    name = f"icon-{size}.png"
    base.resize((size, size), Image.Resampling.LANCZOS).save(assets / "AppIcon.appiconset" / name)
    images.append({"idiom": "iphone", "size": f"{points}x{points}", "scale": f"{scale}x", "filename": name})
base.save(assets / "AppIcon.appiconset/icon-1024.png")
images.append({"idiom": "ios-marketing", "size": "1024x1024", "scale": "1x", "filename": "icon-1024.png"})
(assets / "AppIcon.appiconset/Contents.json").write_text(json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2)+"\n")
