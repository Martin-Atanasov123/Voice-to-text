"""Entry point: `python -m flowlocal`. CUDA DLL setup MUST precede faster_whisper imports."""
import sys

from .cuda_setup import setup_cuda_dlls

setup_cuda_dlls()

from .app import main  # noqa: E402  (import after DLL setup is the whole point)

if __name__ == "__main__":
    sys.exit(main())
