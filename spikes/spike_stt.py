"""Spike: prove faster-whisper large-v3-turbo int8 works on the GTX 1650 for EN + BG.

Usage:
  python spike_stt.py --wav path.wav --lang en --device cuda
  python spike_stt.py --mic 10 --lang bg --device cpu   (record 10s from default mic)
"""
import argparse
import site
import sys
import time
from pathlib import Path


def cuda_dll_setup():
    """Use the app's real CUDA DLL setup (PATH + preload; add_dll_directory alone fails)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from flowlocal.cuda_setup import setup_cuda_dlls

    setup_cuda_dlls()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", help="transcribe this wav file")
    ap.add_argument("--mic", type=int, default=0, help="record N seconds from mic instead")
    ap.add_argument("--lang", default="en", choices=["en", "bg"])
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--beam", type=int, default=5)
    args = ap.parse_args()

    cuda_dll_setup()
    from faster_whisper import WhisperModel

    t0 = time.monotonic()
    print(f"Loading {args.model} on {args.device} (int8)...", flush=True)
    model = WhisperModel(args.model, device=args.device, compute_type="int8")
    print(f"Model loaded in {time.monotonic() - t0:.1f}s", flush=True)

    if args.wav:
        audio = args.wav
    elif args.mic:
        import numpy as np
        import sounddevice as sd
        print(f"Recording {args.mic}s from default mic... speak now!", flush=True)
        rec = sd.rec(int(args.mic * 16000), samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        audio = rec.flatten()
    else:
        sys.exit("Provide --wav or --mic N")

    t1 = time.monotonic()
    segments, info = model.transcribe(audio, language=args.lang, beam_size=args.beam)
    text = " ".join(s.text.strip() for s in segments)
    print(f"Transcribed in {time.monotonic() - t1:.1f}s (lang={info.language})", flush=True)
    print("TEXT:", text, flush=True)


if __name__ == "__main__":
    main()
