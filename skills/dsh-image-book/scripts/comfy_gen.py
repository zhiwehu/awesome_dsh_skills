#!/usr/bin/env python3
"""ComfyUI (Qwen-Image-2.1) generation driver for the dsh-image-book skill.

Two consistency modes, auto-selected per page:
   * text-to-image (default):        qwen21-3x4.json, TextEncodeQwenImage21
   * reference-consistent (recommended for multi-page books):
        qwen21-edit-3x4.json         -> 1 reference image (TextEncodeQwenImageEdit)
        qwen21-editplus-3x4.json     -> 2-3 reference images (TextEncodeQwenImageEditPlus)
      The Edit nodes fold a character-sheet reference into conditioning through the
      multimodal qwen3vl_8b CLIP, preserving the character's identity far more
      reliably than a verbatim text block. See SKILL.md ("Character consistency").

Per page, optional fields in the prompts JSON:
   "seed":  123                          fixed seed (default SEED)
   "ref":   "elias-sheet.png"            1 reference -> Edit template
   "refs":  ["elias.png", "fisher.png"]  2-3 refs    -> EditPlus (3rd repeats #2)
   "template": "qwen21-3x4.json"         override the auto pick for this page
References are located next to the prompts file (or absolutely), uploaded to
ComfyUI via /upload/image, and fed to a LoadImage node by filename.

Usage:
  python3 comfy_gen.py --list  --prompts book.json      # list pages + mode
  python3 comfy_gen.py          --prompts book.json --all   # all pages
  python3 comfy_gen.py --force --prompts book.json p4      # regenerate a page

The driver parses ALL arguments before touching the prompts file (a former bug
loaded a stale default prompts file and crashed even when --prompts was given).
"""
import json, os, sys, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS = os.path.abspath(os.path.join(HERE, "..", "workflows"))
SERVER = os.environ.get("COMFYUI_SERVER", "http://127.0.0.1:8188")
SEED = 20260922

# Templates live in workflows/ now; the older "scripts/qwen21-3x4.json" was the
# stale default that caused a FileNotFoundError. Reference-consistent templates:
TEMPLATE         = os.path.join(WORKFLOWS, "qwen21-3x4.json")          # text-to-image
TEMPLATE_EDIT    = os.path.join(WORKFLOWS, "qwen21-edit-3x4.json")     # 1 reference
TEMPLATE_EDITPLUS= os.path.join(WORKFLOWS, "qwen21-editplus-3x4.json")  # 2-3 references
# Optional writable mirror of the ComfyUI input dir: if set and has the file, skip
# upload. Default empty => always upload via /upload/image (sandbox-safe).
COMFY_INPUT = os.environ.get("COMFY_INPUT", "")
_UPLOAD_CACHE = {}   # source path -> server-assigned filename (skip re-upload)


def http_json(url, data=None, method=None, timeout=60):
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    if data is not None:
        req.data = json.dumps(data).encode()
    if method:
        req.get_method = lambda: method
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _upload_image(path):
    """POST a file to ComfyUI /upload/image (multipart, overwrite=true) and return
    its server-side filename. HTTP upload keeps this sandbox-safe: it writes to
    ComfyUI's own input dir on the server, never a path outside the workspace."""
    boundary = "----dshImageBookBoundary1234"
    cname = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    disp = ('Content-Disposition: form-data; name="image"; filename="%s"'
            "\r\nContent-Transfer-Encoding: binary\r\n" % cname).encode()
    body = b"".join([
        ("--" + boundary + "\r\n").encode(),
        disp,
        b"Content-Type: image/png\r\n\r\n",
        data,
        ("\r\n--" + boundary + "--\r\n").encode(),
    ])
    req = urllib.request.Request(SERVER + "/upload/image?overwrite=true",
                                data=body,
                                headers={"Content-Type":
                                         "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    return out["name"]


def _subst(o, mapping):
    """Recursively replace string placeholders {{...}} in the workflow object."""
    if isinstance(o, str):
        for k, v in mapping.items():
            o = o.replace(k, str(v))
        return o
    if isinstance(o, dict):
        return {k: _subst(v, mapping) for k, v in o.items()}
    if isinstance(o, list):
        return [_subst(v, mapping) for v in o]
    return o


def _resolve_ref(name, prompt_dir):
    """Locate a reference image and hand it to the server, returning the
    LoadImage filename. Looked up relative to the prompts dir, an optional
    COMFY_INPUT mirror, or absolutely; uploaded via /upload/image to ComfyUI."""
    candidates = [name] if os.path.isabs(name) else [
        os.path.join(prompt_dir, name),
        (os.path.join(COMFY_INPUT, name) if COMFY_INPUT else name),
        name]
    src = next((c for c in candidates if os.path.exists(c)), None)
    if src is None:
        raise FileNotFoundError("reference image not found: %s "
                                "(looked in %s%s)"
                                % (name, prompt_dir,
                                   ("/" + COMFY_INPUT if COMFY_INPUT else "")))
    if src in _UPLOAD_CACHE:
        return _UPLOAD_CACHE[src]
    srv = _upload_image(src)
    _UPLOAD_CACHE[src] = srv
    print("[ref] %s -> %s (uploaded via /upload/image)" %
          (os.path.basename(name), srv), flush=True)
    return srv


def generate(prompt_text, out_path, template=None, seed=SEED, ref=None, refs=None,
             prompt_dir=None, poll_interval=5, max_wait=1500):
    # Build the reference list: 0 -> t2i, 1 -> Edit, 2-3 -> EditPlus.
    rlist = list(refs) if refs else ([ref] if ref else [])
    if template is None:
        if len(rlist) == 0:
            template = TEMPLATE
        elif len(rlist) == 1:
            template = TEMPLATE_EDIT
        else:
            template = TEMPLATE_EDITPLUS

    wf = json.load(open(template))
    if "{{prompt}}" not in json.dumps(wf):
        raise ValueError("template %s is missing the {{prompt}} placeholder" % template)

    prompt_dir = prompt_dir or os.path.dirname(os.path.abspath(template))
    mapping = {"{{prompt}}": prompt_text, "{{seed}}": str(seed)}
    if len(rlist) >= 1:
        mapping["{{ref}}"]  = _resolve_ref(rlist[0], prompt_dir)
    if len(rlist) >= 2:
        mapping["{{ref2}}"] = _resolve_ref(rlist[1], prompt_dir)
         # EditPlus has 3 image slots; repeat the 2nd reference into the 3rd when
        # only two are given so the workflow still has a valid image on every slot.
        mapping["{{ref3}}"] = _resolve_ref(rlist[2] if len(rlist) >= 3
                                           else rlist[1], prompt_dir)
    wf = _subst(wf, mapping)

    leftover = [k for k in ("{{prompt}}", "{{seed}}", "{{ref}}", "{{ref2}}", "{{ref3}}")
                if k in json.dumps(wf)]
    if leftover:
        raise ValueError("unsubstituted placeholders remain: %s in %s "
                         "(add the matching ref/refs fields per page)"
                         % (leftover, os.path.basename(template)))

    res = http_json(SERVER + "/prompt", {"prompt": wf, "client_id": "dsh-image-book"})
    pid = res["prompt_id"]
    print("[gen] %s submitted %s -> %s"
          % (os.path.basename(template), pid, os.path.basename(out_path)), flush=True)
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(poll_interval)
        hist = http_json(SERVER + "/history/" + pid)
        if pid not in hist:
            continue
        entry = hist[pid]
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError("generation error: " + json.dumps(status)[:600])
        outputs = entry.get("outputs", {})
        for node_id, node_out in outputs.items():
            for img in node_out.get("images", []):
                if img.get("type") == "output":
                    q = urllib.parse.urlencode({"filename": img["filename"],
                                               "subfolder": img.get("subfolder", ""),
                                               "type": "output"})
                    with urllib.request.urlopen(SERVER + "/view?" + q, timeout=120) as r:
                        data = r.read()
                    with open(out_path, "wb") as f:
                        f.write(data)
                    print("[gen] saved %s (%d KB, %.0fs)"
                          % (out_path, len(data) // 1024, time.time() - t0), flush=True)
                    return out_path
    raise TimeoutError("timed out waiting for " + pid)


def load_pages(path):
    if not os.path.exists(path):
        raise SystemExit("prompts file not found: %s\n   pass --prompts <path.json>\n   "
                         "e.g. python3 comfy_gen.py --list --prompts "
                         "examples/atmospheric.json" % path)
    return json.load(open(path))


def main():
    args = sys.argv[1:]
    # optional flags consumed before positional keys / --all
    template = None        # None => auto-pick (t2i vs edit by ref presence)
    prompts_file = None
    force = False
    keys = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--template":
            template = args[i + 1]; i += 2
        elif a == "--prompts":
            prompts_file = args[i + 1]; i += 2
        elif a == "--force":
            force = True; i += 1
        else:
            keys.append(a); i += 1

    # Parse ALL args first, THEN load the requested prompts file. (A former
    # version loaded a stale default BEFORE parsing args and crashed even when a
    # valid --prompts was passed — the latent bug.)
    if not prompts_file:
        print(__doc__)
        sys.exit(1)
    pages = load_pages(prompts_file)
    prompt_dir = os.path.dirname(os.path.abspath(prompts_file))
    if "--list" in keys or not keys:
        for k, v in pages.items():
            if "refs" in v:
                mode = "edit+%d" % len(v["refs"])
            elif "ref" in v:
                mode = "edit"
            else:
                mode = "t2i"
            print("%-12s seed=%-4s %s   -> %s"
                  % (k, str(v.get("seed", "def")), mode, v["file"]))
        if "--list" in keys:
            return
    # no --list: generate the requested pages
    page_keys = [k for k in keys if k not in ("--list", "--all")]
    if "--all" in keys or not page_keys:
        page_keys = list(pages.keys())
    for k in page_keys:
        p = pages[k]
        out = os.path.join(prompt_dir, p["file"])
        if os.path.exists(out) and not force:
            print("[skip] %s exists (use --force to redo)" % out, flush=True)
            continue
        print("[gen] === %s (seed=%s, ref=%s) ==="
              % (k, p.get("seed", "def"), p.get("ref") or p.get("refs") or "-"),
              flush=True)
        generate(p["prompt"], out, template=(template or p.get("template")),
                 seed=p.get("seed", SEED), ref=p.get("ref"), refs=p.get("refs"),
                 prompt_dir=prompt_dir)


if __name__ == "__main__":
    main()
