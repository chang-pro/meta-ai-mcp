"""Edge-case tests for meta-ai-mcp. Fully offline — the browser layer is mocked.

Run:  venv/Scripts/python test_edge_cases.py
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meta_chat
import meta_image
import meta_video as MV
from meta_video import MetaError


NO_SLEEP = patch("time.sleep", lambda s: None)


def _node_check(js):
    """Validate a JS snippet with Node. Returns error string or None."""
    r = subprocess.run(
        ["node", "-e", "new Function(process.argv[1]); console.log('OK')", js],
        capture_output=True, text=True)
    return None if r.returncode == 0 else r.stderr.strip()[:200]


class JsInjectionTests(unittest.TestCase):
    """Nasty prompts must never break the generated JavaScript."""

    NASTY = [
        'He said "hello" and left',
        "single 'quotes' everywhere",
        "line1\nline2\r\nline3\ttabbed",
        r"C:\Users\test\new\table.txt",
        "'; alert(1); //",
        "}})();alert(1);(()=>{",
        "`backticks` and ${process.env.HOME} template injection",
        "emoji \U0001f525\U0001f4af café naïve 日本語",
        "js line separators and paragraph",  # U+2028/29 break naive JSON-in-JS
        "</script><script>alert(1)</script>",
        "x" * 10000,
    ]

    def test_fill_input_js_survives_nasty_prompts(self):
        for p in self.NASTY:
            js = meta_chat._fill_input_js(json.dumps(p), json.dumps("textarea"))
            err = _node_check(js)
            self.assertIsNone(err, f"prompt {p[:40]!r}: {err}")

    def test_submit_js_survives_nasty_prompts(self):
        """meta_video.submit builds its JS the same way — check its f-string too."""
        for p in self.NASTY:
            pj = json.dumps(p)
            js = f"""(() => {{
                const ta=document.querySelector('textarea'); if(!ta) return 'no-textarea';
                const set=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
                set.call(ta, {pj});
                return 'len='+ta.value.length;
            }})()"""
            err = _node_check(js)
            self.assertIsNone(err, f"prompt {p[:40]!r}: {err}")

    def test_static_js_snippets_valid(self):
        for name, js in {
            "find_input": meta_chat._find_input_js(),
            "click_send": meta_chat._click_send_js(json.dumps(["Send message", "Send"])),
            "last_response": meta_chat._last_response_js(),
            "is_streaming": meta_chat._is_streaming_js(),
        }.items():
            err = _node_check(js)
            self.assertIsNone(err, f"{name}: {err}")

    def test_selector_with_quotes_safe(self):
        js = meta_chat._fill_input_js(json.dumps("hi"), json.dumps('div[contenteditable="true"]'))
        self.assertIsNone(_node_check(js))


class FakeChatG:
    """Fake MetaVibes for MetaChat: dispatches _eval by JS content.

    By default _abw fill/press RAISES so tests exercise the JS fallback path;
    set trusted_input=True to simulate the primary agent-browser path."""

    def __init__(self, url="https://www.meta.ai/", find_sel="div[contenteditable='true']",
                 fill="filled:11", click="clicked:Send", streaming=False, trusted_input=False):
        self.url = url
        self.find_sel = find_sel
        self.fill = fill
        self.click = click
        self.streaming = streaming
        self.trusted_input = trusted_input
        self.responses = [(1, "old")]   # (count, text) returned before submit
        self.after = [(2, "new")]       # cycled through after Send is clicked
        self.sent = False
        self._after_i = 0
        self.opened = []

    def _abw(self, *args, **kw):
        self.opened.append(args)
        if args and args[0] in ("fill", "press"):
            if not self.trusted_input:
                raise MetaError("abw input unavailable in fake")
            if args[0] == "press":
                self.sent = True
        return ""

    def _eval(self, js, timeout=60):
        if "location.href" in js:
            return self.url
        if "const sels=" in js:
            return self.find_sel
        if "no_input" in js:
            return self.fill
        if "no_send" in js:
            self.sent = True
            return self.click
        if "pack(" in js:
            seq = self.after if self.sent else self.responses
            n, t = seq[min(self._after_i, len(seq) - 1)]
            if self.sent:
                self._after_i += 1
            return json.dumps({"n": n, "t": t})
        if "indicators" in js:
            return self.streaming
        raise AssertionError(f"unexpected eval: {js[:60]}")


class MetaChatTests(unittest.TestCase):

    @NO_SLEEP
    def test_happy_path(self):
        g = FakeChatG()
        g.after = [(2, "the answer")]
        out = meta_chat.MetaChat(g).ask("q", timeout=30)
        self.assertEqual(out, "the answer")

    @NO_SLEEP
    def test_trusted_input_path(self):
        """Primary path: agent-browser fill + Enter, no JS fill/click needed."""
        g = FakeChatG(trusted_input=True)
        g.after = [(2, "trusted answer")]
        out = meta_chat.MetaChat(g).ask("q", timeout=30)
        self.assertEqual(out, "trusted answer")
        cmds = [a[0] for a in g.opened]
        self.assertIn("fill", cmds)
        self.assertIn("press", cmds)

    @NO_SLEEP
    def test_same_answer_twice_detected_by_count(self):
        """Re-asking a question yields identical text — count bump must detect it."""
        g = FakeChatG()
        g.responses = [(1, "42")]
        g.after = [(2, "42")]           # same text, one more message
        out = meta_chat.MetaChat(g).ask("what is 6x7", timeout=30)
        self.assertEqual(out, "42")

    @NO_SLEEP
    def test_text_change_without_count_change(self):
        """Some selectors only ever match the last bubble (count stays 1)."""
        g = FakeChatG()
        g.responses = [(1, "old")]
        g.after = [(1, "fresh reply")]
        out = meta_chat.MetaChat(g).ask("q", timeout=30)
        self.assertEqual(out, "fresh reply")

    @NO_SLEEP
    def test_streaming_string_false_still_completes(self):
        """_eval returning the STRING 'false' must not stall the stability check."""
        g = FakeChatG(streaming="false")
        g.after = [(2, "done")]
        out = meta_chat.MetaChat(g).ask("q", timeout=30)
        self.assertEqual(out, "done")

    @NO_SLEEP
    def test_timeout_raises_when_no_reply(self):
        g = FakeChatG()
        g.after = [(1, "old")]          # nothing ever changes
        with self.assertRaises(MetaError):
            meta_chat.MetaChat(g).ask("q", timeout=0.3)

    @NO_SLEEP
    def test_no_composer_raises(self):
        g = FakeChatG(find_sel=None)
        with self.assertRaises(MetaError):
            meta_chat.MetaChat(g).ask("q", timeout=5)

    @NO_SLEEP
    def test_fill_failure_raises(self):
        g = FakeChatG(fill="no_input")
        with self.assertRaises(MetaError):
            meta_chat.MetaChat(g).ask("q", timeout=5)

    def test_get_response_malformed(self):
        g = FakeChatG()
        chat = meta_chat.MetaChat(g)
        g._eval = lambda js, timeout=60: "garbage not json"
        self.assertEqual(chat._get_response(), (0, "garbage not json"))
        g._eval = lambda js, timeout=60: None
        self.assertEqual(chat._get_response(), (0, ""))
        g._eval = lambda js, timeout=60: json.dumps({"n": "weird", "t": None})
        self.assertEqual(chat._get_response(), (0, ""))


class FakeImgG:
    """Fake MetaVibes for meta_image: per-poll img lists + in-page fetch."""

    def __init__(self, polls, payload=b"x" * 25000):
        self.polls = list(polls)       # list of url-lists, consumed per _t39_imgs call
        self.payload = payload
        self.i = 0

    def ensure_composer(self):
        pass

    def submit(self, prompt):
        self.submitted = prompt

    def _eval(self, js, timeout=60):
        if "querySelectorAll('img')" in js:
            out = self.polls[min(self.i, len(self.polls) - 1)]
            self.i += 1
            if isinstance(out, Exception):
                raise out
            return json.dumps(out)
        raise AssertionError(f"unexpected eval: {js[:60]}")

    def _abw(self, cmd, js, timeout=90):
        b64 = base64.b64encode(self.payload).decode()
        return json.dumps("data:image/jpeg;base64," + b64)


class MetaImageTests(unittest.TestCase):

    URL = "https://cdn.example/t39.105495/img1.jpg"

    def _out(self, d):
        return os.path.join(d, "out.jpg")

    @NO_SLEEP
    def test_success_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            g = FakeImgG(polls=[[], [self.URL], [self.URL]])
            res = meta_image.generate_image("a cat", self._out(d), timeout=30, g=g)
            self.assertEqual(res, self._out(d))
            self.assertEqual(os.path.getsize(res), 25000)

    @NO_SLEEP
    def test_transient_poll_error_recovers(self):
        """A browser hiccup mid-wait must not abort the run."""
        with tempfile.TemporaryDirectory() as d:
            g = FakeImgG(polls=[[], MetaError("hiccup"), MetaError("hiccup"),
                                [self.URL], [self.URL]])
            res = meta_image.generate_image("a cat", self._out(d), timeout=60, g=g)
            self.assertEqual(res, self._out(d))

    @NO_SLEEP
    def test_empty_repoll_falls_back(self):
        """Confirmation re-poll returning [] must not IndexError."""
        with tempfile.TemporaryDirectory() as d:
            g = FakeImgG(polls=[[], [self.URL], []])
            res = meta_image.generate_image("a cat", self._out(d), timeout=30, g=g)
            self.assertEqual(res, self._out(d))

    @NO_SLEEP
    def test_tiny_image_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            g = FakeImgG(polls=[[], [self.URL], [self.URL]], payload=b"x" * 100)
            res = meta_image.generate_image("a cat", self._out(d), timeout=30, g=g)
            self.assertIsNone(res)
            self.assertFalse(os.path.exists(self._out(d)))

    @NO_SLEEP
    def test_timeout_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            g = FakeImgG(polls=[[]])
            res = meta_image.generate_image("a cat", self._out(d), timeout=10, g=g)
            self.assertIsNone(res)

    @NO_SLEEP
    def test_imagine_prefix_not_doubled(self):
        with tempfile.TemporaryDirectory() as d:
            g = FakeImgG(polls=[[], [self.URL], [self.URL]])
            meta_image.generate_image("Imagine a dog", self._out(d), timeout=30, g=g)
            self.assertEqual(g.submitted, "Imagine a dog")
            g2 = FakeImgG(polls=[[], [self.URL], [self.URL]])
            meta_image.generate_image("a dog", self._out(d), timeout=30, g=g2)
            self.assertEqual(g2.submitted, "Imagine a dog")


class MetaVideoTests(unittest.TestCase):

    def test_download_rejects_blob_and_junk(self):
        fake = object.__new__(MV.MetaVibes)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.mp4")
            for bad in ("blob:https://meta.ai/x", None, "", 123, "ftp://x/y.mp4"):
                with self.assertRaises(MetaError, msg=f"url={bad!r}"):
                    MV.MetaVibes.download(fake, bad, out)

    @NO_SLEEP
    def test_wait_new_video_requires_stability(self):
        fake = object.__new__(MV.MetaVibes)
        seq = [["https://x.fbcdn.net/new.mp4"]] * 5
        fake.video_srcs = lambda: seq.pop(0) if seq else ["https://x.fbcdn.net/new.mp4"]
        url = MV.MetaVibes.wait_new_video(fake, before=[], timeout=5, poll=0.01)
        self.assertEqual(url, "https://x.fbcdn.net/new.mp4")

    @NO_SLEEP
    def test_wait_new_video_ignores_non_fbcdn(self):
        fake = object.__new__(MV.MetaVibes)
        fake.video_srcs = lambda: ["blob:x", "https://other.cdn/clip.mp4"]
        with self.assertRaises(MetaError):
            MV.MetaVibes.wait_new_video(fake, before=[], timeout=0.1, poll=0.01)

    @NO_SLEEP
    def test_rotate_account_devtools_list_format(self):
        """accounts/*.json in DevTools export format (list) must work, skipping malformed rows."""
        fake = object.__new__(MV.MetaVibes)
        with tempfile.TemporaryDirectory() as d:
            p1, p2 = os.path.join(d, "a.json"), os.path.join(d, "b.json")
            with open(p1, "w") as f:
                json.dump({"datr": "x"}, f)
            with open(p2, "w") as f:
                json.dump([{"name": "datr", "value": "y"},
                           {"value": "orphan-no-name"},
                           {"name": "ecto_1_sess", "value": "z"}], f)
            fake.accounts, fake.acct_idx = [p1, p2], 0
            captured = {}
            fake._cdp_cookie_ops = lambda ops: captured.update(ops=ops)
            fake._abw = lambda *a, **k: ""
            fake.ensure_composer = lambda: None
            who = MV.MetaVibes.rotate_account(fake)
            self.assertEqual(who, "b.json")
            methods = [m for m, _ in captured["ops"]]
            self.assertEqual(methods[0], "Network.clearBrowserCookies")
            names = [p["name"] for m, p in captured["ops"] if m == "Network.setCookie"]
            self.assertEqual(sorted(names), ["datr", "ecto_1_sess"])  # orphan row skipped


class McpServerTests(unittest.TestCase):
    """Input guards must reject bad prompts BEFORE any browser is touched."""

    @classmethod
    def setUpClass(cls):
        try:
            import mcp_server
            cls.srv = mcp_server
        except ImportError:
            cls.srv = None

    def _skip_if_no_mcp(self):
        if self.srv is None:
            self.skipTest("mcp package not installed in this interpreter")

    def test_generate_image_empty_prompt(self):
        self._skip_if_no_mcp()
        for bad in ("", "   ", "\n\t"):
            res = self.srv.generate_image(bad)
            self.assertFalse(res["success"])
            self.assertIn("empty", res["error"])

    def test_ask_meta_empty_prompt(self):
        self._skip_if_no_mcp()
        for bad in ("", "   "):
            res = self.srv.ask_meta(bad)
            self.assertFalse(res["success"])
            self.assertIn("empty", res["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
