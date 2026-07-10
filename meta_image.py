"""Meta AI FREE image generation via the browser (CDP 19343) — reliable capture.

Meta's reverse-engineered HTTP API is schema-stale, but the meta.ai/create UI generates images
beautifully for free. This drives that UI and captures the RESULT correctly:
  - generated images live on the AI CDN path `t39.105495` with a descriptive alt (gallery/UI
    assets are rsrc.php / different paths), so we wait for a NEW t39 image after submit;
  - download happens IN-PAGE via fetch->dataURL (no cookie/auth dance).

generate_image(prompt, out_path, timeout) -> out_path or None. ClipPro uses this as the FREE
primary for B-roll stills; right.codes gpt-image-2 / nano-banana is the paid fallback.
"""
import sys, os, time, json, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta_video as MV

AI_CDN = "t39.105495"   # Meta AI generated-image CDN marker


def _t39_imgs(g):
    js = ("JSON.stringify([...document.querySelectorAll('img')]"
          ".map(i=>i.currentSrc||i.src).filter(u=>u&&u.includes('" + AI_CDN + "')))")
    v = g._eval(js)
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = []
    return list(v or [])


def _fetch_b64(g, url, timeout=90):
    """Fetch the image bytes inside the page (same origin/cookies) and return base64."""
    uj = json.dumps(url)
    js = ("(async()=>{try{const r=await fetch(" + uj + ");const b=await r.blob();"
          "return await new Promise(res=>{const fr=new FileReader();"
          "fr.onload=()=>res(fr.result);fr.readAsDataURL(b);});}catch(e){return 'ERR:'+e;}})()")
    out = g._abw("eval", js, timeout=timeout).strip()
    try:
        out = json.loads(out)
    except Exception:
        pass
    if isinstance(out, str) and out.startswith("data:"):
        return base64.b64decode(out.split(",", 1)[1])
    return None


def generate_image(prompt, out_path, timeout=180, g=None):
    g = g or MV.MetaVibes()
    g.ensure_composer()
    before = set(_t39_imgs(g))
    g.submit("Imagine " + prompt if not prompt.lower().startswith("imagine") else prompt)
    fresh = None
    waited = 0
    while waited < timeout:
        time.sleep(5); waited += 5
        try:
            cur = _t39_imgs(g)
        except Exception:
            continue   # transient eval/browser hiccup — keep waiting, don't abort the run
        new = [u for u in cur if u not in before]
        if new:
            # newest is first in DOM order; give it 1 more cycle to finish loading hi-res
            time.sleep(4)
            try:
                new = [u for u in _t39_imgs(g) if u not in before] or new
            except Exception:
                pass   # re-poll failed; fall back to the list we already have
            fresh = new[0]
            break
    if not fresh:
        return None
    data = _fetch_b64(g, fresh)
    if not data or len(data) < 20000:
        return None
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--out", default=r"C:\Users\User\Documents\code\meta-ai-api\image_test\meta_out.jpg")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    r = generate_image(a.prompt, a.out, a.timeout)
    print("RESULT:", r, (os.path.getsize(r) if r and os.path.exists(r) else 0), "bytes")
