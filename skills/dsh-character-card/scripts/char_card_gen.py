#!/usr/bin/env python3
"""dsh-character-card — generate a character design sheet from one character image.

Given ANY image containing a character, produce a character card (角色卡):
front / side / back / 45-degree full-body views, a row of facial expressions,
and detail crops (accessories, shoes, signature items) — identity-locked to the
input image via ComfyUI reference mode (TextEncodeQwenImageEdit).

Usage:
  python3 char_card_gen.py <character_image> [--out DIR] [--name NAME]
      [--style STYLE] [--expressions "a;b;c;d"] [--details "x;y"]
      [--server URL] [--seed N] [--split]

Outputs (in --out dir, default: <image_dir>/charcard/):
  <name>-card.png         the character card (or -poses/-expressions with --split)
  <name>-block.md         verbatim character block for downstream consistency

Examples:
  python3 char_card_gen.py girl.png
  python3 char_card_gen.py girl.png --name Mio --style "Ghibli watercolor anime"
  python3 char_card_gen.py girl.png --split   # separate poses + expressions cards
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse
from io import BytesIO
from PIL import Image

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workflows", "char-card-3x4.json")
DEFAULT_SERVER = os.environ.get("COMFYUI_SERVER", "http://127.0.0.1:8188")
SEED = int(os.environ.get("CHARCARD_SEED", "7"))

# ---------------------------------------------------------------- prompts ---

VIEW_LAYOUT = (
    "Character design reference sheet on a clean soft cream background, "
    "one single character only, full-color {style} illustration. "
    "Top row, three FULL-BODY standing poses of the SAME character, equally spaced: "
    "LEFT (x=18%): exact FRONT view standing straight, arms relaxed at sides; "
    "CENTER (x=50%): exact SIDE view in profile facing right, same standing pose; "
    "RIGHT (x=82%): exact BACK view from behind, same standing pose. "
    "Bottom left: a three-quarter (45-degree) three-quarter-length view walking toward the viewer. "
    "Bottom right: a row of four head-and-shoulders facial expressions of the same face: "
    "{expressions}. "
    "Along the very bottom, a slim detail strip: close-up crops of {details}. "
    "Small neat hand-lettered English labels under each view: FRONT, SIDE, BACK, 3/4 VIEW, "
    "EXPRESSIONS, DETAILS. No other text, no watermark."
)

SPLIT_POSES = (
    "Character design reference sheet on a clean soft cream background, "
    "one single character only, full-color {style} illustration. "
    "Four FULL-BODY standing poses of the SAME character arranged left to right, "
    "pinned by position: "
    "Position 1 at LEFT (x=14%): exact FRONT view standing straight, arms relaxed; "
    "Position 2 (x=38%): exact 45-degree three-quarter view facing slightly right; "
    "Position 3 (x=62%): exact SIDE view in profile facing right; "
    "Position 4 at RIGHT (x=86%): exact BACK view from behind. "
    "All four share identical proportions, outfit and colors. "
    "Small neat hand-lettered English labels under each: FRONT, 3/4 VIEW, SIDE, BACK. "
    "No other text, no watermark."
)

SPLIT_EXPR = (
    "Character expression sheet on a clean soft cream background, "
    "one single character only, full-color {style} illustration. "
    "Top: one large head-and-shoulders portrait of the character smiling gently, labeled NEUTRAL. "
    "Below it, a neat 2x3 grid of six head-and-shoulders facial expressions of the SAME face: "
    "{expressions}. "
    "Bottom: a slim horizontal detail strip with close-up crops of {details}. "
    "Small neat hand-lettered English labels under each cell. No other text, no watermark."
)

DEFAULT_EXPRESSIONS = "gentle smile; surprised wide eyes; sad teary eyes; laughing happily"
DEFAULT_SPLIT_EXPRESSIONS = DEFAULT_EXPRESSIONS + "; angry pout; thoughtful gaze"
DEFAULT_DETAILS = "the face, hairstyle and signature accessory; hands, footwear and any carried items"

RENDER_RULES = (
    "Keep the character's face, hairstyle, outfit, colors and proportions EXACTLY "
    "consistent with the reference image across every view. Clean presentation layout, "
    "even spacing, no scene background, no shading of the sheet background."
)


def build_prompt(style, expressions, details, split=None):
    expr = "; ".join(expressions)
    det = "; ".join(details)
    if split == "poses":
        body = SPLIT_POSES.format(style=style)
    elif split == "expressions":
        body = SPLIT_EXPR.format(style=style, expressions=expr, details=det)
    else:
        body = VIEW_LAYOUT.format(style=style, expressions=expr, details=det)
    return body + " " + RENDER_RULES


# ------------------------------------------------------------- comfy glue ---

def http_json(url, data=None, timeout=60):
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    if data is not None:
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def upload_ref(server, local_path, name):
    im = Image.open(local_path).convert("RGB")
    w, h = im.size
    # longest side to 1344, both sides multiples of 32 (MPS adaptive-pooling safe)
    scale = 1344.0 / max(w, h)
    if scale < 1 or scale > 2.5:
        new = (round(w * scale / 32) * 32, round(h * scale / 32) * 32)
    else:
        new = (round(w / 32) * 32 or 32, round(h / 32) * 32 or 32)
    new = tuple(max(32, side) for side in new)
    if new != (w, h):
        im = im.resize(new, Image.LANCZOS)
    image_bytes = BytesIO()
    im.save(image_bytes, "PNG")
    boundary = "----dshcharcard"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
            f"Content-Type: image/png\r\n\r\n").encode()
    body += image_bytes.getvalue()
    body += (f"\r\n--{boundary}\r\n"
             'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
             f"--{boundary}--\r\n").encode()
    req = urllib.request.Request(server + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read())
    return res["name"], os.path.abspath(local_path), im.size


def generate(server, prompt, ref_name, out_path, seed, template=TEMPLATE,
             poll_interval=5, max_wait=1500):
    wf = json.load(open(os.path.abspath(template)))

    def subst(o):
        if isinstance(o, str):
            return o.replace("{{prompt}}", prompt).replace("{{ref}}", ref_name).replace("{{seed}}", str(seed))
        if isinstance(o, dict):
            return {k: subst(v) for k, v in o.items()}
        if isinstance(o, list):
            return [subst(v) for v in o]
        return o

    wf = subst(wf)
    left = json.dumps(wf)
    for tok in ("{{prompt}}", "{{ref}}", "{{seed}}"):
        assert tok not in left, f"placeholder {tok} survived substitution"
    res = http_json(server + "/prompt", {"prompt": wf, "client_id": "dsh-char-card"})
    pid = res["prompt_id"]
    print(f"[card] submitted {pid} -> {os.path.basename(out_path)}", flush=True)
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(poll_interval)
        hist = http_json(server + "/history/" + pid)
        if pid not in hist:
            continue
        entry = hist[pid]
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError("generation error: " + json.dumps(status)[:600])
        for node_out in entry.get("outputs", {}).values():
            for img in node_out.get("images", []):
                if img.get("type") == "output":
                    q = urllib.parse.urlencode({"filename": img["filename"],
                                                "subfolder": img.get("subfolder", ""),
                                                "type": "output"})
                    with urllib.request.urlopen(server + "/view?" + q, timeout=120) as r:
                        data = r.read()
                    with open(out_path, "wb") as f:
                        f.write(data)
                    print(f"[card] saved {out_path} ({len(data)//1024} KB, {time.time()-t0:.0f}s)", flush=True)
                    return out_path
    raise TimeoutError("timed out waiting for " + pid)


# ------------------------------------------------------------- block file ---

def write_block(path, name, style, expressions, details, ref_local):
    """Write the verbatim character block skeleton + pointer to the reference.

    The face/hair/outfit wording must be filled in by the calling agent from
    the reference image (the agent can see it; the pipeline cannot).
    """
    with open(path, "w") as f:
        f.write(f"""# Character block — {name}

Reference image (source of truth for identity): `{ref_local}`
Card image(s) live next to this file.

## Verbatim block (fill the placeholders from the reference image, then
## copy-paste IDENTICALLY into every downstream prompt)

{name}, a [age] [role/background], with [hair length] [hair color] hair
[hairstyle], [distinguishing accessory], [eye color], wearing [top],
[bottom/outerwear], [footwear], carrying [signature item].

Style: {style}.

## Standard expressions
{chr(10).join('- ' + e for e in expressions)}

## Detail anchors
{chr(10).join('- ' + d for d in details)}

## Rules
- Copy the verbatim block word-for-word; even one-word drift ("star hairpin"
  vs "yellow hairpin") causes visual drift over pages.
- For 8+ pages, group scenes, or 2+ characters, prefer reference mode:
  point `"ref"` at the card image (or the original reference) instead of
  relying on text alone.
""")


# ------------------------------------------------------------------ main ----

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="path to any image containing the character")
    ap.add_argument("--out", help="output dir (default <image_dir>/charcard/)")
    ap.add_argument("--name", default=None, help="character name (default: image stem)")
    ap.add_argument("--style", default="Ghibli-style watercolor anime",
                    help="art style for the sheet (default: Ghibli watercolor)")
    ap.add_argument("--expressions", default=None,
                    help="semicolon-separated expression list (4 for single card, 6 for --split)")
    ap.add_argument("--details", default=DEFAULT_DETAILS,
                    help="semicolon-separated detail-crop descriptions (2 items)")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--template", default=TEMPLATE)
    ap.add_argument("--split", action="store_true",
                    help="render two cards: poses (front/45/side/back) + expressions/details")
    args = ap.parse_args()

    src = os.path.abspath(args.image)
    assert os.path.isfile(src), f"no such image: {src}"
    name = args.name or os.path.splitext(os.path.basename(src))[0]
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower()).strip("-") or "char"
    out_dir = os.path.abspath(args.out) if args.out else os.path.join(os.path.dirname(src), "charcard")
    os.makedirs(out_dir, exist_ok=True)

    expression_text = args.expressions if args.expressions is not None else (
        DEFAULT_SPLIT_EXPRESSIONS if args.split else DEFAULT_EXPRESSIONS)
    expressions = [e.strip() for e in expression_text.split(";") if e.strip()]
    expected_count = 6 if args.split else 4
    if len(expressions) != expected_count:
        ap.error(f"--expressions requires {expected_count} semicolon-separated items")
    details = [d.strip() for d in args.details.split(";") if d.strip()]

    ref_name, ref_local, ref_size = upload_ref(args.server, src, f"{safe}-ref.png")
    print(f"[card] ref uploaded: {ref_name} {ref_size}", flush=True)

    jobs = [("poses", f"{safe}-card-poses.png"), ("expressions", f"{safe}-card-expressions.png")] \
        if args.split else [(None, f"{safe}-card.png")]
    for split, fname in jobs:
        prompt = build_prompt(args.style, expressions, details, split=split)
        generate(args.server, prompt, ref_name, os.path.join(out_dir, fname),
                 seed=args.seed, template=args.template)

    write_block(os.path.join(out_dir, f"{safe}-block.md"),
                name, args.style, expressions, details, ref_local)
    print(f"[card] character block -> {os.path.join(out_dir, safe + '-block.md')}", flush=True)


if __name__ == "__main__":
    main()
