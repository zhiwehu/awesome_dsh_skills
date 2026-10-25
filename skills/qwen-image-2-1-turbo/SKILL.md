---
name: qwen-image-2-1-turbo
description: "Draw images on the user's OWN Mac using their locally installed Qwen-Image-2.1-Turbo model and their own ComfyUI server at 127.0.0.1:8188. Offline, free, no API key, images never leave the machine. Use whenever the user wants a picture drawn on this computer — 画一张, 画个, 帮我画, 出图, 生成图片, 画个帅哥, 画个美女, 做张图, 配图, plus draw me, generate an image, make a picture, create an illustration. For anime / illustration / 二次元 requests, use a style-tuned anime model instead — reserve this skill for photoreal portraits, image editing, transparent PNGs, and Qwen-specific work (for dense rendered text, moss-image is measurably better: 16/16 vs 12/16 OCR recall). ALWAYS prefer this local skill over arkcli-gen and any cloud/API image tool — arkcli-gen bills real money and uploads to a remote endpoint, so do not reach for it unless the user explicitly names it or asks for 火山方舟/ARK/Doubao/Seedream. Do not web-search for image generation."
---

# qwen-image-2-1-turbo · local 8-step image generation

The user's Mac already runs **Qwen-Image-2.1-Turbo** on their own ComfyUI. No API key, no upload, no per-image cost. One 8-step generation takes roughly 90–230 s on a **MacBook Pro / M4 Max / 128 GB** (measured 2026-10-25: 89–111 s at 1024×1344).

## Invoke when

The user asks for an image to be drawn, painted, illustrated or generated — including vague phrasings like "帮我画个…" or "来张…". Also use it to iterate: "再来一张", "换个风格", "把那张改成…".

Do **not** invoke for: multi-page illustrated books (use `dsh-image-book`), character sheets / 三视图 (use `dsh-character-card`), video, or when the user explicitly wants a cloud model.

## How to run it

One command. Then show the result and stop — see "After the run" below.

```bash
python3 <skill_dir>/scripts/turbo_t2i.py --prompt "<full descriptive prompt>" --out <path>.png --seed <n>
```

Other flags:

| Flag | Use |
|------|-----|
| `--ratio 1:1\|4:3\|3:4\|3:2\|2:3\|16:9\|9:16` | Model-card resolution presets (2K-class). Omit for the default 1008×1344 portrait. |
| `--seed N` | Omit for a random one. Same seed + same prompt = same image, so reuse it when the user wants a variation of something they already saw. |
| `--prompts pages.json --outdir dir/` | Batch. JSON shape: `{"key": {"prompt": "...", "seed": 1, "file": "a.png", "ratio": "16:9"}}` |
| `--template PATH` | Swap the workflow. Default is the Turbo 8-step one. |
| `--base` | Switch to the **base-model route** (`workflows/qwen21-base-loras-3x4.json`): base weights, 25-step `KSampler`, CFG 2.5, `er_sde`/`beta`, negative prompt, **three** LoRA slots. Slow — see "Base-model route" below. |
| `--sdxl` | Switch to the **SDXL route** (`workflows/sdxl-pony-loras-3x4.json`): a Pony/Illustrious-family checkpoint, 28 steps at CFG 7, `dpmpp_2m`/`karras`, three LoRA slots, and 1024-class sizes. See "SDXL route" below. |
| `--ckpt NAME` | SDXL route: which checkpoint file to load, overriding the template default. Needed because Civitai's filenames never match the template (the template names an author mirror; Civitai ships `cyberrealisticPony_v180Coreshift_pruned_fp16.safetensors`). Validated by preflight, and it accepts the same subfolder syntax ComfyUI does. |
| `--negative "…"` | Negative prompt. Only has any effect at CFG > 1; a generic one is built in. |
| `--steps N` `--cfg F` `--sampler S` `--scheduler S` | Override `KSampler` settings. Works on the base route; on the Turbo route the step count is fixed by its sigma list (only `--cfg` is forwarded to `SamplerCustom`). |

Default output location: put images somewhere sensible and tell the user the path — `~/Pictures/<topic>/` is the convention used here.

## After the run: show it, then stop

A finished run is already proof of success: the script prints `[turbo] <path> (<KB>, <secs>)`
and exits **non-zero** on every failure (unreachable ComfyUI, missing weights, rejected
prompt). Nothing else needs checking.

- **Do not read the image back into context.** No `read_image`, no vision call, no "let me
  check how it turned out", unless the user explicitly asks to look at it. It burns tokens
  and wall-clock and tells you nothing the exit code did not.
- Show the result with a plain markdown reference, which renders for the user without
  loading anything into the model:

  ```markdown
  ![<short description>](<path>)
  ```

- Keep the wrap-up to the path, the parameters (seed / ratio / LoRA), and anything the run
  itself reported (slow generation, preflight warnings). Do not describe the picture and do
  not list follow-up suggestions unprompted — the turn ends when the image lands.

## Preflight is automatic and will tell you what to do

The script checks three things before submitting and exits with an actionable message if any fails:

1. **ComfyUI reachable at `127.0.0.1:8188`.**
   If not — **do not start your own ComfyUI.** ComfyUI and Comfy Desktop share one
   database, so a second instance on another port fails. Ask the user to open
   Comfy Desktop, then retry.
2. **Turbo weights visible** (`qwen_image_2.1_turbo_bf16.safetensors`).
3. **`SigmasFromList` node registered.**

If ComfyUI is down and the user is not around, that is the end of the turn — report it rather than retrying blindly. Each attempt costs nothing but wall-clock, and the failure is a port/database conflict, not a transient error.

Override the target with `COMFYUI_SERVER=http://host:8188` if the server is elsewhere (the user has used a remote Jetson box this way).

## Writing the prompt

Turbo is a full Qwen-Image-2.1 derivative, so ordinary descriptive prompting works.
From experience on this machine:

- **Describe like a photographer.** lens, lighting, framing, mood, palette.
  "85mm lens, soft window light, shallow depth of field" moves the image a lot more than adjectives.
- **Be explicit about framing when it matters.** Full-body shots need "entire figure
  visible from head to toe" or you get a bust portrait.
- **Text: headlines yes, body copy no.** Measured 2026-10-25 (`docs/4-model-benchmark.md`):
  single-line English and large Chinese headlines come out clean, but at text density a
  poster/blackboard needs, Qwen degrades into pseudo-glyph texture — OCR recall 12/16 vs
  MOSS 16/16 and Klein 14/16. For posters, menus, blackboards or anything with paragraphs
  of Chinese, route to `moss-image` first.
- **Transparent output** works: wrap as
  `This is an RGBA format image with transparency. <description>. The image has an alpha channel and a transparent background.`
  and save as PNG.
- **Negative prompts are ignored at cfg 1** — do not bother writing one.

## LoRA

LoRAs must declare `ss_base_model_version: qwen_image_2` to be architecturally
compatible with Turbo. Put the file in `ComfyUI-Shared/models/loras/` and pass its
filename with `--lora`.

Apply them with `--lora` (repeatable). The script auto-switches to the two-slot
template when any `--lora` is given, so there is no separate command to remember:

```bash
python3 <skill_dir>/scripts/turbo_t2i.py \
  --lora "style-lora.safetensors" --lora-strength 0.8 \
  --lora "detail-lora.safetensors" --lora-strength 1.0 \
  --prompt "..." --out out.png
```

- **Order is load order.** The first `--lora` lands on the first loader in the chain.
- **Strength defaults to 1.0** when not given. 0.6–0.8 is a common "present but still
  natural" range; above ~1.2 colours and anatomy tend to break.
- Passing only one `--lora` leaves the second slot at the template's value.
- The template holds two `LoraLoaderModelOnly` slots; a third `--lora` is rejected with an
  explicit message. Add nodes to `workflows/qwen21-turbo-loras-3x4.json` to widen it.

Chain shape is `UNET → LoRA1 → LoRA2 → QwenImage21Cache → SamplerCustom`. The KV cache node
must stay **after** all LoRAs, or its keys come from un-patched weights.

Verified on this machine: two LoRAs load and chain on Turbo at strength 1.0 without
degrading a neutral prompt. Most community LoRAs were trained on the *base*
Qwen-Image-2, not on the 8-step distilled checkpoint, so effects may read weaker or
more aggressive than intended. If the result looks
off, sweep the strength before concluding the LoRA is at fault; the base model with the
25-step KSampler workflow is its native environment.

`--lora` patches slots left to right, and only the ones you pass; any untouched slot keeps
the template's own value. Both LoRA templates ship every slot at **strength 0.0**, so a slot
you do not name stays inert — passing one LoRA activates exactly one.

### Base-model route (`--base`)

Base-trained LoRAs generally want **CFG 2.5–4**; CFG 1 starves them. `--base` selects
`workflows/qwen21-base-loras-3x4.json`: base `qwen_image_2.1_bf16.safetensors`, a 25-step
`KSampler` at CFG 2.5 / `er_sde` / `beta`, a negative prompt, and **three** LoRA slots
(shipped at strength 0.0, so a bare `--base` run is a clean base render).

**Measured 2026-10-14 on this Mac: not viable as a default.** A 1008×1344 CFG-2.5 run was
still in `KSampler` after 12.5 minutes and got interrupted. The reason is structural, not a
setting: at CFG > 1 the DiT is evaluated twice per step, so 25 steps ≈ 50 forward passes,
against 8 for the Turbo path. Treat `--base` as the patient-job quality route. If a job must
stay near Turbo speed while using a base-trained LoRA, prefer the Turbo route and sweep
strength there first.

### SDXL route (`--sdxl`)

Qwen-Image's LoRA ecosystem is small: Civitai lists ~1,629 Qwen LoRAs against ~284,874 for
Illustrious and ~140,422 for Pony. When you need a specific style LoRA that was never
ported to Qwen, an SDXL-family checkpoint usually has it. `--sdxl` selects `workflows/sdxl-pony-loras-3x4.json`:
`CheckpointLoaderSimple` → three `LoraLoaderModelOnly` slots → `KSampler` (28 steps, CFG 7,
`dpmpp_2m`/`karras`), and 1024-class buckets via `SDXL_RATIO` instead of the 2K presets —
`--ratio 3:4` becomes 896×1152, not 1792×2400, because the 2K sizes make SDXL duplicate
anatomy.

Why it is the fast route: SDXL is 3B, against Qwen-Image 2.1's 7B DiT *plus* a 17.5 GB
Qwen3-VL text encoder. A 1024-class SDXL image lands in the tens of seconds here, and the
checkpoint plus its LoRAs fit in ~12 GB, so this route coexists with the local 27B LLM that
Qwen-Image has to fight for memory.

**Pony-family checkpoints need tag discipline.** CyberRealistic Pony, Pony Diffusion V6 XL and
their merges are trained on a score/source scheme: the positive prompt must start with
`score_9, score_8_up, score_7_up` (add `source_photographic` for realism, `source_anime` or
`source_cartoon` for drawn styles), and the negative uses the `score_1…score_6, source_pony,
source_furry` scheme. `--sdxl` supplies that negative automatically; the positive prefix is the
caller's job.

**LoRAs are not interchangeable across the family.** Pony and Illustrious are both SDXL
architecture and load through the same graph, but their tag schemes differ, so a Pony LoRA
underperforms on Illustrious and vice versa. Match the LoRA to the checkpoint.

Do **not** use Pony V7 — it moved to the AuraFlow architecture, so V6 LoRAs do not load, and its
adoption is a rounding error next to V6.

Checkpoint picks (Civitai downloads, 2026-10): realistic → **CyberRealistic Pony** (780k) or
Pony Realism (573k); anime → **Nova Anime XL** (495k) or Illustrious-XL (191k). CyberRealistic
Pony V18 has an author-run HuggingFace mirror (`cyberdelia/CyberRealisticPony`) because its
Civitai download requires a login.

### 4-step acceleration (DMD2)

SDXL has distilled speed adapters with no Qwen-Image equivalent. DMD2 takes 28 steps down to 4:
measured on this Mac, **16.6 s versus 69.2 s** for the same prompt and seed — a **4.2x** win, and
5–6x against the Qwen Turbo route's 90–100 s.

Source needs no Civitai login: `tianweiy/DMD2` (the authors' own repo) →
`dmd2_sdxl_4step_lora_fp16.safetensors`, 393,854,592 bytes, already installed in
`ComfyUI-Shared/models/loras/`.

```bash
--sdxl --lora dmd2_sdxl_4step_lora_fp16.safetensors --lora-strength 1.0 \
  --steps 4 --cfg 1 --sampler lcm --scheduler sgm_uniform
```

The authors' README is explicit that LCMScheduler's default timesteps differ from the ones it
was trained on and asks for `timesteps=[999, 749, 499, 249]`; for SDXL's scaled_linear schedule
the equivalent sigmas are `14.614641, 4.081729, 1.612886, 0.693205, 0.0`, feedable through the
`SigmasFromList` node + `SamplerCustom` if the KSampler defaults disappoint. Strength 1.0 suits
the SDXL base it shipped for; the README advises lowering it for community merges, so sweep
0.6–1.0 on a Pony merge like CyberRealistic. 4-step output runs slightly brighter than 28-step
(measured mean 174 vs 149) — expected for a distilled adapter, not a failure.

## The one thing not to get wrong

The bundled workflow uses `SamplerCustom` + `SigmasFromList`, not `KSampler`.

Turbo ships a fixed 8-step sigma schedule whose tail is heavily non-uniform
(`… 0.704534, 0.414568`). A generic scheduler at `steps=8` produces a near-uniform
schedule and visibly worse output. `SigmasFromList` feeds the checkpoint's own
values verbatim.

If the user asks you to change step count, change the sigma list — not the step
count, and never swap in `KSampler`.

**And do not use this workflow for the base (non-Turbo) model.** Base
`qwen_image_2.1_bf16.safetensors` needs ~25 steps with `KSampler`; running it
through this 8-step schedule is wrong in the other direction.

## Contents

| Path | What |
|------|------|
| `scripts/turbo_t2i.py` | The generator. Preflight + single/batch. |
| `workflows/qwen21-turbo-3x4.json` | API-format workflow, 8-step, 1008×1344, `{{prompt}}`/`{{seed}}` placeholders. Also consumable by the workspace's `scripts/comfy_gen.py --template`. |
| `workflows/qwen21-turbo-lora-3x4.json` | Same, with one LoRA spliced in. |
| `workflows/qwen21-turbo-loras-3x4.json` | Two chained LoRA slots; selected automatically by `--lora`. |
| `workflows/qwen21-turbo-ui.json` | Graph-format copy for dragging onto the ComfyUI canvas. |
| `reference.md` | Deployment layout, verification commands, and the network pitfalls hit while installing. |

## Editing the workflow

`workflows/qwen21-turbo-3x4.json` is hand-editable JSON (node ids keyed
`class_type`/`inputs`, prompts substituted as `{{prompt}}`). After changing node
wiring, regenerate and re-verify with the workspace tooling:

```bash
python3 scripts/ui_to_api.py <ui.json> --prompt "test" --out /tmp/x.png --submit
```

A structural self-check is not sufficient — ComfyUI only rejects wiring problems
(missing required input, dependency cycles) at submit time, so run the round-trip.