# qwen-image-2-1-turbo

Text-to-image and image editing on a local ComfyUI with **Qwen-Image-2.1-Turbo**, the
8-step distilled checkpoint. Offline, no API key, images never leave the machine.

## What it is good at

- **Editing**: the only one of the local models with a reference/edit path (feed it an image,
  ask for a change).
- Transparent PNG output (native RGBA) and clean single-line English headlines.

## Prerequisites

- macOS with Apple Silicon, a local ComfyUI
- Weights: `qwen_image_2.1_turbo_bf16.safetensors`, `qwen3vl_8b_bf16.safetensors`,
  `qwen_image_2.1_vae_bf16.safetensors`
- The `SigmasFromList` custom node (the 8-step route needs the official sigma table)

## Run

```bash
python3 scripts/turbo_t2i.py \
    --prompt "cinematic portrait, 30-year-old woman, window light" \
    --out ~/Pictures/out.png --seed 42
```

## Files

| File | Use |
|---|---|
| `SKILL.md` | the instructions an agent follows |
| `scripts/turbo_t2i.py` | the driver (turbo / base / SDXL routes) |
| `workflows/` | API-format ComfyUI graphs |
| `reference.md` | deployment layout and the network pitfalls hit while installing |

## License

Qwen-Image-2.1 ships under the qwen-research license — check it before commercial use.
Model weights are not included here.
