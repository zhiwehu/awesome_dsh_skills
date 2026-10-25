#!/usr/bin/env python3
"""Generate images with the local Qwen-Image-2.1-Turbo via ComfyUI.

Self-contained: talks to a ComfyUI server over /prompt and does not care which
process serves it, so it works against the user's Comfy Desktop instance.

Preflight is deliberate. ComfyUI and Comfy Desktop share one database, so
starting a second copy on another port fails; if nothing is listening we stop and
tell the user how to start theirs rather than fighting for the port.

Usage:
    turbo_t2i.py --prompt "a red panda astronaut" --out out.png
    turbo_t2i.py --prompt "..." --ratio 16:9 --seed 42 --out out.png
    turbo_t2i.py --prompts pages.json --outdir gallery/     # batch
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
DEFAULT_TEMPLATE = SKILL / "workflows" / "qwen21-turbo-3x4.json"
SERVER = os.environ.get("COMFYUI_SERVER", "http://127.0.0.1:8188")
TURBO_UNET = "qwen_image_2.1_turbo_bf16.safetensors"
BASE_TEMPLATE = SKILL / "workflows" / "qwen21-base-loras-3x4.json"
SDXL_TEMPLATE = SKILL / "workflows" / "sdxl-pony-loras-3x4.json"

# SDXL is a 1024-class model: its native buckets, not the 2K presets the Qwen
# templates are built around. Feeding it 1792x2400 produces duplicated anatomy.
SDXL_RATIO = {
    "1:1": (1024, 1024), "4:3": (1152, 896), "3:4": (896, 1152),
    "3:2": (1216, 832), "2:3": (832, 1216), "16:9": (1344, 768), "9:16": (768, 1344),
}

# CFG > 1 only matters with a negative prompt; at CFG 1 the encoder ignores it.
DEFAULT_NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra digits, missing digits, fused fingers, "
    "deformed, disfigured, mutated, blurry, out of focus, jpeg artifacts, "
    "watermark, signature, text, logo, cartoon, cgi, 3d render, plastic skin"
)

# Pony-family models are trained on a score/source tag scheme and degrade badly
# without the quality prefix in the positive and this scheme in the negative.
PONY_PREFIX = "score_9, score_8_up, score_7_up"
PONY_NEGATIVE = (
    "score_1, score_2, score_3, score_4, score_5, score_6, source_pony, source_furry, "
    "worst quality, low quality, normal quality, lowres, bad anatomy, bad hands, "
    "extra digits, fewer digits, jpeg artifacts, watermark, signature, text, username, blurry"
)

# Model-card resolution presets; the 3:4 template ships at 1008x1344.
RATIO_SIZE = {
    "1:1": (2048, 2048), "4:3": (2400, 1792), "3:4": (1792, 2400),
    "3:2": (2528, 1696), "2:3": (1696, 2528), "16:9": (2752, 1536), "9:16": (1536, 2752),
}


def http_json(path, data=None, timeout=120):
    req = urllib.request.Request(SERVER + path, headers={"Content-Type": "application/json"})
    if data is not None:
        req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            sys.exit("ComfyUI 拒绝了工作流 (HTTP %d):\n%s" % (e.code, json.dumps(json.loads(body), indent=2, ensure_ascii=False)[:1500]))
        except json.JSONDecodeError:
            sys.exit(f"ComfyUI 拒绝了工作流 (HTTP {e.code}):\n{body[:1500]}")
    except urllib.error.URLError:
        sys.exit(preflight_hint())


def preflight(template=None, ckpt=None):
    """Fail with actionable instructions instead of a stack trace.

    Validates whichever weights the *template* asks for: `UNETLoader` on the Qwen
    routes, `CheckpointLoaderSimple` on the SDXL route, so no route validates
    against another route's files. A `--ckpt` override is what gets checked, not
    the template default it replaces.
    """
    try:
        urllib.request.urlopen(SERVER + "/system_stats", timeout=5)
    except Exception:
        sys.exit(preflight_hint())
    unets, ckpts, needs_sigmas = [], [], False
    if template:
        try:
            tpl = json.load(open(template))
        except Exception:
            tpl = {}
        for node in tpl.values():
            ct = node.get("class_type")
            if ct == "UNETLoader":
                unets.append(node["inputs"]["unet_name"])
            elif ct == "CheckpointLoaderSimple":
                ckpts.append(ckpt or node["inputs"]["ckpt_name"])
            elif ct == "SigmasFromList":
                needs_sigmas = True
    if unets:
        have = http_json("/object_info/UNETLoader")["UNETLoader"]["input"]["required"]["unet_name"][0]
        missing = [n for n in unets if n not in have]
        if missing:
            sys.exit(
                f"ComfyUI 在跑，但看不到模板要用的底模: {', '.join(missing)}\n"
                f"  当前可用: {have or '(空)'}\n"
                "  权重挂在 ComfyUI-Shared/models/diffusion_models/，重启 ComfyUI 后再试。"
            )
    if ckpts:
        have = http_json("/object_info/CheckpointLoaderSimple")["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        missing = [n for n in ckpts if n not in have]
        if missing:
            sys.exit(
                f"ComfyUI 在跑，但看不到模板要用的 checkpoint: {', '.join(missing)}\n"
                f"  当前可用: {have or '(空)'}\n"
                "  checkpoint 放在 ComfyUI-Shared/models/checkpoints/ 下。"
            )
    if not unets and not ckpts:
        have = http_json("/object_info/UNETLoader")["UNETLoader"]["input"]["required"]["unet_name"][0]
        if TURBO_UNET not in have:
            sys.exit(f"ComfyUI 在跑，但看不到 {TURBO_UNET}（默认模板用的底模）。")
    if needs_sigmas and "SigmasFromList" not in http_json("/object_info"):
        sys.exit(
            "ComfyUI 在跑，但缺少 SigmasFromList 节点 —— Turbo 的 8 步 sigma 调度靠它。\n"
            "  该节点应位于 ComfyUI/custom_nodes/dsh_sigmas_from_list/，"
            "重启 ComfyUI 后再试。"
        )
    label = ", ".join(unets + ckpts) if (unets or ckpts) else TURBO_UNET
    print(f"[turbo] ComfyUI 就绪 @ {SERVER}, 底模已就位 ({label})")


def preflight_hint():
    return (
        f"连不上 ComfyUI ({SERVER})。\n\n"
        "  本机 ComfyUI 与 Comfy Desktop 共用同一个数据库，无法在别的端口再起一个，\n"
        "  所以不要自行启动 —— 请让用户打开 Comfy Desktop，它会监听 8188。\n"
        f"  打开后重试，或用 COMFYUI_SERVER=http://<host>:8188 指定其它已有实例。\n\n"
        "  确认用户已启动后，可先自查：\n"
        "    curl -s http://127.0.0.1:8188/system_stats | head -c 200"
    )


def subst(o, prompt, seed, negative=""):
    """Placeholders live in strings; width/height are ints, patched in generate()."""
    if isinstance(o, str):
        return (o.replace("{{prompt}}", prompt)
                 .replace("{{seed}}", str(seed))
                 .replace("{{negative}}", negative))
    if isinstance(o, dict):
        return {k: subst(v, prompt, seed, negative) for k, v in o.items()}
    if isinstance(o, list):
        return [subst(v, prompt, seed, negative) for v in o]
    return o


def apply_loras(wf, loras):
    """loras: list of (lora_name_or_None, strength). Patches the chained
    LoraLoaderModelOnly nodes in place, left to right.

    In API format the node id is the dict key, not a field on the node, so slots
    are collected by key and sorted numerically. `--lora` therefore always lands on
    the first loader in the chain regardless of how the template numbers them.
    """
    if not loras:
        return 0
    slots = sorted(
        ((k, v) for k, v in wf.items() if v.get("class_type") == "LoraLoaderModelOnly"),
        key=lambda kv: (0, int(kv[0])) if str(kv[0]).isdigit() else (1, 0),
    )
    if len(loras) > len(slots):
        sys.exit(f"模板只有 {len(slots)} 个 LoraLoaderModelOnly 节点，但传入了 {len(loras)} 个 LoRA。"
                 "需要更多请在模板里加节点。")
    for (_, node), (name, strength) in zip(slots, loras):
        if name:
            node["inputs"]["lora_name"] = name
        node["inputs"]["strength_model"] = strength
    return len(loras)


def generate(prompt, out_path, template, seed, width=None, height=None,
             loras=(), negative=None, steps=None, cfg=None, sampler=None,
             scheduler=None, ckpt=None, poll=8, max_wait=3600):
    raw = json.dumps(json.load(open(template)))
    for ph in ("{{prompt}}", "{{seed}}"):
        if ph not in raw:
            sys.exit(f"模板缺少占位符 {ph}: {template}")
    neg = DEFAULT_NEGATIVE if negative is None else negative
    wf = subst(json.load(open(template)), prompt, seed, neg)
    is_base = any(n.get("class_type") == "KSampler" for n in wf.values())
    for node in wf.values():
        ct = node.get("class_type")
        if ct == "EmptyLatentImage":
            if width:
                node["inputs"]["width"] = width
            if height:
                node["inputs"]["height"] = height
        elif ct == "KSampler":
            if steps is not None:
                node["inputs"]["steps"] = steps
            if cfg is not None:
                node["inputs"]["cfg"] = cfg
            if sampler:
                node["inputs"]["sampler_name"] = sampler
            if scheduler:
                node["inputs"]["scheduler"] = scheduler
        elif ct == "CheckpointLoaderSimple" and ckpt:
            # Civitai filenames never match the template default, so let the caller name it.
            node["inputs"]["ckpt_name"] = ckpt
        elif ct == "SamplerCustom" and cfg is not None:
            # Turbo path: only cfg is meaningful here, the sigma list fixes the steps.
            node["inputs"]["cfg"] = cfg
    if not is_base and (steps or sampler or scheduler):
        print("[turbo] 提示: 该模板走 SamplerCustom，步数由 sigma 列表决定，"
              "--steps/--sampler/--scheduler 不生效")
    n = apply_loras(wf, loras)
    if n:
        loaded = sorted(((k, v) for k, v in wf.items()
                         if v.get("class_type") == "LoraLoaderModelOnly"
                         and v["inputs"].get("strength_model")),
                        key=lambda kv: (0, int(kv[0])) if str(kv[0]).isdigit() else (1, 0))
        print(f"[turbo] 已应用 {n} 个 LoRA: " +
              ", ".join(f"{v['inputs']['lora_name']}@{v['inputs']['strength_model']}"
                        for _, v in loaded))

    pid = http_json("/prompt", {"prompt": wf, "client_id": "turbo-t2i"})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(poll)
        hist = http_json("/history/" + pid)
        if pid not in hist:
            continue
        status = hist[pid].get("status", {})
        if status.get("status_str") == "error":
            sys.exit("生成失败: " + json.dumps(status.get("messages", []), ensure_ascii=False)[:800])
        for _, o in hist[pid].get("outputs", {}).items():
            for img in o.get("images", []):
                q = urllib.parse.urlencode({"filename": img["filename"],
                                            "subfolder": img.get("subfolder", ""),
                                            "type": img.get("type", "output")})
                with urllib.request.urlopen(SERVER + "/view?" + q, timeout=180) as r:
                    data = r.read()
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(data)
                print(f"[turbo] {out_path}  ({len(data)//1024} KB, {time.time()-t0:.0f}s)")
                return out_path
    sys.exit("等待超时")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--prompts", help="JSON: {\"key\": {\"prompt\":..., \"seed\":..., \"file\":...}}")
    ap.add_argument("--out")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--base", action="store_true",
                    help="走 base 底模路线：25 步 KSampler + CFG>1 + 3 个 LoRA 槽")
    ap.add_argument("--sdxl", action="store_true",
                    help="走 SDXL 路线（Pony/Illustrious 系 checkpoint）：28 步、CFG 7、"
                         "3 个 LoRA 槽，尺寸用 1024 级桶而非 2K 预设")
    ap.add_argument("--ckpt",
                    help="SDXL 路线：checkpoint 文件名，覆盖模板默认值"
                         "（Civitai 下载的文件名通常和模板不同）")
    ap.add_argument("--ratio", choices=sorted(RATIO_SIZE))
    ap.add_argument("--size", help="任意像素尺寸 WxH（如 1152x1536），优先于 --ratio 预设")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--negative", default=None,
                    help="负面提示词（CFG>1 时才起作用；默认内置一串通用负向词）")
    ap.add_argument("--steps", type=int, help="仅 KSampler 模板：覆盖步数")
    ap.add_argument("--cfg", type=float, help="覆盖 CFG（base 路线推荐 2.5–4）")
    ap.add_argument("--sampler", help="仅 KSampler 模板：覆盖采样器，如 er_sde")
    ap.add_argument("--scheduler", help="仅 KSampler 模板：覆盖调度器，如 beta")
    ap.add_argument("--lora", action="append", default=[],
                    help="LoRA filename; repeat to chain. Order = load order.")
    ap.add_argument("--lora-strength", type=float, action="append", default=[],
                    help="Strength for the matching --lora (default 1.0 each)")
    ap.add_argument("--no-preflight", action="store_true")
    a = ap.parse_args()

    if not a.prompt and not a.prompts:
        ap.error("需要 --prompt 或 --prompts")

    if a.lora_strength and len(a.lora_strength) > len(a.lora):
        ap.error("--lora-strength 不能多于 --lora")
    strengths = list(a.lora_strength) + [1.0] * (len(a.lora) - len(a.lora_strength))
    loras = list(zip(a.lora, strengths))
    if a.sdxl and a.template == str(DEFAULT_TEMPLATE):
        a.template = str(SDXL_TEMPLATE)
    if a.base and a.template == str(DEFAULT_TEMPLATE):
        a.template = str(BASE_TEMPLATE)
    if loras and a.template == str(DEFAULT_TEMPLATE):
        a.template = str(SKILL / "workflows" / "qwen21-turbo-loras-3x4.json")
    if a.sdxl and a.negative is None:
        a.negative = PONY_NEGATIVE

    if not a.no_preflight:
        preflight(a.template, a.ckpt)

    ratio_table = SDXL_RATIO if a.sdxl else RATIO_SIZE
    if a.size:
        try:
            _w, _h = (int(x) for x in a.size.lower().replace("*", "x").split("x"))
        except Exception:
            ap.error("--size 需要 WxH 格式，例如 1152x1536")
        width, height = _w, _h
    else:
        width, height = (ratio_table[a.ratio] if a.ratio else (None, None))

    if a.prompts:
        pages = json.load(open(a.prompts))
        for key, spec in pages.items():
            p = spec["prompt"] if isinstance(spec, dict) else spec
            seed = spec.get("seed", a.seed) if isinstance(spec, dict) else a.seed
            fname = spec.get("file", f"{key}.png") if isinstance(spec, dict) else f"{key}.png"
            r = spec.get("ratio") if isinstance(spec, dict) else None
            w, h = (ratio_table[r] if r else (width, height))
            lo = spec.get("loras") if isinstance(spec, dict) else None
            print(f"[turbo] === {key} ===")
            generate(p, Path(a.outdir) / fname, a.template, seed, w, h,
                     loras=[tuple(x) for x in lo] if lo else loras,
                     negative=a.negative, steps=a.steps, cfg=a.cfg,
                     sampler=a.sampler, scheduler=a.scheduler, ckpt=a.ckpt)
    else:
        generate(a.prompt, a.out or "turbo.png", a.template, a.seed, width, height,
                 loras=loras, negative=a.negative, steps=a.steps, cfg=a.cfg,
                 sampler=a.sampler, scheduler=a.scheduler, ckpt=a.ckpt)


if __name__ == "__main__":
    main()