"""Meta AI Vibes video-generation MCP server (browser engine).

Exposes a `generate_video` tool that drives the persistent logged-in Chrome
(CDP 19343) to make a Meta AI video and download the mp4. Cookie-based auth
lives in the Chrome profile -- same "cookie once" UX as the Perplexity MCP,
but robust to Meta's schema changes.

Register in .claude.json (adjust paths to your install location):
  "meta-video": {
    "type": "stdio",
    "command": "/path/to/meta-ai-api/venv/Scripts/python.exe",
    "args": ["/path/to/meta-ai-api/mcp_server.py"]
  }
"""
import os
from mcp.server.fastmcp import FastMCP
from meta_video import MetaVibes, MetaError
import launch_meta_browser

mcp = FastMCP("meta-video")


@mcp.tool()
def generate_video(prompt: str, image_path: str = "", out_path: str = "",
                   timeout: int = 300, chat_retries: int = 1, rotate_accounts: bool = True) -> dict:
    """Generate a video with Meta AI (free) and download the mp4.

    Reuses ONE chat; if a generation stalls it opens a NEW chat and retries, and if the whole
    account keeps stalling it ROTATES to the next account (cookie files under accounts/, cycling back).

    Args:
        prompt: What the video should show / how to animate. For image->video,
                describe the motion and say to keep characters consistent.
        image_path: Optional. Absolute path to an image to animate (image->video).
                    Leave empty for text->video.
        out_path: Optional. Where to save the mp4. Defaults to the
                  META_OUT_DIR env var, or ~/Documents/meta_clips/.
        timeout: Max seconds to wait for the render (default 300).
        chat_retries: extra fresh-chat attempts per account after a stall (default 1).
        rotate_accounts: rotate to the next cookie account when chats keep stalling (default True).

    Returns dict with success, out_path, video_url, bytes.
    """
    try:
        launch_meta_browser.launch()
        if not launch_meta_browser.cdp_alive():
            return {"success": False,
                    "error": "Meta AI Chrome (CDP 19343) not running and could not start. "
                             "Run launch_meta_browser.py and ensure meta.ai is logged in."}
        gen = MetaVibes()
        return gen.generate_video(
            prompt,
            image_path=image_path or None,
            out_path=out_path or None,
            timeout=timeout,
            chat_retries=chat_retries,
            rotate_accounts=rotate_accounts)
    except Exception as e:
        # never let a raw exception escape the MCP tool -- return a clean result
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def generate_image(prompt: str, out_path: str = "", timeout: int = 180) -> dict:
    """Generate an IMAGE with Meta AI (free) via the meta.ai/create browser and download it.

    Meta's reverse-engineered HTTP image API is schema-stale; this drives the logged-in
    meta.ai/create UI (the same browser video uses) and captures the generated result from
    Meta's AI image CDN, downloading it IN-PAGE (no cookie/auth dance).

    Args:
        prompt: What the image should show. "Imagine " is prepended automatically if absent.
        out_path: Where to save the image. Defaults to META_IMG_DIR env var, else
                  ~/Documents/meta_images/<slug>.jpg.
        timeout: Max seconds to wait for the image (default 180).

    Returns dict with success, out_path, bytes.
    """
    try:
        if not (prompt or "").strip():
            return {"success": False, "error": "empty prompt"}
        launch_meta_browser.launch()
        if not launch_meta_browser.cdp_alive():
            return {"success": False,
                    "error": "Meta AI Chrome (CDP 19343) not running and could not start. "
                             "Run launch_meta_browser.py and ensure meta.ai is logged in."}
        import meta_image
        if not out_path:
            base = os.environ.get("META_IMG_DIR") or os.path.join(
                os.path.expanduser("~"), "Documents", "meta_images")
            slug = "".join(c if c.isalnum() else "_" for c in prompt.lower())[:40].strip("_") or "meta_img"
            out_path = os.path.join(base, slug + ".jpg")
        res = meta_image.generate_image(prompt, out_path, timeout=timeout)
        if res and os.path.exists(res):
            return {"success": True, "out_path": res, "bytes": os.path.getsize(res)}
        return {"success": False, "error": "no image captured (generation stalled or timed out)",
                "out_path": None}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def meta_browser_status() -> dict:
    """Check whether the Meta AI Vibes Chrome (CDP 19343) is running & reachable."""
    alive = launch_meta_browser.cdp_alive()
    return {"cdp_alive": alive, "port": 19343,
            "hint": "" if alive else "Run launch_meta_browser.py; ensure meta.ai logged in."}


if __name__ == "__main__":
    mcp.run()
