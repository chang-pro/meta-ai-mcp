"""Meta AI MCP server — free image generation and AI prompting via browser.

Exposes three tools:
  generate_image   — free image generation via meta.ai/create (the main feature)
  ask_meta         — free prompting / chat with Meta AI (Llama) — no API key needed
  generate_video   — DEPRECATED: Meta AI Vibes (meta.ai/vibes) was shut down
  meta_browser_status — check if the CDP browser is alive

All tools drive the persistent logged-in Chrome on CDP port 19343. Cookie-based
auth lives in the Chrome profile — log in once, use indefinitely.

Register in ~/.claude.json under mcpServers (adjust paths to your install):
  "meta-ai": {
    "type": "stdio",
    "command": "/path/to/meta-ai-api/venv/Scripts/python.exe",
    "args": ["/path/to/meta-ai-api/mcp_server.py"]
  }
"""
import os
from mcp.server.fastmcp import FastMCP
from meta_video import MetaVibes, MetaError
import launch_meta_browser

mcp = FastMCP("meta-ai")


def _ensure_browser():
    launch_meta_browser.launch()
    if not launch_meta_browser.cdp_alive():
        return {"success": False,
                "error": "Meta AI Chrome (CDP 19343) not running and could not start. "
                         "Run launch_meta_browser.py and log into meta.ai first."}
    return None


@mcp.tool()
def generate_image(prompt: str, out_path: str = "", timeout: int = 180) -> dict:
    """Generate a FREE image with Meta AI and download it to disk.

    Drives the logged-in meta.ai browser — no API key, no credits, no subscription.
    Works by navigating to the meta.ai/create page, submitting the prompt, waiting
    for the image to appear on Meta's AI image CDN, and downloading it in-page.

    Args:
        prompt: What the image should show. Keep it descriptive.
                "Imagine " is prepended automatically if not already present.
        out_path: Where to save the image. Defaults to ~/Documents/meta_images/<slug>.jpg
        timeout: Max seconds to wait for the image (default 180).

    Returns dict with success, out_path, bytes.
    """
    try:
        if not (prompt or "").strip():
            return {"success": False, "error": "prompt cannot be empty"}
        err = _ensure_browser()
        if err:
            return err
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
def ask_meta(prompt: str, timeout: int = 120) -> dict:
    """Ask Meta AI (free Llama-based chat) a question and get the full response.

    Uses the logged-in meta.ai browser — no API key, no token limits, no cost.
    Great for: free AI inference, research questions, writing help, coding help.

    Note: this shares the same Chrome session as generate_image. If an image
    generation is in progress, wait for it to finish before calling ask_meta.

    Args:
        prompt: Your question or message to Meta AI.
        timeout: Max seconds to wait for the full response (default 120).

    Returns dict with success, response (the AI's reply text), chars (response length).
    """
    try:
        if not (prompt or "").strip():
            return {"success": False, "error": "prompt cannot be empty"}
        err = _ensure_browser()
        if err:
            return err
        from meta_chat import MetaChat
        g = MetaVibes()
        chat = MetaChat(g)
        response = chat.ask(prompt, timeout=timeout)
        return {"success": True, "response": response, "chars": len(response)}
    except MetaError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def meta_browser_status() -> dict:
    """Check whether the Meta AI Chrome (CDP 19343) is running and reachable."""
    alive = launch_meta_browser.cdp_alive()
    return {"cdp_alive": alive, "port": 19343,
            "hint": "" if alive else "Run launch_meta_browser.py; log into meta.ai first."}


@mcp.tool()
def generate_video(prompt: str, image_path: str = "", out_path: str = "",
                   timeout: int = 300, chat_retries: int = 1,
                   rotate_accounts: bool = True) -> dict:
    """[DEPRECATED] Meta AI Vibes video generation — meta.ai/vibes was shut down.

    This tool is kept for reference but will likely fail. Meta discontinued the
    Vibes video generation feature. Use generate_image for free image generation instead.

    Args:
        prompt: What the video should show.
        image_path: Optional path to an image to animate (image→video).
        out_path: Where to save the mp4.
        timeout: Max seconds to wait (default 300).
        chat_retries: Extra fresh-chat attempts on stall (default 1).
        rotate_accounts: Rotate to next cookie account on repeated stalls (default True).

    Returns dict with success, out_path, video_url, bytes.
    """
    try:
        err = _ensure_browser()
        if err:
            return err
        gen = MetaVibes()
        return gen.generate_video(
            prompt,
            image_path=image_path or None,
            out_path=out_path or None,
            timeout=timeout,
            chat_retries=chat_retries,
            rotate_accounts=rotate_accounts)
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    mcp.run()
