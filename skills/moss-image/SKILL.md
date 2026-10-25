---
name: moss-image
description: "Draw images on the user's OWN Mac using their locally installed MOSS-Image (5B DiT + Qwen3.5-9B encoder, Apache-2.0) and their own ComfyUI server at 127.0.0.1:8188. Offline, free, no API key, nothing leaves the machine. Run 8 steps in ~40 s thanks to the community DMD distillation LoRA. PREFER THIS SKILL OVER qwen-image-2-1-turbo whenever the image must contain a lot of legible text — dense blackboard math, storefront signage, menus, posters, book pages, infographics — because MOSS keeps writing real characters at text densities where Qwen degrades into pseudo-glyph texture. Also reach for it for photoreal editorial portraits and street/product shots. Do NOT use it for anime or 2D illustration (use a style-tuned anime model), for multi-page picture books (use dsh-image-book), or for character sheets / 三视图 (use dsh-character-card — those need reference-image mode, which this ComfyUI build does not implement for MOSS)."
---

# moss-image · local 8-step text-to-image

The user's Mac runs **MOSS-Image-SFT** on their own ComfyUI, plus the community
**8-step DMD LoRA** (`lodestones/MOSS-Image-SFT-8-steps-dmd`) that cuts the
50-step CFG-3 recipe down to 8 network evaluations at CFG 1.0.

Measured on the user's **MacBook Pro / M4 Max / 128 GB** (bf16, MPS; 2026-10-25):

| | 512² | 1024² | 1456² |
|---|---|---|---|
| 8 steps + LoRA | 12 s | **39 s** | 108 s |
| extra for the very first image | +42 s (loads ~28 GB of weights) | | |

## Invoke when

The user wants an image drawn and **text matters** — a blackboard covered in
formulas, shop signs, a chalkboard menu, a poster or book page, a UI screenshot,
an infographic, a poster with a headline and body copy. This is the skill's
killer feature and the reason it exists next to Qwen-Image-2.1.

Also good for: photoreal editorial portraits, street scenes, product shots, any
scene where you want crisp signage in the background.

Not for: anime / illustration / 2D styles (use a style-tuned anime model), multi-page books
(use `dsh-image-book`), character sheets needing image references (use
`dsh-character-card` — reference-token support is absent from this ComfyUI build).

## How to run it

One command, then show the result and stop.

```bash
python3 ~/.agents/skills/moss-image/scripts/moss_t2i.py \
  --prompt "<full descriptive prompt>" --out ~/Pictures/<topic>/x.png --seed <n>
```

| Flag | Use |
|------|-----|
| `--ratio 1:1\|4:3\|3:4\|3:2\|2:3\|16:9\|9:16` | ~1M-pixel presets. Add `-2k` for `1:1-2k` (1456²) / `16:9-2k`. |
| `--size 1344x1024` | Explicit override; **both dims must be multiples of 16**. |
| `--seed N` | Same seed + same prompt = same image. Omit for random; print the printed seed when the user wants a variation. |
| `--slow` | Official-quality route: 50 steps, CFG 3, no LoRA. **~8 minutes, ~10× slower.** Only when the user asks for maximum quality or the 8-step result is visibly not enough. |
| `--explain` | Print the LoRA routing decision and exit **without** generating. Use when the user asks which LoRA would be picked, or before an expensive `--slow` run. |
| `--no-auto-lora` | Disable automatic LoRA selection (DMD only). |
| `--lora NAME` | Force a specific LoRA (repeatable). Disables auto-routing. |
| `--strength F` | Weight for forced `--lora` entries; auto-routed ones carry their own. |
| `--negative "…"` | Only has an effect when cfg > 1; at CFG 1.0 the negative branch is never evaluated. |

## Automatic LoRA selection

**Do not ask the user which LoRA to use, and do not name one in the prompt.**
`moss_t2i.py` reads `lora_routes.json` (sitting next to the script) and picks from
the prompt by itself. Every generation prints what it chose:

```
  auto + MOSSRealisticSnapshotV1.safetensors @0.7  [photo-realism]
```

The table is **ordered rules**, not a guess: each rule lists keywords that must
(`all`) or may (`any`) appear and words that veto it (`not`). First full match
wins per *slot* (currently just `look`), so two competing looks cannot stack.

| Rule | Picks | Notes |
|---|---|---|
| `photo-realism` | `MOSSRealisticSnapshotV1` | photo, candid, snapshot, 实拍, 照片; vetoed by anime/illustration/painting |

No match means plain MOSS-Image with only the DMD LoRA — which is the right answer
for most requests. **Trust the default.** Passing `--no-auto-lora` for text-heavy
tasks (blackboards, signage, posters) is correct: those want the model's own text
fidelity, not a style LoRA.

Match the table with word boundaries so partial words never trigger a rule. When a
prompt is genuinely ambiguous, run `--explain` and say so rather than guessing.

To add a LoRA: drop the file in `~/ComfyUI-Shared/models/loras/`, then add an entry to
`loras` plus a rule. Trigger
words that look like `training_<id>-<timestamp>` are training session ids, not real
triggers — leave them out.

Output location convention: `~/Pictures/<topic>/`.

## Non-negotiable: CFG must be 1.0 on the 8-step route

The DMD LoRA is distilled for CFG 1.0. Raising CFG collapses it back toward the
un-denoised base output. The script warns and proceeds, but treat CFG > 1 as a
code smell, not a knob.

A useful side effect: because CFG 1.0 runs no uncond pass, the negative prompt is
inert on this route — anything you put there has no effect.

## Prompting notes

- Natural-language English, like a photography brief. Subject, framing, lens,
  light, then explicit text requirements: `a red signboard reading 老张牛肉面`,
  `a blackboard of calculus with Chinese annotations such as 换元法`.
- State the text **verbatim and in quotes**; MOSS renders quoted strings far more
  faithfully than "some Chinese text".
- Chinese renders correctly — this is one of the few open models that does it at
  paragraph length. Expect real characters with loosely coherent meaning, not a
  factually correct paragraph.
- Anatomy and hands are usually fine at editorial framing; very close-up hands
  still fail like every model in this class.

## Failure modes seen in practice

| Symptom | Cause |
|---|---|
| Washed-out, low-contrast, hazy image | 8 steps without the LoRA, or CFG raised above 1.0 |
| Image looks fine but text is mush | Prompt asked for "text" generically instead of quoting the literal string |
| `is not visible to ComfyUI` | Weights are not symlinked into `~/ComfyUI-Shared/models/` |
| Very slow (>8 min) | The `--slow` route, or ComfyUI fell back to CPU inference |

## What this build cannot do

- **Reference / edit mode** (img2img with a reference image, character 三视图):
  the shipped `comfy/ldm/moss_image/model.py` in ComfyUI 0.42.5 is the 190-line
  text-to-image version. Reference-token conditioning exists only in newer master.
- **Control adapters** (color/depth `MOSSImageControl` nodes): wired for it in the
  node set, but untested here — do not promise it.
