"""Meta AI Vibes video generator via CDP browser automation (agent-browser engine).

Drives the persistent logged-in Chrome on CDP 19343 (profile Chrome-MetaAI-Vibes)
through agent-browser to generate videos and download the mp4. Robust engine:
real logged-in session, survives Meta schema changes. See browser-registry.md 19343.

Why agent-browser (not raw CDP): Meta's composer is a React controlled input;
only a value-tracker-aware fill (what agent-browser/Playwright does) enables the
Send button. Raw CDP Runtime.evaluate leaves it disabled.

API:
  gen = MetaVibes()
  res = gen.generate_video(prompt, image_path=None, out_path=None, timeout=300)
"""
import json
import os
import time
import subprocess
import urllib.request

SESSION = os.environ.get("META_ABW_SESSION", "metaai-vibes")
CDP_PORT = int(os.environ.get("META_CDP_PORT", "19343"))
DEFAULT_OUT_DIR = os.environ.get(
    "META_OUT_DIR",
    os.path.join(os.path.expanduser("~"), "Documents", "meta_clips"))
ABW_JS = os.environ.get(
    "META_ABW_JS",
    os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules",
                 "agent-browser", "bin", "agent-browser.js"))


class MetaError(Exception):
    pass


def _probe_dur(f):
    try:
        o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                           capture_output=True, text=True).stdout.strip()
        return float(o or 0)
    except Exception:
        return 0.0


# Style presets — appended to the prompt to restyle the generation. Add freely.
STYLES = {
    "cinematic":  "Cinematic film look, shallow depth of field, warm color grade, subtle camera movement, 35mm.",
    "anime":      "Anime cel-shaded style, expressive linework, vibrant colors, Studio-Ghibli-like.",
    "claymation": "Claymation stop-motion look, tactile clay texture, handcrafted, playful.",
    "pixar":      "3D animated movie style, Pixar-like, soft global illumination, glossy, expressive.",
    "comic":      "Bold comic-book style, inked outlines, halftone shading, dynamic angles.",
    "realistic":  "Photorealistic, natural lighting, documentary realism, lifelike motion.",
    "flat2d":     "Flat 2D cartoon style, clean bold outlines, bright flat colors (ClipPro house look).",
}


class MetaVibes:
    def __init__(self, session=SESSION, port=CDP_PORT):
        self.session = session
        self.port = port
        # ensure agent-browser is attached to the running logged-in Chrome
        self._abw("connect", str(port))

    # ---- agent-browser plumbing ----
    def _abw(self, *args, timeout=60):
        cmd = ["node", ABW_JS, "--session", self.session, *args]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise MetaError(f"agent-browser {args[0]} timed out after {timeout}s")
        except FileNotFoundError:
            raise MetaError("node not found on PATH (needed to run agent-browser)")
        if p.returncode != 0:
            raise MetaError(f"agent-browser {args[0]} failed: {p.stderr.strip()[:300]}")
        return p.stdout

    def _eval(self, js, timeout=60):
        """Run JS in the page; return the parsed JSON value (agent-browser prints it quoted)."""
        out = self._abw("eval", js, timeout=timeout).strip()
        # agent-browser prints the return value as a JSON string literal
        try:
            val = json.loads(out)
        except json.JSONDecodeError:
            val = out
        return val

    # ---- page helpers ----
    def ensure_composer(self):
        # SPA-navigate to Create (click nav, no full reload) if composer missing
        has = self._eval("!!document.querySelector('textarea')")
        if has in (True, "true"):
            return
        self._abw("open", "https://www.meta.ai/create")
        for _ in range(20):
            if self._eval("!!document.querySelector('textarea')") in (True, "true"):
                return
            time.sleep(1)
        raise MetaError("composer textarea never appeared")

    def video_srcs(self):
        """Ordered list of video srcs in DOM order (topmost/newest first).

        Collects both the <video> currentSrc/src AND any nested <source> element src, so we can reach the raw
        CDN asset even when the player's own src is a blob:/MediaSource URL (which urllib cannot fetch)."""
        js = ("JSON.stringify([...document.querySelectorAll('video')].flatMap(v=>["
              "v.currentSrc,v.src,...[...v.querySelectorAll('source')].map(s=>s.src)]).filter(Boolean))")
        val = self._eval(js)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                val = []
        return list(val or [])

    def upload_image(self, image_path):
        if not os.path.exists(image_path):
            raise MetaError(f"image not found: {image_path}")
        # reveal a file input if needed
        if self._eval("!!document.querySelector('input[type=file]')") not in (True, "true"):
            self._eval("""(() => { const b=[...document.querySelectorAll('button,[role=button]')]
                .find(x=>{const l=(x.getAttribute('aria-label')||'').toLowerCase();
                  return l.includes('add')||l.includes('attach')||l.includes('photo')||l.includes('image')||l.includes('file');});
                if(b) b.click(); return !!b; })()""")
            time.sleep(1)
        # set the file on the input via agent-browser upload
        self._abw("upload", "input[type=file]", image_path, timeout=60)
        time.sleep(3)  # preview attach

    def submit(self, prompt):
        pj = json.dumps(prompt)
        typed = self._eval(f"""(() => {{
            const ta=document.querySelector('textarea'); if(!ta) return 'no-textarea';
            ta.focus();
            const set=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
            set.call(ta, {pj});
            ta.dispatchEvent(new Event('input',{{bubbles:true}}));
            ta.dispatchEvent(new Event('change',{{bubbles:true}}));
            const b=[...document.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')==='Send');
            return 'len='+ta.value.length+' send='+(b?String(b.disabled):'none');
        }})()""")
        if "no-textarea" in str(typed):
            raise MetaError("composer textarea missing at submit")
        time.sleep(0.8)
        clicked = self._eval("""(() => {
            const b=[...document.querySelectorAll('button,[role=button]')]
              .find(x=>x.getAttribute('aria-label')==='Send');
            if(!b) return 'no-send'; b.disabled=false; b.click(); return 'clicked'; })()""")
        if "clicked" not in str(clicked):
            raise MetaError(f"Send failed ({clicked}); type result was {typed}")

    def wait_new_video(self, before, timeout=300, poll=4):
        """Return the src of the clip this run generated.

        `before` is the ordered list of video srcs captured pre-submit. A just-
        submitted generation renders into the TOPMOST creation card, so among
        newly-appeared fbcdn srcs we take the one earliest in DOM order (rather
        than any new src, which could be a lazy-loaded OLD clip further down).
        Requires the pick to be stable across two polls before returning.
        """
        before_set = set(before)
        end = time.time() + timeout
        last_pick = None
        while time.time() < end:
            ordered = self.video_srcs()  # topmost first
            fresh = [s for s in ordered if s not in before_set and "fbcdn" in s]
            if fresh:
                # the real generated clip is the topmost new one (first in DOM order)
                pick = fresh[0]
                if pick == last_pick:      # stable across two polls -> trust it
                    return pick
                last_pick = pick
            else:
                last_pick = None
            time.sleep(poll)
        if last_pick:                       # timed out but had a candidate
            return last_pick
        raise MetaError(f"no new video within {timeout}s")

    def download(self, url, out_path, timeout=180):
        # Pull the ORIGINAL asset straight off Meta's CDN (fbcdn) — NOT Meta's in-app "save/download" button, which
        # re-encodes and stamps the visible "Meta AI" logo. The raw CDN mp4 is the clean file the no-watermark
        # downloaders target. A blob:/MediaSource URL is the in-player stream and is NOT fetchable via urllib —
        # reject it loudly so we never ship a 0-byte/placeholder clip or silently fall back to a watermarked path.
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            raise MetaError(f"not a downloadable CDN url (got {str(url)[:40]!r}); need an https fbcdn source, "
                            "not a blob:/MediaSource stream")
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Referer": "https://www.meta.ai/"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r, open(out_path, "wb") as f:
                f.write(r.read())
        except Exception as e:
            raise MetaError(f"download failed: {type(e).__name__}: {e}")
        if os.path.getsize(out_path) < 1000:
            raise MetaError("downloaded file is suspiciously small (<1KB)")
        return out_path

    # ---- public ----
    def generate_video(self, prompt, image_path=None, out_path=None, timeout=300):
        if out_path is None:
            safe = "".join(c for c in prompt[:40] if c.isalnum() or c in " -_").strip().replace(" ", "-")
            out_path = os.path.join(DEFAULT_OUT_DIR, f"{safe or 'clip'}.mp4")
        self.ensure_composer()
        before = self.video_srcs()
        if image_path:
            self.upload_image(image_path)
        self.submit(prompt)
        url = self.wait_new_video(before, timeout=timeout)
        self.download(url, out_path, timeout=max(180, timeout))
        size = os.path.getsize(out_path)
        return {"success": True, "out_path": out_path, "video_url": url,
                "bytes": size, "prompt": prompt}

    # ---- multi-segment chaining (5s back-to-back -> continuous longer motion) + styles ----
    def _last_frame(self, video_path, out_png):
        """Grab the final frame of a clip — the seed image for the next chained segment (continuous motion)."""
        subprocess.run(["ffmpeg", "-y", "-sseof", "-0.2", "-i", video_path, "-frames:v", "1", out_png],
                       capture_output=True, text=True)
        if not (os.path.exists(out_png) and os.path.getsize(out_png) > 500):
            raise MetaError("could not extract last frame for chaining")
        return out_png

    def generate_chained(self, prompt, image_path=None, target_seconds=10, style=None,
                         out_path=None, timeout=300, max_segments=6):
        """Beat Meta's ~5.2s cap: generate segments BACK-TO-BACK, each seeded from the previous clip's LAST FRAME,
        then concat -> one continuous longer clip at Meta's clean quality (no time-stretch). `style` applies a preset
        from STYLES (or a raw style string). Returns {success, out_path, segments, seconds, style}."""
        if out_path is None:
            safe = "".join(c for c in prompt[:40] if c.isalnum() or c in " -_").strip().replace(" ", "-")
            out_path = os.path.join(DEFAULT_OUT_DIR, f"{safe or 'clip'}_chain.mp4")
        style_txt = STYLES.get(style, style) if style else ""
        base = (prompt + (". " + style_txt if style_txt else "")).strip()
        work = os.path.join(os.path.dirname(out_path) or DEFAULT_OUT_DIR, "_chain_work")
        os.makedirs(work, exist_ok=True)
        segs = []; cur_img = image_path; total = 0.0
        for i in range(max_segments):
            segp = os.path.join(work, f"seg{i:02d}.mp4")
            p = base if i == 0 else ("Continue the exact same shot smoothly — same characters, faces, clothing and "
                                     "setting, NO cut, a natural continuation of the motion. " + base)
            res = self.generate_video(p, image_path=cur_img, out_path=segp, timeout=timeout)
            if not res.get("success"):
                break
            segs.append(segp); total += _probe_dur(segp)
            if total >= target_seconds:
                break
            cur_img = self._last_frame(segp, os.path.join(work, f"last{i:02d}.png"))
        if not segs:
            return {"success": False, "error": "no segments generated"}
        listf = os.path.join(work, "concat.txt")
        with open(listf, "w", encoding="utf-8") as f:
            for s in segs:
                f.write(f"file '{s.replace(os.sep, '/')}'\n")
        r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out_path],
                           capture_output=True, text=True)
        if r.returncode != 0 or not (os.path.exists(out_path) and os.path.getsize(out_path) > 1000):
            return {"success": False, "error": "concat failed: " + (r.stderr or "")[-200:]}
        return {"success": True, "out_path": out_path, "segments": len(segs),
                "seconds": round(total, 2), "style": style, "prompt": base}


if __name__ == "__main__":
    import sys
    import launch_meta_browser
    prompt = sys.argv[1] if len(sys.argv) > 1 else "A yellow kite in a blue sky, gentle wind, cinematic short clip"
    image = sys.argv[2] if len(sys.argv) > 2 else None
    result = launch_meta_browser.launch()
    if not launch_meta_browser.cdp_alive():
        print(f"ERROR: could not start Meta AI Chrome (CDP {CDP_PORT}). Run launch_meta_browser.py and log into meta.ai first.")
        sys.exit(1)
    g = MetaVibes()
    print("Generating (this takes ~30-90s)...", flush=True)
    print(json.dumps(g.generate_video(prompt, image_path=image), indent=2))
