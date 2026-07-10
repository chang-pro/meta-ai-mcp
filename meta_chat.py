"""Meta AI free chat/prompting via the browser (CDP 19343).

Drives the logged-in meta.ai chat interface to submit a prompt and capture
the AI response. No API key, no credits — uses the real browser session.

Uses the same MetaVibes CDP + agent-browser stack as meta_image.py and meta_video.py.
"""
import json
import os
import time
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

META_CHAT_URL = "https://www.meta.ai/"

# Selectors for the meta.ai chat composer (as of 2026). textarea FIRST: meta.ai's
# real composer is a 0x0 auto-grow <textarea> (offsetParent null, rect 0x0) that
# React reads — a visibility filter would reject the only working input on the page.
_INPUT_SELECTORS = [
    "textarea",
    "div[contenteditable='true']",
    "div[contenteditable]",
    "[role=textbox]",
]
_SEND_ARIA = ["Send message", "Send"]


def _find_input_js():
    """JS that returns the first selector with a present, enabled composer input, or null.

    Deliberately NO visibility check — see _INPUT_SELECTORS note."""
    sel_json = json.dumps(_INPUT_SELECTORS)
    return f"""(()=>{{
        const sels={sel_json};
        for(const s of sels){{
            const els=[...document.querySelectorAll(s)].filter(e=>!e.disabled);
            if(els.length) return s;
        }}
        return null;
    }})()"""


def _fill_input_js(prompt_json, selector_json):
    """JS that fills the found input element (works for both textarea and contenteditable).

    contenteditable path uses execCommand('insertText') — Meta's composer is a Lexical
    (React) editor; setting textContent directly does NOT update the editor state, but
    insertText goes through the browser editing pipeline Lexical listens to."""
    return f"""(()=>{{
        const sel={selector_json};
        const el=document.querySelector(sel);
        if(!el) return 'no_input';
        el.focus();
        el.scrollIntoView({{block:'center'}});
        if(el.tagName==='TEXTAREA'){{
            const set=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
            set.call(el,{prompt_json});
            el.dispatchEvent(new Event('input',{{bubbles:true}}));
            el.dispatchEvent(new Event('change',{{bubbles:true}}));
        }} else {{
            const range=document.createRange();
            range.selectNodeContents(el);
            const s=window.getSelection();
            s.removeAllRanges();
            s.addRange(range);
            document.execCommand('insertText',false,{prompt_json});
        }}
        return 'filled:'+((el.value||el.textContent||'').length);
    }})()"""


def _click_send_js(send_labels_json):
    """JS that clicks the Send button by aria-label, force-enabling it first.

    No visibility check and disabled is overridden — same proven pattern as
    meta_video.submit (React sometimes leaves the button disabled until its
    own event loop catches up, but a click still submits)."""
    return f"""(()=>{{
        const labels={send_labels_json};
        const btns=[...document.querySelectorAll('button,[role=button]')];
        for(const lbl of labels){{
            const b=btns.find(b=>
                (b.getAttribute('aria-label')||'').toLowerCase()===lbl.toLowerCase());
            if(b){{b.disabled=false;b.click();return 'clicked:'+lbl;}}
        }}
        // fallback: find any send-looking button
        const fallback=btns.find(b=>
            /send|submit/i.test(b.getAttribute('aria-label')||b.title||''));
        if(fallback){{fallback.disabled=false;fallback.click();return 'clicked:fallback';}}
        return 'no_send';
    }})()"""


def _last_response_js():
    """JS that returns JSON {n: message count, t: last AI response text}.

    The count matters: if Meta gives the SAME answer twice in a row (or you re-ask a
    question), the text alone never changes — the count is how we detect the new reply."""
    return """(()=>{
        const pack=(n,t)=>JSON.stringify({n:n,t:(t||'').trim()});
        // .ur-markdown = meta.ai's rendered AI reply container (verified live 2026-07-10;
        // user bubbles do NOT match it). Role-based selectors kept as fallbacks.
        const roles=['.ur-markdown',
                     '[data-message-role="assistant"]','[data-author="assistant"]',
                     '[class*="assistant"],[class*="ai-message"],[class*="bot-message"]'];
        for(const sel of roles){
            const msgs=[...document.querySelectorAll(sel)];
            if(msgs.length){return pack(msgs.length,msgs[msgs.length-1].innerText);}
        }
        // fallback: grab all role-tagged messages
        const allMsgs=[...document.querySelectorAll('[data-message-role],[data-author]')];
        if(!allMsgs.length){
            // last resort: any div that looks like a chat bubble with substantial text
            const divs=[...document.querySelectorAll('div[class*="message"],div[class*="bubble"],div[class*="response"]')]
                .filter(d=>d.innerText&&d.innerText.trim().length>20);
            const last=divs[divs.length-1];
            return pack(divs.length,last?last.innerText:'');
        }
        const lastMsg=allMsgs[allMsgs.length-1];
        return pack(allMsgs.length,lastMsg.innerText||lastMsg.textContent||'');
    })()"""


def _is_streaming_js():
    """Returns true if Meta AI is still generating (typing indicator / loading)."""
    return """(()=>{
        const indicators=[
            '[class*="typing"]','[class*="loading"],[class*="generating"]',
            '[aria-label*="typing"],[aria-label*="loading"]',
            '[data-testid*="typing"],[data-testid*="loading"]',
            'svg[class*="spinner"],div[class*="spinner"]',
        ];
        return indicators.some(sel=>document.querySelector(sel)!==null);
    })()"""


class MetaChat:
    """Drives meta.ai chat for free prompting. Reuses the same CDP session as MetaVibes."""

    def __init__(self, g=None):
        """Pass an existing MetaVibes instance to share the CDP session, or leave None to create one."""
        if g is None:
            import meta_video as MV
            g = MV.MetaVibes()
        self._g = g

    def _ensure_chat(self):
        """Navigate to meta.ai chat if not already there."""
        url = self._g._eval("location.href") or ""
        # vibes page is video-specific; for chat we want the main page
        if "meta.ai" not in url or "/vibes" in url or "/create" in url:
            self._g._abw("open", META_CHAT_URL)
            time.sleep(3)

    def _get_response(self):
        """Return (message_count, last_response_text) from the page."""
        raw = self._g._eval(_last_response_js())
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return 0, raw.strip()
        if isinstance(raw, dict):
            try:
                n = int(raw.get("n") or 0)
            except (TypeError, ValueError):
                n = 0
            return n, str(raw.get("t") or "").strip()
        return 0, ""

    def ask(self, prompt: str, timeout: int = 120) -> str:
        """Submit a prompt to Meta AI chat and return the response text.

        Args:
            prompt: Your question or message.
            timeout: Max seconds to wait for a complete response.

        Returns the AI response as a plain string. Raises MetaError on failure.
        """
        from meta_video import MetaError
        self._ensure_chat()

        # Find the input element
        sel = self._g._eval(_find_input_js())
        if not sel:
            raise MetaError("No composer input found on meta.ai — page may not be loaded correctly")

        # Snapshot message count + text so a NEW reply is detectable even when its
        # text is identical to the previous one (same question asked twice)
        before_n, before_text = self._get_response()

        # Primary path: agent-browser fill + real Enter keypress. These are TRUSTED
        # CDP input events — meta.ai's main-page composer ignores synthetic
        # element.click() on its Send button (verified live 2026-07-10), but
        # submits fine on a real Enter.
        try:
            self._g._abw("fill", sel, prompt, timeout=30)
            time.sleep(0.5)
            self._g._abw("press", "Enter", timeout=15)
        except MetaError:
            # Fallback: JS fill + Send-button click (works on the older /vibes composer)
            fill_result = self._g._eval(_fill_input_js(json.dumps(prompt), json.dumps(sel)))
            if "no_input" in str(fill_result):
                raise MetaError(f"Could not fill input (selector={sel})")
            time.sleep(0.5)
            click_result = self._g._eval(_click_send_js(json.dumps(_SEND_ARIA)))
            if "no_send" in str(click_result):
                raise MetaError("Send button not found or not clickable")

        # Wait for new response to appear and finish streaming
        end = time.time() + timeout
        last_text = None       # last text seen SINCE a new reply appeared
        stable_count = 0
        STABLE_NEEDED = 3      # 3 consecutive same-text non-streaming polls = done

        while time.time() < end:
            time.sleep(2)
            n, current = self._get_response()
            # _eval may return a bool or the strings "true"/"false" — normalize
            still_streaming = self._g._eval(_is_streaming_js()) in (True, "true")

            is_new = n > before_n or (bool(current) and current != before_text)
            if not is_new:
                continue
            if current and current == last_text and not still_streaming:
                stable_count += 1
                if stable_count >= STABLE_NEEDED:
                    return current
            else:
                stable_count = 0
                last_text = current

        # Timed out — return whatever partial reply we saw
        if last_text:
            return last_text
        raise MetaError(f"No response received within {timeout}s")
