import os
import torch
from sentence_transformers import SentenceTransformer
import time
import warnings
warnings.filterwarnings("ignore", message=".*flash attention.*")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

MODEL_NAME = "intfloat/multilingual-e5-small"

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device:", device)

    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.eval()
    torch.set_grad_enabled(False)
    print(f"Model loaded in {time.time() - t0:.2f} s")

    texts = [
        "这是一个部署测试。",
        "第二句话用于测试批处理。",
    ]

    t1 = time.time()
    emb = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    t2 = time.time()

    print("Shape:", emb.shape)                     # 预期 (2, 512)
    print("Encode time (ms):", (t2 - t1) * 1000)   # 编码耗时
    print("First 5 dims:", emb[0][:5])             # 看看向量长啥样

if __name__ == "__main__":
    main()
