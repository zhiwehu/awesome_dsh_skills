#!/usr/bin/env python3
"""Generic picture-book PDF assembler: full-bleed pages with optional margin style.

Usage:
  python3 make_book_pdf.py --title "The Bench" --out The-Bench.pdf \
      --pages bench-cover.png,bench-p1.png,bench-p2.png,bench-p3.png,bench-p4.png,bench-p5.png \
      --gutter 84 --bg "#181614" --rounded

#181614 is the near-black horror-comic gutter; for the warm Bench book use #F0E6D2.
"""
import argparse, os
from PIL import Image, ImageDraw

def parse_color(s):
    s = s.strip().lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", required=True, help="comma-separated page files")
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--gutter", type=int, default=36)
    ap.add_argument("--bg", default="#181614")
    ap.add_argument("--rounded", action="store_true", help="draw a thin cream border")
    args = ap.parse_args()

    BG = parse_color(args.bg)
    BORDER = parse_color("#F0E6D2")
    pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    out_pages = []
    for img_file in pages:
        img = Image.open(os.path.join(args.dir, img_file)).convert("RGB")
        iw, ih = img.size
        gw = args.gutter
        page = Image.new("RGB", (iw + 2 * gw, ih + 2 * gw), BG)
        page.paste(img, (gw, gw))
        if args.rounded:
            d = ImageDraw.Draw(page)
            d.rectangle([gw, gw, gw + iw - 1, gw + ih - 1], outline=BORDER, width=2)
        out_pages.append(page)
    out_path = os.path.join(args.dir, args.out)
    out_pages[0].save(out_path, save_all=True, append_images=out_pages[1:],
                      resolution=144.0, title=args.title)
    print("saved", out_path, "pages:", len(out_pages))

if __name__ == "__main__":
    main()