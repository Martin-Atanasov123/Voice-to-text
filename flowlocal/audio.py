"""Microphone capture: 16kHz mono float32, minimal-work callback."""
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self, device: int | None = None, max_seconds: float = 120.0):
        self.device = device
        self.max_samples = int(max_seconds * SAMPLE_RATE)
        self._blocks: list[np.ndarray] = []
        self._sample_count = 0
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self.overflowed = False

    def _callback(self, indata, frames, time_info, status):
        # audio thread: append + count only
        if self._sample_count < self.max_samples:
            self._blocks.append(indata.copy())
            self._sample_count += frames
        else:
            self.overflowed = True

    def start(self) -> None:
        with self._lock:
            self._blocks = []
            self._sample_count = 0
            self.overflowed = False
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()

    def stop(self) -> np.ndarray:
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if not self._blocks:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._blocks).flatten()
            self._blocks = []
            return audio

    @property
    def seconds_recorded(self) -> float:
        return self._sample_count / SAMPLE_RATE
