#!/usr/bin/env python3
"""Render the SAME documentary line in several Kokoro voices so the owner can
pick the most natural American English by ear (owner request 2026-11-01).

Nobody can judge "most natural" from code, so this produces real audio files
and the post-processed version of each. Run on Actions (voice-preview workflow)
or locally on the phone.

    python3 tools/voice_preview.py            # default shortlist + post chain
    python3 tools/voice_preview.py am_onyx    # one specific voice
"""
import io
import os
import contextlib
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "voice_preview")
LINE = ("In the last six months, three labs shipped models that were supposed to "
        "arrive in 2027. Nobody outside those buildings saw it coming, and the "
        "numbers behind that claim are stranger than the headlines.")

SHORTLIST = ["af_heart", "am_michael", "am_fenrir", "am_onyx", "am_puck", "am_adam"]


def main(argv):
    voices = argv[1:] or SHORTLIST
    sys.path.insert(0, os.path.join(BASE, "factory"))
    os.makedirs(OUT, exist_ok=True)
    with contextlib.redirect_stderr(io.StringIO()):
        from kokoro_onnx import Kokoro
    kokoro = Kokoro(os.path.join(BASE, "tts_kokoro", "kokoro-v1.0.fp16.onnx"),
                    os.path.join(BASE, "tts_kokoro", "voices-v1.0.bin"))
    import soundfile as sf
    made = []
    for v in voices:
        try:
            audio, sr = kokoro.create(LINE, voice=v, speed=0.97, lang="en-us")
            raw = os.path.join(OUT, f"raw_{v}.wav")
            sf.write(raw, audio, sr)
            # same broadcast chain the production run uses
            import factory
            mp3 = os.path.join(OUT, f"voice_{v}.mp3")
            ok = factory._post_narration(raw, mp3)
            os.remove(raw)
            print(f"{v:12} -> {'OK' if ok else 'FAIL'}  {mp3}", flush=True)
            if ok:
                made.append(mp3)
        except Exception as ex:
            print(f"{v:12} -> error: {str(ex)[:90]}", flush=True)
    print("done:", len(made), "voice sample(s) in", OUT, flush=True)
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
