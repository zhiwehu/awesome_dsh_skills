#!/usr/bin/env python3
"""FLUX 3 Image Klein (BFL, 5.6B distilled) text-to-image driver for the local ComfyUI.

FLUX 3 Klein = 5.6B single-stream DiT, step-distilled (16 steps, CFG 1.0) + Qwen3-VL-4B
text encoder + FLUX.2 VAE.  Uses `flux3` CLIPLoader type and ModelSamplingFlux shift
2.77259, matching BFL's official ComfyUI graph.

Verified on this Mac 2026-10-18: 16 steps, 1024x1024 -> 186 s warm / 338 s cold, M4 Max.

Usage:
  python3 flux3_klein_t2i.py --prompt "..." --out gallery/flux3klein/x.png [options]

Options:
  --out PATH          output png (default gallery/flux3klein/<timestamp>.png)
  --seed N            default: random
  --steps N           default 16 (BFL's distilled setting)
  --cfg F             default 1.0 (distilled => guidance off; do not raise)
  --sampler S         default euler
  --scheduler S       default simple
  --ratio R           one of 1:1 3:4 4:3 2:3 3:2 16:9 9:16 (1024-class)
  --width/--height    explicit pixel size, overrides --ratio (model is native up to 4K)
  --lora NAME[@STR]   add a LoraLoaderModelOnly (repeatable); must be a Flux.3 Klein LoRA
  --unet/--clip/--vae override the weight filenames
  --no-model-sampling skip ModelSamplingFlux (A/B against the official graph)
  --template PATH     workflow template (default ../workflows/flux3-klein-t2i.json)
  --dry-run           print the resolved workflow and exit
"""
import argparse, json, os, random, re, shutil, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = next((p for p in (os.path.join(HERE, "..", "workflows", "flux3-klein-t2i.json"),
                             os.path.join(ROOT, "workflows", "flux3-klein-t2i.json"),
                             os.path.join(ROOT, "docs", "flux3-klein-workflows",
                                          "api_t2i_minimal.json"))
                 if os.path.exists(p)),
                os.path.join(HERE, "..", "workflows", "flux3-klein-t2i.json"))
SERVER = os.environ.get("COMFYUI_SERVER", "http://127.0.0.1:8188")
DEFAULT_OUTDIR = os.environ.get(
    "FLUX3_OUTDIR", os.path.expanduser("~/Pictures/flux3klein"))
COMFY_OUTPUT = os.environ.get(
    "COMFY_OUTPUT", os.path.expanduser("~/ComfyUI-Shared/output"))

# The only MPS-safe build.  Apple MPS cannot execute fp8/int8 at all, so the
# int8-convrot and nvfp4 variants published alongside this one will not run here.
UNET = "flux3-image-klein-bf16.safetensors"
CLIP = "qwen3vl_4b_bf16.safetensors"      # shared with Krea 2
VAE = "flux2-vae.safetensors"
SHIFT = 2.77259                            # = log(16), BFL's official graph value

RATIOS = {  # 1024-class buckets; the model is native up to 4K
    "1:1": (1024, 1024), "3:4": (1024, 1344), "4:3": (1344, 1024),
    "2:3": (1024, 1536), "3:2": (1536, 1024), "16:9": (1536, 864), "9:16": (864, 1536),
}


def http_json(url, data=None, timeout=60):
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    if data is not None:
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def preflight(unet, clip, vae):
    """Fail early with an actionable message instead of a ComfyUI stack trace."""
    try:
        http_json(SERVER + "/system_stats", timeout=10)
    except Exception as e:
        sys.exit(f"[flux3] ComfyUI not reachable at {SERVER}: {e}\n"
                 f"        Open Comfy Desktop (do not start a second instance) and retry.")
    problems = []
    for node, field, wanted in (("UNETLoader", "unet_name", unet),
                                ("CLIPLoader", "clip_name", clip),
                                ("VAELoader", "vae_name", vae)):
        info = http_json(f"{SERVER}/object_info/{node}", timeout=30)[node]
        choices = info["input"]["required"][field][0]
        if wanted not in choices:
            problems.append(f"{wanted} not visible to {node}\n      available: {choices}")
    if problems:
        sys.exit("[flux3] preflight failed:\n  - " + "\n  - ".join(problems) +
                 "\n        If a weight is missing, Comfy Desktop only scans "
                 "~/ComfyUI-Shared/models — check the symlink there (see reference.md).")
    print(f"[flux3] preflight OK: Klein DiT + Qwen3-VL-4B + FLUX.2 VAE visible", flush=True)


def parse_lora(spec, default_strength):
    """'file.safetensors@0.7' -> (file, 0.7)"""
    if "@" in spec:
        name, _, st = spec.rpartition("@")
        try:
            return name, float(st)
        except ValueError:
            pass
    return spec, default_strength


def fill(obj, mapping):
    """Substitute {{placeholders}} recursively; coerce numeric-looking values."""
    if isinstance(obj, dict):
        return {k: fill(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v, mapping) for v in obj]
    if isinstance(obj, str):
        m = re.fullmatch(r"\{\{(\w+)\}\}", obj.strip())
        if m:
            return mapping[m.group(1)]
        return re.sub(r"\{\{(\w+)\}\}", lambda x: str(mapping[x.group(1)]), obj)
    return obj


def build(args, available_loras):
    wf = json.load(open(args.template))
    steps = args.steps

    # Optional LoRA chain: LoraLoaderModelOnly chained between UNETLoader and the sampler.
    model_src = "1"
    if args.lora:
        for i, spec in enumerate(args.lora, start=100):
            name, strength = parse_lora(spec, 1.0)
            if available_loras and name not in available_loras:
                print(f"[flux3] LoRA not visible to ComfyUI, skipping: {name}", flush=True)
                continue
            wf[str(i)] = {"class_type": "LoraLoaderModelOnly",
                          "inputs": {"lora_name": name, "strength_model": strength,
                                     "model": [model_src, 0]}}
            model_src = str(i)

    mapping = {
        "unet": args.unet, "clip": args.clip, "vae": args.vae,
        "prompt": args.prompt, "width": args.width, "height": args.height,
        "seed": args.seed, "steps": steps, "cfg": args.cfg,
        "sampler": args.sampler, "scheduler": args.scheduler,
        "max_shift": SHIFT, "base_shift": SHIFT,
        "model_source": model_src if args.model_sampling else "1",
        "prefix": args.prefix,
    }
    wf = fill(wf, mapping)

    if not args.model_sampling:
        # drop ModelSamplingFlux (node 6) and repoint the sampler at the raw model
        wf.pop("6", None)
        wf["7"]["inputs"]["model"] = [model_src, 0]
    return wf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--steps", type=int, default=16)
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--scheduler", default="simple")
    ap.add_argument("--ratio", default="1:1", choices=sorted(RATIOS))
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    # NOTE: argparse eats '-1' inside nargs; ask users to use NAME@-1 form instead.
    ap.add_argument("--lora", action="append", default=[])
    ap.add_argument("--unet", default=UNET)
    ap.add_argument("--clip", default=CLIP)
    ap.add_argument("--vae", default=VAE)
    ap.add_argument("--no-model-sampling", dest="model_sampling",
                    action="store_false", default=True)
    ap.add_argument("--template", default=TEMPLATE)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.cfg != 1.0:
        print(f"[flux3] warning: Klein is step-distilled; CFG {args.cfg} is off-recipe. "
              f"1.0 is the official setting.", flush=True)

    w = args.width or RATIOS[args.ratio][0]
    h = args.height or RATIOS[args.ratio][1]
    args.width, args.height = w, h
    args.seed = args.seed if args.seed is not None else random.randint(0, 2**48)
    name = os.path.splitext(os.path.basename(args.out))[0] if args.out else f"klein_{args.seed}"
    args.prefix = f"flux3klein/{name}_{args.seed}"
    out = args.out or os.path.join(DEFAULT_OUTDIR, f"{name}.png")

    available_loras = []
    if args.lora or args.dry_run:
        try:
            info = http_json(f"{SERVER}/object_info/LoraLoaderModelOnly", timeout=30)
            available_loras = info["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0]
        except Exception:
            pass

    wf = build(args, available_loras)
    if args.dry_run:
        print(json.dumps(wf, indent=2))
        return

    preflight(args.unet, args.clip, args.vae)
    r = http_json(SERVER + "/prompt",
                  {"prompt": wf, "client_id": f"flux3-{args.seed}"}, timeout=120)
    if r.get("node_errors"):
        sys.exit(f"[flux3] workflow rejected: {json.dumps(r['node_errors'])[:900]}")
    pid = r["prompt_id"]
    print(f"[flux3] queued {pid}  seed={args.seed}  {w}x{h}  {args.steps} steps  "
          f"cfg={args.cfg}  {args.sampler}/{args.scheduler}", flush=True)

    t0 = time.time()
    while time.time() - t0 < args.timeout:
        m = re.search(r'"(?:Float8_e4m3fn|Float8_e5m2)" not implemented',
                      json.dumps(http_json(SERVER + "/queue", timeout=30)))
        h_ = http_json(f"{SERVER}/history/{pid}", timeout=30)
        if h_:
            e = list(h_.values())[0]
            st = e.get("status", {}).get("status_str")
            if st != "success":
                msgs = e.get("status", {}).get("messages", [])
                sys.exit(f"[flux3] generation failed: {json.dumps(msgs)[-900:]}")
            files = [im for o in e.get("outputs", {}).values() for im in o.get("images", [])]
            if not files:
                sys.exit("[flux3] no image produced")
            f = files[-1]
            src = os.path.join(COMFY_OUTPUT, f.get("subfolder", ""), f["filename"])
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            shutil.copyfile(src, out)
            print(f"[flux3] done in {time.time()-t0:.0f}s -> {out}  (seed {args.seed})")
            return
        time.sleep(5)
    sys.exit(f"[flux3] timeout after {args.timeout}s waiting for {pid}")


if __name__ == "__main__":
    main()
