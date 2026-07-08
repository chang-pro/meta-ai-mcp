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
                   timeout: int = 300) -> dict:
    """Generate a video with Meta AI (free) and download the mp4.

    Args:
        prompt: What the video should show / how to animate. For image->video,
                describe the motion and say to keep characters consistent.
        image_path: Optional. Absolute path to an image to animate (image->video).
                    Leave empty for text->video.
        out_path: Optional. Where to save the mp4. Defaults to the
                  META_OUT_DIR env var, or ~/Documents/meta_clips/.
        timeout: Max seconds to wait for the render (default 300).

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
            timeout=timeout)
    except Exception as e:
        # never let a raw exception escape the MCP tool -- return a clean result
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def meta_browser_status() -> dict:
    """Check whether the Meta AI Vibes Chrome (CDP 19343) is running & reachable."""
    alive = launch_meta_browser.cdp_alive()
    return {"cdp_alive": alive, "port": 19343,
            "hint": "" if alive else "Run launch_meta_browser.py; ensure meta.ai logged in."}


if __name__ == "__main__":
    mcp.run()
