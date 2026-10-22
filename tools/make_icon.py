"""Regenerates the fox icon (branding/ and app/assets/). Needs: pip install pillow"""
from PIL import Image, ImageDraw, ImageFilter
S = 4          # supersample
N = 1024
W = N * S

def P(pts):
    return [(x * S, y * S) for x, y in pts]

img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

ORANGE = (255, 122, 26, 255)
ORANGE_D = (222, 88, 10, 255)
BROWN = (58, 28, 12, 255)
CREAM = (255, 244, 230, 255)

# ears (outer)
d.polygon(P([(110, 70), (430, 300), (120, 520)]), fill=ORANGE_D)
d.polygon(P([(914, 70), (594, 300), (904, 520)]), fill=ORANGE_D)
# ears (inner)
d.polygon(P([(190, 200), (370, 330), (180, 440)]), fill=BROWN)
d.polygon(P([(834, 200), (654, 330), (844, 440)]), fill=BROWN)
# head
d.polygon(P([(90, 470), (200, 250), (512, 200), (824, 250), (934, 470),
             (800, 760), (512, 975), (224, 760)]), fill=ORANGE)
# white cheeks / muzzle
d.polygon(P([(90, 470), (330, 640), (512, 600), (694, 640), (934, 470),
             (800, 760), (512, 975), (224, 760)]), fill=CREAM)
# forehead blaze (lighter orange)
d.polygon(P([(512, 230), (640, 330), (512, 470), (384, 330)]), fill=(255, 150, 60, 255))
# eyes
d.polygon(P([(300, 560), (420, 585), (330, 640), (270, 600)]), fill=BROWN)
d.polygon(P([(724, 560), (604, 585), (694, 640), (754, 600)]), fill=BROWN)
# nose
d.polygon(P([(440, 830), (584, 830), (512, 905)]), fill=BROWN)
# bold M on the forehead
def M(cx, cy, w, h, t, col):
    pts = [(cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 2), (cx, cy + h * 0.1),
           (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2)]
    pts = [(x * S, y * S) for x, y in pts]
    d.line(pts, fill=col, width=int(t * S), joint="curve")
    r = t * S / 2
    for x, y in (pts[0], pts[-1], pts[1], pts[3]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=col)
M(512, 405, 190, 150, 44, BROWN)

img = img.resize((N, N), Image.LANCZOS)
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(f"{ROOT}/branding", exist_ok=True)
os.makedirs(f"{ROOT}/app/assets", exist_ok=True)
img.save(f"{ROOT}/branding/moxy_1024.png")
for s in (256, 64, 40):
    img.resize((s, s), Image.LANCZOS).save(f"{ROOT}/app/assets/moxy_{s}.png")
img.save(f"{ROOT}/app/assets/moxy.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
