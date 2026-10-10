#!/usr/bin/env python3
"""Generate a professional YouTube thumbnail via ChatGPT (logged-in Browserbase session)
and install it as <rundir>/thumb.jpg for factory.py --setthumb.

Usage:
  python3 factory/chatgpt_thumb.py --wss <cdp-wss-url> --rundir <rundir> --prompt-file <file>

The agent must have called browserbase_navigate to https://chatgpt.com first and passes
the debug wss URL from that call. Requires the page to be logged in (chat composer present).

Exit codes:
  0  OK (thumb.jpg written)
  2  NOT_LOGGED_IN (no composer — keep the PIL thumbnail)
  3  LIMIT_REACHED (free-plan image limit — keep the PIL thumbnail)
  4  TIMEOUT / generation failed
  5  bad args
"""
import argparse, base64, json, os, sys, time, urllib.parse
import websocket

POLL_MAX = 420  # seconds to wait for image generation (slow free-plan gens run 3-6 min)


def connect(wss):
    ws = websocket.create_connection(wss, timeout=300)
    mid = [0]

    def ev(expr, await_promise=False):
        mid[0] += 1
        ws.send(json.dumps({
            "id": mid[0], "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True,
                        "awaitPromise": await_promise, "userGesture": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == mid[0]:
                return m.get("result", {}).get("result", {}).get("value")

    def key(ktype, key="Enter", code="Enter", vk=13):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": "Input.dispatchKeyEvent",
                            "params": {"type": ktype, "key": key, "code": code,
                                       "windowsVirtualKeyCode": vk,
                                       "nativeVirtualKeyCode": vk}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == mid[0]:
                return m

    return ws, ev, key


def try_switch_account(ev, key, account2):
    """Open the ChatGPT account menu and click the entry matching account2.
    Returns True if a matching entry existed and was clicked."""
    if not account2:
        return False
    opened = ev(
        "(()=>{const btn=document.querySelector('[data-testid=\"accounts-profile-button\"]')"
        "||[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').toLowerCase().includes('account')&&(b.getAttribute('aria-label')||'').toLowerCase().includes('menu'));"
        "if(!btn) return false; btn.click(); return true;})()")
    if opened is not True:
        return False
    time.sleep(4)
    found = ev(
        f"(()=>{{const els=[...document.querySelectorAll('button, a, [role=\"menuitem\"]')];"
        f"const hit=els.find(e=>e.innerText && e.innerText.toLowerCase().includes({json.dumps(account2.lower())}));"
        f"if(!hit) return false; hit.click(); return true;}})()")
    if found is not True:
        return False
    time.sleep(8)
    return ev("!!(document.getElementById('prompt-textarea') || document.querySelector('[contenteditable=true][role=textbox]'))") is True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wss", required=True)
    ap.add_argument("--rundir", required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--variants", type=int, default=1, help="generate N candidates (A/B alternates; candidate 1 goes live)")
    ap.add_argument("--account2", default=os.environ.get("CHATGPT_ACCOUNT2", ""),
                    help="second account email; on LIMIT_REACHED try switching to it once")
    args = ap.parse_args()
    style_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content_policy.json")
    style = json.load(open(style_file)).get("production_style", {})
    if style.get("account_switches_allowed") is False:
        # Owner requires one existing ChatGPT account only; never switch identities.
        args.account2 = ""
    elif not args.account2:
        # Config is used only when the active owner policy allows account switching.
        cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "chatgpt_accounts.json")
        if os.path.exists(cfg):
            try:
                args.account2 = json.load(open(cfg)).get("account2", "")
            except Exception:
                pass

    prompt = open(args.prompt_file).read().strip()
    assert len(prompt) > 100, "prompt too short"

    ws, ev, key = connect(args.wss)
    try:
        n = max(1, getattr(args, "variants", 1))
        made = 0
        for vi in range(n):
            args._vi = vi
            p = prompt if vi == 0 else prompt + f"\n\nIMPORTANT: alternative composition {vi+1} — change camera angle, background mood and color emphasis so it looks clearly different from other versions, same text overlay."
            for _attempt in (1, 2):
                r = run(ws, ev, key, args, p)
                if r == "OK":
                    made += 1
                    break
                if r != "SWITCH_RETRY":
                    break
            if r != "OK" and made == 0:
                return
        if n > 1 and made:
            import shutil
            shutil.copyfile(os.path.join(args.rundir, f"thumb_candidate_1.jpg"),
                           os.path.join(args.rundir, "thumb.jpg"))
            print(f"OK variants: {made} candidates saved; candidate 1 set as thumb.jpg")
    finally:
        try:
            ws.close()
        except Exception:
            pass


def run(ws, ev, key, args, prompt):
    if True:
        # logged in? composer present?
        if ev("!!(document.getElementById('prompt-textarea') || document.querySelector('[contenteditable=true][role=textbox]'))") is not True:
            print("NOT_LOGGED_IN: no composer on page")
            sys.exit(2)
        old_srcs = set(ev("[...document.querySelectorAll('img')].map(i=>i.src)") or [])
        # focus composer and type
        ev("(document.getElementById('prompt-textarea') || document.querySelector('[contenteditable=true][role=textbox]')).focus()")
        ws.send(json.dumps({"id": 9991, "method": "Input.insertText",
                            "params": {"text": prompt}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 9991:
                break
        time.sleep(2)
        if int(ev("(document.getElementById('prompt-textarea') || document.querySelector('[contenteditable=true][role=textbox]')).textContent.length") or 0) < 100:
            print("TYPING_FAILED")
            sys.exit(4)
        # submit
        key("keyDown"); key("keyUp")

        # poll for generation
        t0 = time.time()
        src = None
        while time.time() - t0 < POLL_MAX:
            time.sleep(10)
            body = ev("document.body.innerText") or ""
            low = body.lower()
            if "image limit" in low or "limit reached" in low or \
               "you've hit the limit" in low or "hit your limit" in low:
                print(f"LIMIT_REACHED (account2 configured: {bool(args.account2)})")
                if args.account2:
                    print("trying account switch ...")
                    time.sleep(5)
                    # dismiss the limit dialog
                    ev("(()=>{const b=[...document.querySelectorAll('button')].find(b=>/ok|got it|close/i.test(b.innerText)); if(b){b.click(); return true;} return false;})()")
                    time.sleep(2)
                    if try_switch_account(ev, key, args.account2):
                        print("SWITCHED_TO_ACCOUNT2")
                        # new session may need a fresh page
                        time.sleep(5)
                        return "SWITCH_RETRY"
                    print("SWITCH_FAILED (second account not in session?)")
                sys.exit(3)
            srcs = ev("JSON.stringify([...document.querySelectorAll('img')].map(i=>i.src).filter(s=>s.includes('estuary') || s.startsWith('blob:')).slice(-3))")
            try:
                src_list = [v for v in json.loads(srcs or "[]") if v not in old_srcs]
            except Exception:
                src_list = []
            gen_running = ("creating image" in low or "making the first draft" in low
                           or "making" in low and "%" in body)
            if src_list and not gen_running:
                src = src_list[-1]
                break
        if not src:
            print("TIMEOUT: image never appeared")
            sys.exit(4)

        # download in-page (session cookies) -> base64
        b64 = ev(
            "(async()=>{const r=await fetch(" + json.dumps(src) + ",{credentials:'include'});"
            "if(!r.ok) return 'FETCH_FAIL'; const b=await r.blob();"
            "return await new Promise(res=>{const f=new FileReader();"
            "f.onload=()=>res(f.result.split(',')[1]);f.readAsDataURL(b);});})()",
            await_promise=True)
        if not b64 or b64 == "FETCH_FAIL":
            print("DOWNLOAD_FAILED")
            sys.exit(4)
        raw = base64.b64decode(b64)
        tmp_png = os.path.join(args.rundir, "_thumb_gpt_raw.png")
        open(tmp_png, "wb").write(raw)

        # crop to 16:9 -> 1280x720 jpg < 2MB
        from PIL import Image
        im = Image.open(tmp_png).convert("RGB")
        w, h = im.size
        t = 16 / 9
        if w / h > t:
            nw = int(h * t); x = (w - nw) // 2; im = im.crop((x, 0, x + nw, h))
        else:
            nh = int(w / t); y = (h - nh) // 2; im = im.crop((0, y, w, y + nh))
        im = im.resize((1280, 720), Image.LANCZOS)
        out = (os.path.join(args.rundir, f"thumb_candidate_{getattr(args,'_vi',0)+1}.jpg")
               if getattr(args, "variants", 1) > 1 else os.path.join(args.rundir, "thumb.jpg"))
        q = 92
        while q >= 60:
            im.save(out, "JPEG", quality=q)
            if os.path.getsize(out) < 2_000_000:
                break
            q -= 10
        os.remove(tmp_png)
        print(f"OK thumb={out} size={os.path.getsize(out)}")
        return "OK"


if __name__ == "__main__":
    main()
