# moss-image

Text-to-image on a local ComfyUI with **MOSS-Image** (5B DiT + a Qwen3.5-9B text encoder,
Apache-2.0), plus a community 8-step DMD LoRA that makes it the fastest local model here.

## What it is good at

- **Rendered text.** It writes whole passages of Chinese that are actually readable —
  blackboards, menus, shop signs, posters — where other local models dissolve into
  pseudo-glyphs.
- Speed: ~70 s for 1024x1344 on an M4 Max, the fastest of the four models measured.

## Prerequisites

- macOS with Apple Silicon, a local ComfyUI **0.42+** (needs the `moss_image` encoder type)
- Weights: `moss_image_sft_bf16.safetensors`, `qwen3.5_9b_bf16.safetensors`,
  `flux2-vae.safetensors`, `MOSS-8steps-dmd-lora.safetensors`

## Run

```bash
python3 scripts/moss_t2i.py \
    --prompt 'a green blackboard filled with calculus, "换元法" in the corner' \
    --out ~/Pictures/board.png
```

## Files

| File | Use |
|---|---|
| `SKILL.md` | the instructions an agent follows |
| `scripts/moss_t2i.py` | the driver |
| `lora_routes.json` | prompt-keyword to LoRA routing table |

## License

Apache-2.0. Model weights are not included here.
