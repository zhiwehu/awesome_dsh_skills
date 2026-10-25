# flux3-klein

Photoreal / cinematic / product stills on a local ComfyUI with **FLUX 3 Klein** (Black Forest
Labs, 5.6B distilled). Offline, no API key, nothing leaves the machine.

## What it is good at

- The most photoreal of the local models: skin texture, knit, bokeh, rain-on-glass.
- The most literal prompt follower — complex camera angles and poses land.
- 16 steps at CFG 1; ~105 s for 1024x1344 on an M4 Max.

## Prerequisites

- macOS with Apple Silicon, a local ComfyUI (tested on 0.42.0)
- Weights: `flux3-image-klein-bf16.safetensors`, `qwen3vl_4b_bf16.safetensors`, `flux2-vae.safetensors`
- To go past ~2 MP use `VAEDecodeTiled`: plain `VAEDecode` raises
  `MPSGaph does not support tensor dims larger than INT_MAX` at 2048x2048.

## Run

```bash
python3 scripts/flux3_klein_t2i.py \
    --prompt "rain-slicked Paris street corner, 85mm" \
    --out ~/Pictures/out.png --ratio 3:4
```

## Files

| File | Use |
|---|---|
| `SKILL.md` | the instructions an agent follows |
| `scripts/flux3_klein_t2i.py` | the driver |
| `workflows/` | API-format ComfyUI graphs |
| `reference.md` | architecture, install layout, MPS pitfalls, license |

## License

FLUX Kommunity license: free commercial use below USD 5M annual revenue. Model weights are
not included here.
