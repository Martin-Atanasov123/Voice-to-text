"""faster-whisper wrapper with a VRAM-aware model chain.

Benchmarks on this machine (GTX 1650, VRAM usually ~80% taken by other apps):
- large-v3-turbo/cuda with contended VRAM: 44-197s per 11s clip (driver pages
  weights to system RAM — it "works" but thrashes, so try/except can't catch it;
  only a free-VRAM probe can)
- large-v3-turbo/cpu: ~13s per 11s clip — too slow
- small/cpu int8 beam1: ~2.6s per 11s clip, same text on test samples

Chain (device=auto): turbo/cuda IF >= 3GB VRAM free, else small/cpu.
cuda_setup.setup_cuda_dlls() must run before this module is imported.
"""
import logging
import subprocess

import numpy as np

log = logging.getLogger(__name__)

TURBO_VRAM_FREE_MB = 3000


def _free_vram_mb() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return 0


class Transcriber:
    def __init__(
        self,
        model_name: str = "small",
        device: str = "auto",
        hq_model: str = "large-v3-turbo",
        beam_size: int = 1,
    ):
        self.model_name = model_name
        self.hq_model = hq_model
        self.device = device
        self.beam_size = beam_size
        self.model = None
        self.active: tuple[str, str] | None = None  # (model_name, device) loaded

    def _chain(self) -> list[tuple[str, str]]:
        if self.device == "cpu":
            return [(self.model_name, "cpu")]
        if self.device == "cuda":
            return [(self.model_name, "cuda"), (self.model_name, "cpu")]
        # auto: only worth the GPU if the big model truly fits in free VRAM
        chain = []
        if _free_vram_mb() >= TURBO_VRAM_FREE_MB:
            chain.append((self.hq_model, "cuda"))
        chain.append((self.model_name, "cpu"))
        return chain

    def load(self) -> None:
        from faster_whisper import WhisperModel

        last_err = None
        for name, device in self._chain():
            try:
                log.info("Loading whisper %s on %s (int8)", name, device)
                self.model = WhisperModel(name, device=device, compute_type="int8")
                self.active = (name, device)
                return
            except Exception as e:  # OOM, missing CUDA DLLs, etc.
                log.warning("Load failed for %s/%s: %s", name, device, e)
                last_err = e
        raise RuntimeError(f"Could not load any whisper model: {last_err}")

    def transcribe(self, audio: np.ndarray, language: str) -> str:
        if self.model is None:
            self.load()
        try:
            return self._run(audio, language)
        except Exception as e:
            # GPU state can degrade after load (VRAM stolen) — retreat to small/cpu
            log.warning("Transcribe failed on %s: %s — retrying on cpu", self.active, e)
            from faster_whisper import WhisperModel

            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            self.active = (self.model_name, "cpu")
            return self._run(audio, language)

    def _run(self, audio: np.ndarray, language: str) -> str:
        segments, _info = self.model.transcribe(
            audio, language=language, beam_size=self.beam_size, vad_filter=True
        )
        return " ".join(s.text.strip() for s in segments).strip()
