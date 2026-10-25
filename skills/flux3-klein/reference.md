# flux3-klein · reference

Everything measured on this machine (M4 Max, 137 GB unified, ComfyUI 0.41.2, PyTorch 2.12.1,
MPS backend) on **2026-10-18**.

## 1. What FLUX 3 Image Klein is

Black Forest Labs, released **2026-10-15**, open weights under the FLUX Kommunity License.

- **5.6B** single-stream DiT image generator (text encoders not counted).
- One architecture covers **text-to-image, image editing (up to 10 reference images), and
  bounding-box layout control**, at up to **4K**.
- Two published variants:
  - **Klein** (distilled): **16 steps, no guidance** — the fast/generation model.
  - **Klein Base** (undistilled): 50 steps, CFG 3.5 — for fine-tuning, LoRA training, research.
    LoRAs trained on Base work on Klein with partial compatibility.
- BFL's own numbers: 1MP in ~4 s on an RTX 5090, <9 s on an RTX 4070 through ComfyUI.

BFL's launch post claims Klein leads its internal text-to-image / multi-reference / editing
Elo comparison "ahead of larger open weights models" and above Ideogram V4.5 and FLUX.2
[pro]. That is a **vendor self-evaluation**; treat it as directional. It explicitly notes
**Krea 2 does not support image editing** and was therefore excluded from the editing
comparison. Parameter counts cited: Klein 5.6B, Qwen-Image 2.1 7B, Krea 2 12.9B.

## 2. Install layout on this Mac

Comfy Desktop only scans `~/ComfyUI-Shared/models` (the active extra-model-paths config is
`~/Library/Application Support/Comfy Desktop/instance-model-paths/inst-*.yaml`, which sets
`comfy.desktop_0.base_path = ~/ComfyUI-Shared/models, is_default: true`).
The real bytes live in the workspace and are **symlinked** in — the same convention already
used for `krea2Anime_v20_bf16` and `qwen_image_2.1_turbo_bf16`.

```
~/ComfyUI-Shared/models/                                  <- bytes
├── diffusion_models/flux3-image-klein-bf16.safetensors      11,097,404,512 B
├── vae/flux2-vae.safetensors                                   336,211,292 B
└── text_encoders/qwen3vl_4b_bf16.safetensors                 8,875,719,384 B  (shared w/ Krea 2)

~/ComfyUI-Shared/models/                                    <- symlinks
├── diffusion_models/flux3-image-klein-bf16.safetensors -> ...
├── vae/flux2-vae.safetensors                           -> ...
└── text_encoders/qwen3vl_4b_bf16.safetensors           -> ...
```

**If the workspace moves, the symlinks dangle and Klein disappears from the loaders.** Repair:

```bash
ln -sfn "<new>/models/diffusion_models/flux3-image-klein-bf16.safetensors" \
  ~/ComfyUI-Shared/models/diffusion_models/flux3-image-klein-bf16.safetensors
ln -sfn "<new>/models/vae/flux2-vae.safetensors" ~/ComfyUI-Shared/models/vae/flux2-vae.safetensors
```

ComfyUI must be **restarted** after adding a model for it to appear in `object_info`.

### SHA256 (verified against Hugging Face)

| File | SHA256 |
|---|---|
| flux3-image-klein-bf16.safetensors | `c3e9813cdd049c831c836b2e9db61150e49a93fc1a4c63b256494642fee0bd7c` |
| flux2-vae.safetensors | `868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3` |

### How it was obtained (the download is non-obvious)

1. **Both official channels are gated.** `black-forest-labs/flux-3-image-klein-comfy` on HF
   reports `gated: auto` → `401 Access to model ... is restricted`; Civitai needs
   `CIVITAI_TOKEN` and returns `401 requires you to be logged in`. ModelScope is
   `ApprovalMode: 2` (also gated). Use the **ungated byte-identical mirror**
   `ml-resources/flux-3-image-klein-comfy` instead (74k downloads).
2. **The HF CDN is unreachable from here.** `us.aws.cdn.hf.co` (where LFS blobs actually
   live) is TLS-reset both directly *and* through every Clash node — small JSON files work
   because only blobs route to that host. **hf-mirror.com works, but only without the
   proxy** (with it: connection fails).
   ```bash
   env -u https_proxy -u http_proxy curl -L -C - -o <dest> \
     "https://hf-mirror.com/ml-resources/flux-3-image-klein-comfy/resolve/main/<file>"
   ```
   Measured ~3.4 MB/s → ~55 min for the 11 GB model. (`hf download` fails: it targets xet
   and hits the same dead CDN.)
3. **The encoder is shared with Krea 2** — same `qwen3vl_4b` (713 BF16 tensors; local file
   8,875,719,384 B vs mirror 8,875,719,408 B, a 24-byte header difference). Do not download
   a second copy.

**Not installed:** `flux3-image-klein-base-*` (Klein Base, for LoRA training) and the
18.82 GB `qwen3.5_9b_flux3_prompt_upsampler_bf16.safetensors`. The official BFL workflows in
`docs/flux3-klein-workflows/` *do* reference the upsampler, so they will
not run as-is; this skill's template deliberately omits it.

## 3. Verified graph and settings

From BFL's official `flux3_klein_bf16_t2i.json` (a subgraph-based UI workflow), reduced to a
flat API graph by this skill:

```
UNETLoader(flux3-image-klein-bf16, default)
  -> ModelSamplingFlux(max_shift=2.77259, base_shift=2.77259, w, h)
  -> KSampler(seed, steps=16, cfg=1.0, euler, simple, denoise=1.0)
CLIPLoader(qwen3vl_4b_bf16, type="flux3")
CLIPTextEncode -> both positive and negative
EmptyFlux2LatentImage(w, h, 1)
VAELoader(flux2-vae) -> VAEDecode -> SaveImage
```

- `CLIPLoader` **type must be `flux3`** (present in ComfyUI 0.41.2's enum).
- Shift `2.77259` = `log(16)`; the official graph also computes `log(a)` from a step
  primitive, which is the same value at 16 steps.
- Positive and negative are **the same conditioning** — at CFG 1.0 the negative is ignored.
  Never write a negative prompt for Klein.
- `Flux3LayoutPrompt` exists for prompt/bbox handling; the bounding-box path is **not**
  wired up in this skill.

Measured: **186 s warm, 338 s cold** for 1024×1024 / 16 steps (~11.6 s per step plus load).

## 4. Apple MPS: the one thing that breaks everything

**MPS cannot execute fp8 or int8 tensors.** Krea 2 hit this first; the same applies to
Klein. Published alongside the bf16 files are `-int8-convrot`, `-nvfp4` (and an fp8 build in
some repos). Loading any of them raises a `Float8_e4m3fn` / `Float8_e5m2` TypeError at
`CLIPTextEncode` **and** again at `KSampler` — deleting only one of the two does not help.

`nvfp4` additionally requires a Blackwell GPU. **Use only the bf16 files.**

Dtype audit of the installed set (all safe):

| File | Tensors | Dtypes |
|---|---|---|
| flux3-image-klein-bf16 | 360 | 359 × BF16, 1 × bfloat16 |
| flux2-vae | 251 | 250 × F32, 1 × I64 |
| qwen3vl_4b_bf16 | 713 | 713 × BF16 |

Also note `qwen3vl_4b_fp8_scaled.safetensors` sits in the same folder — it is fp8 and must
not be selected as Klein's encoder.

## 5. Ecosystem position (Civitai, counted 2026-10-18)

| Base model | LoRAs | Checkpoints |
|---|---|---|
| **Flux.3 Klein** | **~6** | ~3 |
| Qwen 2.1 | ~115 | ~21 |
| Krea 2 | ~5,990 | ~97 |

Klein is 3 days old at time of writing, so its LoRA ecosystem is effectively empty. HF
downloads tell the same story: Qwen-Image-2.1 165,326 / 3,344 likes vs
flux-3-image-klein 22,790 / 416 likes.

**LoRA compatibility: Flux.3 Klein / Klein-Base LoRAs only.** FLUX.1, FLUX.2 and Krea 2
LoRAs are not compatible. Note Civitai's base-model filter string is `Flux.3 Klein`
(the model id 3003556 is `CivitaiOfficial`'s mirror of BFL's release).

## 6. Routing on this machine

| Need | Skill / model |
|---|---|
| Photoreal, cinematic, product, landscape, 4K, fastest | **flux3-klein** |
| Literal rendered text, Chinese typography, posters | `qwen-image-2-1-turbo` |
| Transparent PNG / native RGBA | `qwen-image-2-1-turbo` |
| Image editing / multi-reference | `qwen-image-2-1-turbo`, or wire Klein's edit workflow |

All three share the **one** ComfyUI at `127.0.0.1:8188`. Never start a second instance —
Comfy Desktop and ComfyUI share a database, and a second instance on another port fails.

## 7. Editing (not yet wired)

Klein supports editing, multi-reference (up to 10 images) and bounding-box layout, and BFL
ships `image_flux3_klein_distilled_image_edit.json`,
`..._distilled_image_edit_boundingbox_v2.json`, `image_flux3_klein_image_edit.json` and
`image_flux3_klein_t2i.json` (the `_sd_` / Klein-Base equivalents too). These live in
`docs/flux3-klein-workflows/` (the four fetched so far) and are the
starting point if the user wants editing locally. That path is untested on this machine.

## 8. License

**FLUX Kommunity License.** The model and anything derived from it (LoRAs, fine-tunes) are
**non-commercial**, and derivatives must carry the same license. Users and companies with
**under US$5M annual revenue may use generated images commercially**; larger commercial use
requires a license from Black Forest Labs. Contrast with Qwen-Image 2.1's Qwen Research
License, which is more restrictive for commercial output.

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Float8_e4m3fn` / `Float8_e5m2` TypeError | fp8/int8 weight loaded | switch to the bf16 filename |
| Klein absent from `UNETLoader` list | symlink missing, or ComfyUI not restarted | re-create the symlink, restart ComfyUI |
| Black / flat image | FLUX.1/2 LoRA hung on Klein, or CFG raised above 1.0 | remove LoRA, `--cfg 1.0` |
| `CLIPLoader` type error | template used the wrong type | must be `flux3` |
| Burnt / muddy output | CFG too high | Klein is distilled: CFG must be 1.0 |
| ComfyUI unreachable | server not running | open Comfy Desktop, retry once |
| `preflight failed: ... not visible` | weight missing or symlink dangling | see §2 |
