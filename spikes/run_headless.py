"""Milestone 1/2 headless runner: hold CapsLock -> speak -> release -> text pasted.

Run in a console:  .venv\\Scripts\\python spikes\\run_headless.py [--no-cleanup]
Ctrl+C to exit. No overlay/tray yet — console prints show pipeline state.
"""
import argparse
import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flowlocal.cuda_setup import setup_cuda_dlls

setup_cuda_dlls()

from flowlocal.audio import Recorder
from flowlocal.cleanup import OllamaCleaner
from flowlocal.config import Config
from flowlocal.hotkey import CapsLockHook
from flowlocal.inserter import insert_text
from flowlocal.layout import get_dictation_language
from flowlocal.stt import Transcriber


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cleanup", action="store_true", help="paste raw transcript")
    args = ap.parse_args()

    cfg = Config.load()
    recorder = Recorder(device=cfg.mic_device, max_seconds=cfg.max_record_s)
    stt = Transcriber(cfg.whisper_model, cfg.whisper_device, cfg.whisper_model_hq, cfg.beam_size)
    cleaner = OllamaCleaner(
        cfg.ollama_url,
        {"en": cfg.ollama_model_en, "bg": cfg.ollama_model_bg},
        cfg.cleanup_timeout_s,
    )

    print("Preloading whisper model...", flush=True)
    stt.load()
    print(f"Ready (whisper: {stt.active}).", flush=True)
    use_cleanup = cfg.cleanup_enabled and not args.no_cleanup
    if use_cleanup:
        ok = cleaner.health_check()
        print(f"Ollama: {'ok, warming up' if ok else 'NOT AVAILABLE — raw paste mode'}", flush=True)
        if ok:
            threading.Thread(target=cleaner.warm_up, daemon=True).start()

    jobs: queue.Queue = queue.Queue(maxsize=1)
    ctx = {}

    def on_press():
        if jobs.full():
            print("[busy] dictation in progress — ignored", flush=True)
            return
        ctx["language"] = get_dictation_language()
        recorder.start()
        print(f"[recording] lang={ctx['language']}", flush=True)

    def on_release(held):
        audio = recorder.stop()
        try:
            jobs.put_nowait((audio, ctx.get("language", "en"), held))
        except queue.Full:
            pass

    def on_tap():
        recorder.stop()  # tap started the stream on press; discard it

    hook = CapsLockHook(on_press, on_release, on_tap, cfg.tap_threshold_s)
    hook.start()
    print("Hold CapsLock and speak. Ctrl+C to quit.", flush=True)

    def worker():
        while True:
            audio, language, held = jobs.get()
            try:
                t0 = time.monotonic()
                print(f"[transcribing] {held:.1f}s of audio...", flush=True)
                raw = stt.transcribe(audio, language)
                print(f"[raw {time.monotonic()-t0:.1f}s] {raw}", flush=True)
                if not raw:
                    print("[skip] empty transcript", flush=True)
                    continue
                text = raw
                if use_cleanup:
                    cleaned, ok = cleaner.clean(raw, language)
                    if ok:
                        text = cleaned
                        print(f"[cleaned {time.monotonic()-t0:.1f}s] {text}", flush=True)
                    else:
                        print("[warn] cleanup failed — pasting raw", flush=True)
                insert_text(text)
                print(f"[pasted {time.monotonic()-t0:.1f}s total]", flush=True)
            except Exception as e:
                print(f"[error] {e}", flush=True)
            finally:
                jobs.task_done()

    threading.Thread(target=worker, daemon=True).start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        hook.stop()
        print("Bye.", flush=True)


if __name__ == "__main__":
    main()
