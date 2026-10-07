---
name: dsh-character-card
description: Generate a character design card (角色卡) from ANY single character image using ComfyUI + Qwen-Image-2.1 reference mode — front / 45-degree / side / back full-body views, a set of facial expressions, and detail crops, identity-locked to the input image, plus a reusable verbatim character block. Use this skill when the user gives a character/person/creature image and asks for 角色卡, character sheet, character card, 三视图, 转面, 表情表, "帮我把这个角色做成卡片", "make a reference sheet", or wants multi-view consistency for later illustration work.
---

# dsh-character-card · Character Card Generator (ComfyUI + Qwen-Image-2.1)

Turn **one arbitrary image of a character** into a production-ready character card:
转面 views (正面 / 45° / 侧面 / 背面; four full-body views with `--split`), facial expressions, detail crops —
plus a **verbatim character block** file for keeping the character consistent in
all downstream generation.

Built on the same stack as `dsh-image-book`: a ComfyUI server running
**Qwen-Image-2.1** (`qwen_image_2.1_bf16` + `qwen3vl_8b_bf16` text encoder +
`qwen_image_2.1_vae_bf16` VAE), using **reference mode**
(`TextEncodeQwenImageEdit`) so the face/hair/outfit identity comes from the
input image itself, not just words.

## When to invoke

- User provides any character image and wants a 角色卡 / character sheet / 三视图 / 表情表
- User wants to lock a character's identity before making a book/comic/series
- NOT for: text-to-image with no reference (use plain `dsh-image-book` flows),
  LoRA training, video, photo-realistic portraits

## Files

| File | Purpose |
|------|---------|
| `workflows/char-card-3x4.json` | ComfyUI API workflow: Qwen-Image-2.1, 1008×1344, `{{prompt}}` + `{{ref}}` + `{{seed}}` |
| `scripts/char_card_gen.py` | CLI driver: resizes ref to /32, uploads, builds sheet prompt, submits, polls, downloads, writes character block |
| `docs/images/` | Sample card and derived action images |

## Quick start

Install from the repository root with `./install.sh dsh-character-card`, then
reload your DSH session. For direct CLI use, enter the skill directory first:

```bash
# From the repository root; for a user install, use "${DSH_HOME:-$HOME/.dsh}/skills/dsh-character-card"
cd skills/dsh-character-card
python3 -m pip install pillow
```

Resolve `scripts/char_card_gen.py` relative to this skill's directory, not the
user's project working directory. Pass an absolute input image path when changing directories.
The default sheet has front/side/back full-body views and a 45° walking
three-quarter-length view; use `--split` for four full-body standing views.

```bash
# Minimal: card from any character image (defaults: Ghibli watercolor style)
python3 scripts/char_card_gen.py /path/to/character.png

# Full control
python3 scripts/char_card_gen.py girl.png \
    --name Mio \
    --style "Ghibli-style watercolor anime" \
    --expressions "gentle smile;surprised;sad teary eyes;laughing" \
    --details "face, hair and straw hat;hands, white sandals and bicycle basket" \
    --server http://127.0.0.1:8188

# Two separate cards (poses card + expressions/detail card) — roomier layouts
python3 scripts/char_card_gen.py girl.png --split
```

Outputs land in `<image_dir>/charcard/` by default:

- `<name>-card.png` — the character card (or `-card-poses.png` + `-card-expressions.png` with `--split`)
- `<name>-block.md` — verbatim character block skeleton for downstream prompts

## How it works

1. **Reference upload.** The input image is converted to RGB, resized so both
   sides are multiples of 32 (avoids the MPS/VAE adaptive-pooling error),
   uploaded via ComfyUI `/upload/image`.
2. **Reference-mode generation.** `LoadImage` feeds the ref into
   `TextEncodeQwenImageEdit` together with the sheet-layout prompt; the
   multimodal encoder (Qwen3-VL) carries face/hair/outfit identity as image
   features — far stronger than any text description.
3. **Pinned layout.** View positions are pinned by x-percentages
   (LEFT 18% / CENTER 50% / RIGHT 82%) because diffusion models drift
   left-right order on unpinned multi-figure sheets.
4. **Character block.** The agent (which CAN see images) reads the reference
   and fills the placeholder wording in `<name>-block.md`; that verbatim block
   is then copy-pasted into every future prompt for this character.

## Requirements

- A reachable ComfyUI server with Qwen-Image-2.1 loaded:
  `qwen_image_2.1_bf16.safetensors`, `qwen3vl_8b_bf16.safetensors`,
  `qwen_image_2.1_vae_bf16.safetensors`
- Server URL via `--server` or `COMFYUI_SERVER` env
  (default: `http://127.0.0.1:8188` for a local ComfyUI)
- Python 3.9+ with `PIL` only

## Customizing the card

- **Expressions** (`--expressions`): 4 items for the single card, 6 for `--split`.
  Keep each 2–4 words: "gentle smile", "surprised wide eyes", "angry pout".
- **Details** (`--details`): 2 close-up crop descriptions — typically
  "face + hair + signature accessory" and "hands/footwear/carried items".
- **Style** (`--style`): any illustration style Qwen-Image-2.1 knows; the card
  style can differ from the source image style, identity still holds.
- **Seed**: default 7; on a bad sheet, retry with `--seed` bumps rather than
  rewording the layout.

## Known limits (from dsh-image-book battle testing)

- 4+ figures on one sheet → order drift unless positions are pinned
  (the bundled prompts already pin them; if you customize, keep the pinning).
- The sheet itself may render small label text imperfectly — labels are
  cosmetic; verify the *views* visually, ignore OCR on the card.
- Identity lock degrades for extreme angles/occlusions in the source image;
  the cleanest input is one clear full- or half-body view of the character.
- Qwen-Image-2.1 is illustration-tuned; photo-real humans work but read
  slightly painterly on the card.

## Downstream use

For this optional downstream workflow, separately install `dsh-image-book`.
It is not required to generate cards. First generate the file used below:

```bash
python3 scripts/char_card_gen.py /absolute/path/to/girl.png --name Mio --split
```

Point later pages at the resulting card with reference mode from `dsh-image-book`.
Resolve `ref` from the downstream prompt file's directory; adjust or use an absolute
path if that file is not beside the source image:


```json
{ "p1": { "file": "p1.png", "ref": "charcard/mio-card-poses.png", "prompt": "... [verbatim block] ..." } }
```

`comfy_gen.py` auto-selects the edit template as soon as `ref` is present.
