---
name: dsh-image-book
description: Generate English picture-comic books (绘本/漫画) end-to-end with a local ComfyUI + Qwen-Image-2.1 setup, including character consistency, English text rendering verification via OCR, and PDF assembly. Use this skill when the user asks for an English comic, picture book, manga, illustrated story, or any multi-page illustrated narrative. Triggers on phrases like "做一个绘本", "做一本漫画", "生成绘本", "make a picture book", "make a comic", "draw a manga", "illustrate a story".
---

# dsh-image-book · English Picture-Comic Book Generator

A complete end-to-end pipeline for producing English picture-comic books (绘本 / 漫画) from a single brief. Built and battle-tested on macOS with a local ComfyUI server and Qwen-Image-2.1.

## When to invoke this skill

Invoke when the user asks to create, draw, or generate an English illustrated book/comic/story — even a one-page strip. This skill owns:

- Story design (题材 / 角色 / 节奏 / 旁白语言)
- Cover + page prompts (with character consistency)
- Generation via ComfyUI / Qwen-Image-2.1
- OCR-based English text verification
- PDF assembly

Do not invoke for: still images without story (use `nano-banana-pro-prompts-recommend-skill`), photo generation, video, or anything that is not multi-page illustrated narrative.

---

## What this directory contains (reusable assets)

| File | What it is | When to use |
|------|-----------|-------------|
| `workflows/qwen21-3x4.json` | ComfyUI API-format workflow, 25 steps, cfg 1, 1008×1344 portrait, `{{prompt}}` + `{{seed}}` | **Default for text-heavy pages** |
| `workflows/qwen21-3x4-s15.json` | Same as above but 15 steps | Faster, **but causes duplicate text bubbles** — see pitfalls |
| `workflows/qwen21-edit-3x4.json` | 25 steps, takes **1 reference image** via `{{ref}}` (`TextEncodeQwenImageEdit`) | Character-sheet-consistent pages |
| `workflows/qwen21-editplus-3x4.json` | 25 steps, takes **2-3 reference images** via `{{ref}}`/`{{ref2}}`/`{{ref3}}` (`TextEncodeQwenImageEditPlus`) | Multi-character consistency, group scenes |
| `scripts/comfy_gen.py` | CLI driver. Picks t2i vs edit automatically, uploads refs, submits, polls, downloads | All generation runs |
| `scripts/ocr_verify.py` | Python OCR verifier using Swift Vision backend, with Levenshtein-tolerant matching | After generation, before declaring a page done |
| `scripts/ocr_vision.swift` | Swift script: VNRecognizeTextRequest OCR, plain output | Called by `ocr_verify.py` |
| `scripts/ocr_boxes.swift` | Swift script: OCR + bounding boxes `[x, y, w, h]` | When you need to debug *where* text was rendered |
| `scripts/make_book_pdf.py` | Generic PDF assembler, configurable gutter color | End of every book project |
| `examples/short-story.json` | 7-page example: one protagonist, `charsheet` + dialogue-heavy pages, uses reference mode | Reference for **short stories + reference mode** |
| `examples/atmospheric.json` | 5-page example: atmospheric horror / grotesque, dialogue + caption mix | Reference for atmospheric prompts |
| `examples/restrained.json` | 6-page example: restrained caption-only narration, minimal dialogue | Reference for sparse dialogue pages |
| `examples/ensemble-cast.json` | 13-page example: large ensemble cast (5 characters), many group scenes | Reference for **multi-character consistency + group scenes** |

Any other workflow you drop into `workflows/` works too, as long as it keeps the `{{prompt}}`/`{{seed}}` placeholders (and `{{ref*}}` for its reference slots) — pass it with `--template`.

The example prompt files are **structural references** — read them for prompt anatomy, not for content. Subject matter should come from the user's current request.

---

## The four-phase workflow

### Phase 1 — Design

In conversation with the user, pin down **before writing any prompt**:

1. **Audience** (读者): who is the book for? Children, teens, adults — drives reading level and visual style
2. **Subject / theme** (题材): what is the book about? Whatever the user wants — fiction, non-fiction, fantasy, memoir, etc.
3. **Page count** (篇幅): short (5-6 pages) / medium (8-10) / long (12+)
4. **Art style** (画风): shoujo manga, American horror, semi-realistic illustration, watercolor, or whatever fits the subject
5. **Character roster** (人物): how many, distinct visual anchors per character

Read the example prompt files for structural anatomy (how to write a page prompt), then build the new book's prompts around whatever subject the user asked for.

### Phase 2 — Author prompts

For each page, write a prompt that contains exactly three blocks, in this order:

```
[Scene description with exact spatial layout]

[VERBATIM CHARACTER BLOCK — copy-pasted, character-for-character, from a master sheet]

[Style block + render rules]
```

The verbatim character block is **not optional** when you run text-to-image. Multiple characters drift apart within 3-4 pages without it.

Master character block example (copy verbatim into every prompt):
```
[Protagonist], a [age]-year-old [background], with [hair style and color],
[a distinguishing accessory], [eye color], wearing [outfit detail A],
[outfit detail B], [optional item they always carry]
```

The block must be **identical** across every page prompt. Even one-word drift ("star hairpin" vs "yellow hairpin") over 6+ pages will cause the model to slowly diverge the character's appearance.

#### Two consistency modes — pick per page

| Mode | How | Use for |
|------|-----|---------|
| **Text-to-image** (default) | No `ref` field. Prompt carries the verbatim character block. | Single simple character, short books, quick drafts |
| **Reference mode** | Add `"ref": "my-character-sheet.png"` (one ref → `qwen21-edit-3x4.json`) or `"refs": ["a.png", "b.png"]` (2-3 refs → `qwen21-editplus-3x4.json`) to a page entry. `comfy_gen.py` picks the template automatically. | Multi-page books, 2+ characters, group scenes |

In reference mode the character sheet image is fed to the model's multimodal text encoder (`TextEncodeQwenImageEdit` / `...EditPlus`), which carries far more identity information than any text block can. Keep the verbatim description in the prompt anyway — it still steers wardrobe and pose.

Reference files are resolved relative to the prompts JSON, uploaded through ComfyUI's `/upload/image`, and cached per run. Generate the character sheet page **first** (an entry like the `charsheet` page in `examples/short-story.json`), then point later pages at its output file name.

Render rules — append to every prompt:
```
Render text exactly as quoted, no extra text, no extra caption boxes,
no extra speech bubbles, render each caption exactly once,
do not duplicate any caption.
```

### Phase 3 — Generate, verify, iterate

Run generation (`--list` first if you want to see each page's mode and seed):
```bash
python3 scripts/comfy_gen.py --list --prompts my-book.json
python3 scripts/comfy_gen.py --prompts my-book.json --all
```

Verify text:
```python
import sys; sys.path.insert(0, "scripts")
from ocr_verify import verify
verify("cover.png",   ["TITLE"])
verify("p1.png",      ["caption one", "caption two", "dialogue one", "dialogue two"])
```

If a page fails, regenerate just that page with a new seed:
```bash
python3 scripts/comfy_gen.py --prompts my-book.json --force p4
```

Each page takes ~2 min at 25 steps, ~1.5 min at 15 steps.

### Phase 4 — Assemble PDF

```bash
python3 scripts/make_book_pdf.py \
    --title "The Book Title" \
    --out Output.pdf \
    --pages cover.png,p1.png,p2.png,p3.png \
    --gutter 84 --bg "#F2EAD9" --rounded
```

`--bg` color: warm cream for emotional/realistic (`#F2EAD9`), near-black for horror (`#181614`), sage for youth (`#EFE4D0`).

---

## Pitfalls — read this before generating

These are **real failures** observed across 4 books (32+ pages). They will save you a regenerate.

### 1. 15 steps causes duplicate text bubbles (esp. in dialogue-heavy pages)

Qwen-Image-2.1 at 15 sampling steps prematurely converges and sometimes renders **the same speech bubble twice**, or with one word missing. Always default to **25 steps for dialogue-heavy pages**.

Symptom: OCR sees two copies of the same caption line, or a phrase missing a word that you wrote (e.g. `It's same house` instead of `It's the same house`).
Fix: switch to 25 steps (`qwen21-3x4.json` not `-s15.json`), OR switch to a different seed, OR simplify the page to fewer speech bubbles.

### 2. Multi-character horizontal layouts drift in left-right order

If you ask for 4 people sitting "from left to right: A, B, C, D", Qwen may place them in a different order (it seems to optimize for "visual balance" / "interesting composition"). Always pin positions with absolute x-coordinates:

```
Position 1 at LEFT (x=15% of image width): character A, ...
Position 2 (x=38%): character B, ...
Position 3 (x=62%): character C, ...
Position 4 at RIGHT (x=85%): character D, ...
```

This is **mandatory** for any 4+ character scene, and advisable for 3-character scenes too.

### 3. The host model cannot see the images

Any DSH model without image-input capability (most open-source variants) cannot visually verify generated pages. The host must rely on:
- **OCR text verification** (catches text rendering issues, ~80% of bugs)
- **Statistical checks** (file size, color mean/std, dimensions)
- **Bounding-box spatial checks** (`ocr_boxes.swift`)

The user must visually verify final output. The pipeline does **not** guarantee visual correctness.

### 4. Workflow placeholders are substituted strictly — leftovers abort the run

`comfy_gen.py` substitutes `{{prompt}}`, `{{seed}}`, and (for the edit templates) `{{ref}}` / `{{ref2}}` / `{{ref3}}`. If a placeholder survives substitution, the driver raises instead of silently sending a broken graph — e.g. an edit template without a `ref` on that page, or a template whose node uses a different token name.

Sanity-check a template: `grep -c '{{prompt}}' workflows/qwen21-3x4.json` should return `1`. For `qwen21-editplus-3x4.json`, all three `{{ref*}}` slots must be filled (give 2 refs and the driver repeats the second into the third).

### 5. macOS Swift + Vision requires `-fmodules-cache-path`

When running `swift ocr_vision.swift ...`, the compiler's module cache defaults to `/var/folders/...` which is blocked by macOS sandbox. Always use:
```bash
swift -Xcc -fmodules-cache-path=/tmp/swift-module-cache ocr_vision.swift image.png
```
`comfy_gen.py` and `ocr_verify.py` already do this — if you call `swift` directly, remember to add it.

### 6. OCR is fuzzy. Trust Levenshtein-2, not substring.

macOS Vision OCR will:
- Read `m` as `n` (and vice versa)
- Drop spaces: `THE END` → `THEEND`
- Drop small words in fancy fonts

`ocr_verify.py` uses Levenshtein distance ≤2 per word. This is intentional. If a phrase "fails" but visually you can confirm it's correct in the source prompt, it's probably an OCR miss — trust the prompt.

---

## Quick start (new book)

```bash
cd dsh-image-book          # the directory containing this SKILL.md

# 1. Read one of the example prompts files to learn the structure
python3 -m json.tool examples/short-story.json | head -60

# 2. Copy an example and edit it for your story
cp examples/short-story.json my-book.json
# edit my-book.json: replace seeds, prompts, output file names
#   pages are generated in file order — the "charsheet" entry must come first
#   add  "ref": "bloom-character-sheet.png"  to any page to switch it to reference mode

# 3. Point the driver at your ComfyUI server and generate
export COMFYUI_SERVER=http://127.0.0.1:8188     # or any reachable ComfyUI host
python3 scripts/comfy_gen.py --list --prompts my-book.json
python3 scripts/comfy_gen.py --prompts my-book.json --all
# a quantized template on a small GPU? pass it explicitly:
#   python3 scripts/comfy_gen.py --template workflows/qwen21-3x4-s15.json --prompts my-book.json --all

# 4. Verify each page's rendered English text
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from ocr_verify import verify
verify('my-book-p1.png', ['expected caption 1', 'expected caption 2'])
"

# 5. Build the PDF
python3 scripts/make_book_pdf.py --title "My Book" --out My-Book.pdf \
    --pages my-book-cover.png,my-book-p1.png,my-book-p2.png \
    --gutter 84 --bg "#F2EAD9" --rounded
```

---

## ComfyUI server: local vs remote

`comfy_gen.py` reads the target server from the `COMFYUI_SERVER` environment
variable (default `http://127.0.0.1:8188`) — the same driver works against a
local desktop ComfyUI or a remote box on your LAN/VPN.

| Setup | Typical address | Notes |
|-------|-----------------|-------|
| Local ComfyUI (macOS, bf16 weights) | `http://127.0.0.1:8188` | ~2 min per 1008×1344 page @25 steps on an M-series Mac |
| Remote GPU box (e.g. NVIDIA Jetson / workstation) | `http://<host>:8188` | ~60-70 s per page warm; useful as an always-on render box |

Model file paths and any int8/quantized weight variants live on the **server**,
not in this skill — point `--template` at a workflow whose loader nodes name the
files that server actually has. The bundled templates target the bf16 trio
listed below; a quantized deployment needs its own template copy with the
loader names swapped.

---

## Minimum runtime requirements

- macOS (for Swift Vision OCR; on Linux substitute another OCR backend in `ocr_verify.py`)
- Python 3.9+ with `PIL` and `numpy` (no other deps — `urllib` is stdlib)
- A reachable ComfyUI server: `COMFYUI_SERVER` env var (default `http://127.0.0.1:8188`)
- Qwen-Image-2.1 model loaded in ComfyUI:
  - `qwen_image_2.1_bf16.safetensors` (diffusion model)
  - `qwen3vl_8b_bf16.safetensors` (text encoder)
  - `qwen_image_2.1_vae_bf16.safetensors` (VAE)
  - (quantized deployments work too — copy a template and swap the loader file names)
- `swift` CLI (ships with Xcode Command Line Tools)
- 1008×1344 portrait pages @ 25 steps: ~2 min/page on Apple-silicon MPS, **~60-70 s/page on a dedicated GPU box**, ~1.7 GB of PNG output each
- A model with **image input capability** to verify quality (otherwise rely on OCR + structural checks)

---

## On written English in image captions

Qwen-Image-2.1 renders short, common-vocabulary English accurately. A few rules that hold across reader levels:

- **Keep sentences short.** 5-12 words renders reliably. Long sentences lose words or duplicate phrases.
- **Prefer common words.** *looked sad* renders correctly; *exhibited melancholy* does not.
- **Dialogue beats caption narration.** Caption boxes (narration) and speech bubbles (dialogue) are different render paths — alternating them reduces the "duplicate text" failure mode.
- **Horror / atmospheric: short fragmented lines work best.** Single-clause lines like *"She left this morning."* render more reliably than compound sentences.
- **For children / language learners**: simpler vocabulary; for adult literary fiction: dialogue can be longer but still under ~15 words per bubble.

Choose vocabulary and sentence length to match the audience decided in Phase 1.

---

## What this skill does NOT do

- Video generation
- Photo-realistic portraits (Qwen-Image-2.1 is illustration-tuned)
- Character consistency is bounded by prompt discipline plus reference-image conditioning — there is no LoRA or IP-Adapter training in this pipeline.
- Translated multi-language editions (text is English-only by design)
- Print-ready bleeds / CMYK (PDF is RGB screen-ready)

For LoRA / IP-Adapter / regional prompting / ControlNet at production quality, integrate a third-party ComfyUI workflow outside this skill.

---

## Character consistency in depth: text block vs reference image

This is the single biggest quality factor across a multi-page book, so it is worth understanding what each mode actually does.

**Text-only (t2i).** The character exists only as tokens in the positive prompt. The model re-derives the face from scratch on every page, so drift is cumulative: page 1 and page 6 can look like different people if a single descriptive word changes. The verbatim block keeps drift slow but cannot eliminate it.

**Reference mode.** The character sheet is encoded by the multimodal text encoder (`TextEncodeQwenImageEdit` for one reference, `TextEncodeQwenImageEditPlus` for 2-3) and folded into conditioning. Identity information — face shape, proportions, hair silhouette — arrives as image features rather than words, which is why it holds up better across many pages and across group scenes.

Measured note from a controlled A/B (same `seed=7777`, same scene prompt, same character text):

- **Setup**: one run used verbatim text only; the other used the same text plus a 1024×1024 character-sheet reference.
- **Result**: for that *simple single-character* scene the two were judged approximately equal — reference mode is not a magic upgrade for easy shots.
- **Where it earns its cost**: books with 8+ pages, two or more recurring characters, or group scenes where the same face must survive re-framing.

Implementation details if you want to go beyond the bundled templates:

- `TextEncodeQwenImage21` accepts up to 16 reference images through its `images` autogrow input.
- Reference images should be sized to multiples of 32 to avoid an MPS adaptive-pooling error.
- The reference is passed as an autogrow dict (`{"image_1": ["<LoadImage-node-id>", 0]}`), not positionally — that is what the `edit` templates already do for you.

The bundled `qwen21-edit-3x4.json` / `qwen21-editplus-3x4.json` are the working form of this experiment; `comfy_gen.py` selects them automatically as soon as a page declares `ref` / `refs`.

---

*Last updated: 2026-09. Generic pipeline documentation; subject matter is supplied by each user's request.*