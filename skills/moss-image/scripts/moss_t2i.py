#!/usr/bin/env python3
"""Generate images with MOSS-Image on the user's local ComfyUI, picking LoRAs from the prompt.

The LoRA choice is a *declarative routing table* (../lora_routes.json), not a guess:
rules are ordered, each lists keywords that must/must-not appear, and the first rule
whose conditions all hold wins. Ask for the decision with --explain.

Two base routes:
  default   8-step DMD LoRA at CFG 1.0   -> ~40 s at 1024x1024
  --slow    50-step base at CFG 3.0      -> ~8 min, official quality

Auto-selected LoRAs that were distilled for CFG 3 automatically switch steps/cfg.

Usage:
    moss_t2i.py --prompt "..." --out out.png
    moss_t2i.py --prompt "..." --out out.png --explain     # show routing, generate nothing
    moss_t2i.py --prompt "..." --out out.png --no-auto-lora
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROUTES = SKILL / "lora_routes.json"

SERVER = os.environ.get("COMFYUI_SERVER", "http://127.0.0.1:8188")

UNET = "moss_image_sft_bf16.safetensors"
CLIP = "qwen3.5_9b_bf16.safetensors"
VAE = "flux2-vae.safetensors"
DMD_LORA = "MOSS-8steps-dmd-lora.safetensors"

# Model card: dims must be multiples of 16 and land near 1M / 1.5M / 2M pixels.
RATIO_SIZE = {
    "1:1": (1024, 1024), "4:3": (1152, 864), "3:4": (864, 1152),
    "3:2": (1216, 816), "2:3": (816, 1216), "16:9": (1344, 768), "9:16": (768, 1344),
    "1:1-2k": (1456, 1456), "16:9-2k": (1536, 864),
}

DEFAULT_NEGATIVE = "worst quality, bad anatomy, watermark, jpeg artifact, blurry, out of focus"


# ---------------------------------------------------------------- LoRA routing

KEY_ALIASES = {
    "man": ("man", "men", "male", "males", "boy", "boys", "guy", "guys", "gentleman"),
    "male": ("male", "males", "man", "men", "boy", "boys", "guy", "guys", "gentleman", "his", "him"),
    "woman": ("woman", "women", "female", "females", "lady", "ladies", "girl", "girls"),
    "asian": ("asian", "chinese", "korean", "japanese", "east asian", "东亚", "亚洲", "中国", "韩国", "日本"),
}


def _variants(key):
    return KEY_ALIASES.get(key.lower(), (key,))


def _has(word: str, text: str) -> bool:
    """Substring for CJK (no word boundaries), word-bounded for latin.

    Word boundaries matter: an unbounded 'cat' matches 'category', which silently
    triggers the wrong rule.
    """
    if any("\u4e00" <= ch <= "\u9fff" for ch in word):
        return word in text
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def route(prompt: str):
    """Return (list of {lora, strength, trigger, rule}, list of skipped-with-reason)."""
    cfg = json.loads(ROUTES.read_text())
    table = cfg["loras"]
    text = " " + prompt.lower().replace("-", " ") + " "
    chosen, notes = {}, []

    for rule in cfg["rules"]:
        cond = rule["when"]

        def present(keys):
            """Return the keys that matched (via any alias)."""
            return [k for k in keys if any(_has(v.lower(), text) for v in _variants(k))]

        hit_any = present(cond.get("any", [])) if cond.get("any") else ["*"]
        hit_all = present(cond.get("all", [])) if cond.get("all") else ["*"]
        blocked = present(cond.get("not", [])) if cond.get("not") else []

        if not hit_any:
            continue
        if cond.get("all") and len(hit_all) != len(cond["all"]):
            missing = sorted(set(cond["all"]) - set(hit_all))
            notes.append(f"{rule['id']}: needs all of {cond['all']}, missing {missing}")
            continue
        if blocked:
            notes.append(f"{rule['id']}: blocked by {blocked}")
            continue

        for name in rule["use"]:
            spec = table.get(name)
            if spec is None:
                notes.append(f"{rule['id']}: {name} not in lora table")
                continue
            slot = spec.get("slot", "look")
            if slot in chosen and chosen[slot]["prio"] >= rule.get("priority", 0):
                notes.append(f"{rule['id']}: {name} loses slot '{slot}' to {chosen[slot]['name']}")
                continue
            chosen[slot] = {"name": name, "strength": spec.get("strength", 0.7),
                            "trigger": spec.get("trigger", ""), "rule": rule["id"],
                            "prio": rule.get("priority", 0),
                            "steps": spec.get("steps"), "cfg": spec.get("cfg")}

    return list(chosen.values()), notes


def apply_triggers(prompt, auto):
    """Prepend trigger phrases only when they are real words, not session ids."""
    words = [a["trigger"] for a in auto if a["trigger"] and "training_" not in a["trigger"]]
    if not words:
        return prompt
    low = prompt.lower()
    missing = [wd for wd in words if wd.lower() not in low]
    return (", ".join(missing) + ", " + prompt) if missing else prompt


# ---------------------------------------------------------------- ComfyUI

def api(path, payload=None, timeout=60):
    url = SERVER + path
    if payload is None:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def preflight():
    try:
        api("/system_stats", timeout=5)
    except Exception:
        sys.exit(f"No ComfyUI listening on {SERVER}. Start Comfy Desktop first.")
    seen = {}
    for node, key, folder in (
        ("UNETLoader", "unet_name", "diffusion_models"),
        ("CLIPLoader", "clip_name", "text_encoders"),
        ("VAELoader", "vae_name", "vae"),
        ("LoraLoaderModelOnly", "lora_name", "loras"),
    ):
        try:
            seen[folder] = api(f"/object_info/{node}")[node]["input"]["required"][key][0]
        except Exception:
            seen[folder] = []
    for name, folder in ((UNET, "diffusion_models"), (CLIP, "text_encoders"), (VAE, "vae")):
        if seen.get(folder) and name not in seen[folder]:
            sys.exit(f"{name} is not visible to ComfyUI ({folder}/). "
                     f"Symlink it into ~/ComfyUI-Shared/models/{folder}/ and refresh.")
    if "moss_image" not in str(api("/object_info/CLIPLoader"))[:20000]:
        sys.exit("This ComfyUI build has no moss_image encoder type (needs v0.42+ with the MOSS patch).")
    return seen


def build(prompt, negative, w, h, seed, steps, cfg, chain):
    """chain: list of (lora_name, strength). Each becomes a LoraLoaderModelOnly."""
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "moss_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "7": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["6", 0], "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "moss"}},
    }
    link = ["1", 0]
    for i, (name, strength) in enumerate(chain):
        nid = str(20 + i)
        g[nid] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": link, "lora_name": name, "strength_model": strength}}
        link = [nid, 0]
    g["7"]["inputs"]["model"] = link
    return g


def run(graph, timeout):
    pid = api("/prompt", {"prompt": graph})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = api(f"/history/{pid}")
        if pid in h:
            e = h[pid]
            status = e.get("status", {})
            if status.get("status_str") == "error":
                for m in status.get("messages", []):
                    if m[0] == "execution_error":
                        sys.exit(f"ComfyUI error: {m[1].get('exception_message', '')[:600]}")
                sys.exit("ComfyUI reported an error")
            imgs = [i for o in e.get("outputs", {}).values() for i in o.get("images", [])]
            return imgs, time.time() - t0
        time.sleep(2)
    sys.exit(f"Timed out after {timeout}s")


def fetch(img, dst: Path):
    q = urllib.parse.urlencode({"filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")})
    with urllib.request.urlopen(f"{SERVER}/view?{q}", timeout=120) as r:
        data = r.read()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser(description="MOSS-Image text-to-image via local ComfyUI")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True, help="destination .png")
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--ratio", default="1:1", choices=sorted(RATIO_SIZE))
    ap.add_argument("--size", help="override WxH, e.g. 1344x1024 (both must be /16)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--slow", action="store_true",
                    help="50 steps at CFG 3 without the DMD LoRA (official quality, ~8 min)")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--lora", action="append", default=[],
                    help="force a LoRA (repeatable); disables auto-routing")
    ap.add_argument("--strength", type=float, default=0.7)
    ap.add_argument("--no-auto-lora", action="store_true")
    ap.add_argument("--no-dmd", action="store_true", help="skip the 8-step DMD acceleration LoRA")
    ap.add_argument("--explain", action="store_true", help="print the routing decision and exit")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()

    if a.size:
        w, h = (int(x) for x in a.size.lower().split("x"))
    else:
        w, h = RATIO_SIZE[a.ratio]
    if w % 16 or h % 16:
        sys.exit(f"{w}x{h}: both dimensions must be multiples of 16")

    # ---- LoRA decision
    if a.lora:
        auto = []
        forced = [(n, a.strength) for n in a.lora]
    else:
        auto, notes = route(a.prompt) if not a.no_auto_lora else ([], [])
        forced = []
    chain = forced or [(x["name"], x["strength"]) for x in auto]

    steps = a.steps or (50 if a.slow else 8)
    cfg = a.cfg if a.cfg is not None else (3.0 if a.slow else 1.0)

    # A CFG-3 LoRA cannot live on a CFG-1 rail; honour the LoRA's own config.
    for x in auto:
        if x.get("steps") and a.steps is None:
            steps = x["steps"]
        if x.get("cfg") and a.cfg is None:
            cfg = x["cfg"]

    use_dmd = (not a.slow) and (not a.no_dmd) and cfg <= 1.05
    if use_dmd and cfg <= 1.05:
        chain = [(DMD_LORA, 1.0)] + chain
    elif not a.slow and cfg > 1.05:
        steps = steps if a.steps else 30

    if a.explain:
        print(f"prompt : {a.prompt[:100]}{'...' if len(a.prompt) > 100 else ''}")
        print(f"size   : {w}x{h}  steps={steps}  cfg={cfg}  dmd={'on' if use_dmd else 'off'}")
        if a.lora:
            print("route  : forced via --lora")
        elif not auto:
            print("route  : no rule matched -> plain MOSS-Image")
        for x in auto:
            print(f"  + {x['name']:<48} @{x['strength']}  [{x['rule']}]")
        for n in (notes if not a.no_auto_lora else []):
            print(f"  - {n}")
        print("chain  :", " -> ".join(f"{n}@{s}" for n, s in chain) or "(none)")
        return

    seed = a.seed if a.seed is not None else int.from_bytes(os.urandom(4), "big") % (2**31)
    prompt = apply_triggers(a.prompt, auto) if auto else a.prompt

    preflight()
    print(f"moss {w}x{h} steps={steps} cfg={cfg} seed={seed}")
    if auto:
        for x in auto:
            print(f"  auto + {x['name']} @{x['strength']}  [{x['rule']}]")
    elif not a.lora:
        print("  no LoRA matched")
    print(f"  chain: {' -> '.join(n for n, _ in chain) or '(none)'}", flush=True)

    graph = build(prompt, a.negative, w, h, seed, steps, cfg, chain)
    imgs, took = run(graph, a.timeout)
    if not imgs:
        sys.exit("no image returned")
    dst = Path(a.out).expanduser().resolve()
    size = fetch(imgs[0], dst)
    print(f"DONE {took:.0f}s  {dst}  ({size/1e6:.1f} MB)")
    print(f"seed={seed}")


if __name__ == "__main__":
    main()
