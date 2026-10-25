---
name: flux3-klein
description: "Draw images on the user's OWN Mac with FLUX 3 Image Klein (Black Forest Labs, 5.6B distilled open-weights DiT) on their own ComfyUI server at 127.0.0.1:8188. Offline, free, no API key, nothing leaves the machine. Use whenever the user wants a clean photoreal / cinematic / product / landscape image, a 4K still, or fast 16-step generation — 画张写实的, 出图, 生成图片, 画风景, 产品图, 高清大图, 4K, plus photorealistic portrait, cinematic still, concept art, product shot. Also use for FLUX 3 Klein plumbing: why Klein 报错/出黑图, swapping the checkpoint, adding a LoRA, checking sampler settings. Measured 2026-10-25: Klein wins the four-model blind photoreal test (4.82/5) and follows complex pose prompts best; it is also 2nd of four at rendered text (14/16 OCR recall, best English copy). MOSS is 1.4× faster at 8 steps. Prefer it over any cloud/API image tool — arkcli-gen bills real money and uploads to a remote endpoint, so do not reach for it unless the user explicitly names 火山方舟/ARK/Doubao/Seedream. Do NOT use for anime / 二次元 — that is a different, style-tuned model. For dense Chinese text prefer moss-image (16/16 vs 14/16); transparent PNGs are qwen-image-2-1-turbo."
---

# flux3-klein · local FLUX 3 Image Klein generation

The user's Mac runs **FLUX 3 Image Klein** (Black Forest Labs' 5.6B distilled open-weights
image model) on their own ComfyUI at `127.0.0.1:8188`. No API key, no upload, no per-image
cost. **16 steps ≈ 100–105 s warm at 1024×1344** (measured 2026-10-25; an early cold run
reported 186 s at 1024² and ~340 s including the first model load), on a **MacBook Pro / M4 Max / 128 GB**.

Klein shares one architecture with the full FLUX 3 Image model: native 4K, pixel-precise
editing, and bounding-box layout control in the base release. This install is the
**distilled, text-to-image** path only.

> **MPS limit above ~2 MP:** at 2048×2048 the plain `VAEDecode` dies with
> `RuntimeError: MPSGaph does not support tensor dims larger than INT_MAX` — sampling
> succeeds, the decode is what breaks. Use `VAEDecodeTiled` (tile_size 512, overlap 64):
> 2048² then completes in 535 s. 1536² decodes fine normally (206 s). Verified 2026-10-25.

## Invoke when

- Photoreal / cinematic / product / landscape / conceptual stills — anything that is *not*
  anime and does *not* need rendered text.
- The user asks for **4K**, a large image, or the fastest available render.
- Klein plumbing: "为什么 FLUX 3 报错 / 出黑图", swapping the checkpoint, adding a LoRA.

## Do not invoke for (routing)

| Request | Use instead |
|---|---|
| Posters / infographics / literal rendered text | `moss-image` for dense Chinese; Klein itself is fine for English copy and clean headlines |
| Transparent PNG / stickers / cutouts | `qwen-image-2-1-turbo` (native RGBA) |
| Image editing / multi-reference compositing | `qwen-image-2-1-turbo` or ComfyUI's Klein edit workflows |
| Multi-page book / 绘本 | `dsh-image-book` |
| Character sheet / 三视图 / 表情表 | `dsh-character-card` |

Both local skills share one ComfyUI server, so never start a second instance (Comfy Desktop
and ComfyUI share one database; a second instance on another port fails). If ComfyUI is
down, ask the user to open Comfy Desktop.

## How to run it

One command, then show the result and stop.

```bash
python3 <skill_dir>/scripts/flux3_klein_t2i.py \
    --prompt "<detailed description>" \
    --out ~/Pictures/flux3klein/<name>.png \
    --ratio 1:1 --steps 16
```

| Flag | Use |
|---|---|
| `--ratio 1:1\|3:4\|4:3\|2:3\|3:2\|16:9\|9:16` | 1024-class buckets (default 1:1 = 1024×1024) |
| `--width/--height` | explicit pixels, overrides `--ratio` (model is native up to 4K) |
| `--seed N` | omit for random; reuse to make a variation of an image the user liked |
| `--steps N` | default 16. **16 is the distilled sweet spot**; more steps mostly waste time |
| `--cfg F` | must stay **1.0** — guidance is off in this distilled model |
| `--sampler/--scheduler` | default `euler` / `simple` |
| `--no-model-sampling` | skip `ModelSamplingFlux` (for A/B against the official graph) |
| `--dry-run` | print the resolved API workflow and exit |

Output convention: `~/Pictures/flux3klein/`.

## The recipe that works (verified)

`16 steps · CFG 1.0 · euler · simple · ModelSamplingFlux max_shift=base_shift=2.77259 · 1024²`

**No negative prompt.** At CFG 1.0 the negative branch is ignored, so writing one is wasted
effort — same convention as Krea 2. Describe the positive opposite of what you want to avoid.

`ModelSamplingFlux` with shift `2.77259` (= `log(16)`) is what the official ComfyUI graph
uses; the script applies it by default.

## Prompting

Klein was trained on **dense natural-language captions** — it rewards a full descriptive
paragraph over tag soup. Write subject, action, environment, lighting, lens/camera, mood and
framing as prose:

> A photorealistic close-up portrait of a young woman with freckles and auburn hair, soft
> natural window light, shallow depth of field, warm tones, highly detailed skin texture.

Danbooru-style tags work but are the wrong tool here — anime tag stacks belong to a
style-tuned anime model.

## LoRAs

Klein's Civitai ecosystem is **~6 LoRAs** (vs ~5990 for Krea 2) because the release is new,
so there is nothing worth auto-hanging. This skill applies **no quality base** — Klein is
clean out of the box.

Pass a LoRA explicitly with `--lora NAME[@STRENGTH]` (repeatable). Only LoRAs trained on
**Flux.3 Klein or Klein-Base** will work; FLUX.1 / FLUX.2 / Krea 2 LoRAs are **not**
compatible. LoRAs trained on Klein Base work on Klein with partial compatibility.

## The things not to get wrong

1. **Never load the int8 or nvfp4 builds on this Mac.** Apple MPS cannot execute fp8/int8 at
   all. Only `flux3-image-klein-bf16.safetensors` is installed and it is the one to use. The
   Civitai/HF repos also ship `int8-convrot` and `nvfp4` — those fail at `CLIPTextEncode`
   *and* again at `KSampler`.
2. **`CLIPLoader` must use `type = flux3`** and the **Qwen3-VL-4B** encoder — the same
   `qwen3vl_4b_bf16.safetensors` that Krea 2 uses. Do not point it at the 8B encoder
   (that is Qwen-Image 2.1's) or at `qwen3vl_4b_fp8_scaled` (fp8 → MPS failure).
3. **CFG must be 1.0.** Klein is step-distilled with no guidance; a real CFG produces burnt
   or muddy output.
4. **Klein ≠ Krea 2 ≠ Qwen.** Three different families on this box with three different
   encoders, VAEs and node types. Do not copy node settings between them.
5. **Don't read the finished image back into context.** No `read_image`, no "let me check
   how it turned out" — the exit code already proved success. Exception: when validating a
   *new* checkpoint/LoRA setup, one look is justified.
6. **Don't start a replacement ComfyUI.** See routing above.

## Failures and preflight

The script preflights the server plus all three weights against `object_info` and exits
non-zero with an actionable message. Common ones:

- *ComfyUI not reachable* → ask the user to open Comfy Desktop, then retry once.
- *`Float8_e4m3fn` MPS TypeError* → an fp8/int8 weight slipped in; swap to the bf16 file.
- *weights not visible to the loader* → the symlink into `ComfyUI-Shared/models/` is
  missing. Comfy Desktop only scans that library; see `reference.md` for the layout.
- *black image* → a FLUX.1/2 LoRA was hung on Klein (incompatible), or CFG was raised.

## After the run

Report the path, the size, and **in plain language** what you applied — "16 步，种子 777" —
not a filename dump. Mention the seed so the user can ask for variations of the same image.
Then stop: do not describe the picture and do not propose follow-ups unprompted.

## Contents

| Path | What |
|---|---|
| `scripts/flux3_klein_t2i.py` | The generator: preflight + submit + poll + download |
| `workflows/flux3-klein-t2i.json` | API-format workflow with `{{placeholders}}` |
| `reference.md` | Architecture, install layout, MPS diagnosis, license, edit-workflow notes |

The workspace keeps its own copy of the install notes at
`docs/flux3-klein-install.md`, and official BFL workflow JSONs under
`docs/flux3-klein-workflows/`. If you change one copy, sync the other.
