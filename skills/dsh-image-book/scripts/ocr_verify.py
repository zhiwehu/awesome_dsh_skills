#!/usr/bin/env python3
"""OCR-verify English text rendered in generated manga pages (macOS Vision)."""
import json, subprocess, sys, os, re

JXA = '''
ObjC.import('Vision'); ObjC.import('Foundation');
constpath = Application.currentPath();
function run(argv) {
  const imgPath = argv[0];
  const request = $.VNRecognizeTextRequest.alloc.init;
  request.recognitionLanguages = ["en-US"];
  request.recognitionLevel = 1; // accurate
  const handler = $.VNImageRequestHandler.alloc.initWithURLOptions($(imgPath).stringByAddingPercentEncodingWithAllowedCharacters($.NSCharacterSet.URLPathAllowedCharacterSet), $.nil);
  // Note: file URL needed
  const fileURL = $.NSURL.fileURLWithPath(imgPath);
  const handler2 = $.VNImageRequestHandler.alloc.initWithURLOptions(fileURL, $.nil);
  const ok = handler2.performRequestsError([request], $());
  const results = request.results;
  const out = [];
  const count = results.count;
  for (let i = 0; i < count; i++) {
    const obs = results.objectAtIndex(i);
    out.push(obs.topCandidatesCount ? obs.topCandidates(1).objectAtIndex(0).string.js : "");
  }
  return JSON.stringify(out);
}
'''

SWIFT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_vision.swift")
SWIFT_CACHE = "/tmp/swift-module-cache"

def ocr(img_path):
    r = subprocess.run(
        ["swift", "-Xcc", "-fmodules-cache-path=" + SWIFT_CACHE, SWIFT_SRC,
         os.path.abspath(img_path)],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[:400])
    return [l for l in r.stdout.splitlines() if l.strip()]

def norm(s):
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def loose_contains(haystack, needle, max_per_word=2):
    """True if every word in needle appears in haystack allowing `max_per_word`
    Levenshtein edits (catches OCR m/n, l/i, o/0 confusion and word merges)."""
    tokens = [t for t in re.split(r'[^A-Za-z0-9]+', haystack.upper()) if t]
    for w in norm(needle).split():
        if not any(ed(w, h2) <= max_per_word for h2 in tokens):
            return False
    return True

def ed(a, b):
    """Levenshtein distance, tolerates word merges/splits (OCR drops spaces)."""
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]

def verify(img_path, expected_phrases, max_edits_per_word=2):
    """Each expected phrase must match OCR with small per-word tolerance."""
    lines = ocr(img_path)
    blob = " | ".join(lines)
    report = []
    for phrase in expected_phrases:
        ok = loose_contains(blob, phrase, max_edits_per_word)
        report.append((ok, phrase))
    return lines, report

if __name__ == "__main__":
    img = sys.argv[1]
    phrases = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else []
    lines, report = verify(img, phrases)
    print("=== OCR LINES (%s) ===" % img)
    for l in lines:
        if l.strip():
            print("  ", l)
    if phrases:
        print("=== EXPECTED TEXT CHECK ===")
        for ok, p in report:
            print("  %s  %s" % ("PASS" if ok else "FAIL", p))
        fails = sum(1 for ok, _ in report if not ok)
        sys.exit(1 if fails else 0)
