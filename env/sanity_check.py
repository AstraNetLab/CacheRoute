import sys
import importlib
import importlib.metadata as md

def ok(msg):
    print(f"[OK] {msg}")

def warn(msg):
    print(f"[WARN] {msg}")

def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)

print("=" * 60)
print("Sanity Check: vLLM + LMCache + Torch Environment")
print("=" * 60)

# -------------------------------
# 1. Python version
# -------------------------------
ok(f"Python version: {sys.version.split()[0]}")

# -------------------------------
# 2. Core packages & versions
# -------------------------------
pkgs = [
    "numpy",
    "torch",
    "scipy",
    "scikit-learn",
    "pandas",
    "faiss-cpu",
    "transformers",
    "sentence-transformers",
    "datasets",
    "fastapi",
    "uvicorn",
    "aiohttp",
]

print("\n[Check] Core Python packages:")
for p in pkgs:
    try:
        v = md.version(p)
        ok(f"{p}=={v}")
    except Exception:
        fail(f"{p} NOT installed")

# -------------------------------
# 3. Torch + CUDA
# -------------------------------
import torch

print("\n[Check] Torch / CUDA:")
ok(f"torch version: {torch.__version__}")
ok(f"CUDA available: {torch.cuda.is_available()}")

if not torch.cuda.is_available():
    fail("CUDA is NOT available inside container")

ok(f"CUDA version (torch): {torch.version.cuda}")
ok(f"GPU count: {torch.cuda.device_count()}")

for i in range(torch.cuda.device_count()):
    name = torch.cuda.get_device_name(i)
    ok(f"GPU[{i}]: {name}")

# -------------------------------
# 4. FAISS basic functionality
# -------------------------------
print("\n[Check] FAISS:")
import faiss
import numpy as np

x = np.random.rand(10, 128).astype("float32")
index = faiss.IndexFlatL2(128)
index.add(x)
D, I = index.search(x[:1], 3)
ok("FAISS IndexFlatL2 add/search works")

# -------------------------------
# 5. Transformers basic load (no model download)
# -------------------------------
print("\n[Check] Transformers:")
try:
    import transformers
    ok(f"transformers version: {transformers.__version__}")
except Exception as e:
    fail(f"Transformers import failed: {e}")

# -------------------------------
# 6. vLLM import & EngineArgs
# -------------------------------
print("\n[Check] vLLM:")
try:
    import vllm
    ok("vLLM import OK")
except Exception as e:
    fail(f"vLLM import failed: {e}")

try:
    from vllm.engine.arg_utils import EngineArgs
    ok("vLLM EngineArgs import OK")
except Exception as e:
    fail(f"vLLM EngineArgs import failed: {e}")

# -------------------------------
# 7. LMCache import
# -------------------------------
print("\n[Check] LMCache:")
try:
    import lmcache
    ok("LMCache import OK")
except Exception as e:
    fail(f"LMCache import failed: {e}")

# -------------------------------
# 8. Final verdict
# -------------------------------
print("\n" + "=" * 60)
print("✅ SANITY CHECK PASSED")
print("This container is SAFE to export as base image.")
print("=" * 60)

