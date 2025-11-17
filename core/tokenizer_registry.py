"""
    Unified tokenizer registry for Qwen / LLaMA / DeepSeek / GPT.

    Usage:
        from tokenizer_registry import estimate_tokens
        n = estimate_tokens("你好，世界", tokenizer_type="qwen1.5b")

    Workflow
        名字中包含 "qwen" → 走 Qwen
        包含 "llama" → 走 LLaMA
        包含 "deepseek" → 走 DeepSeek
        以 "gpt" 开头或含 "gpt-3"/"gpt-4" → 走 GPT（tiktoken）

        没有 transformers：直接跳过 HF tokenizer
        没有 tiktoken：直接跳过 GPT 专用逻辑
        全都失败：len(text) 兜底，不会报错
"""

# from __future__ import annotations
from functools import lru_cache
from typing import Optional
from CacheRoute.util.timer import timing

# 这些库可能不存在，所以用 try/except 处理
try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None  # type: ignore

try:
    import tiktoken  # for GPT-family models
except ImportError:
    tiktoken = None  # type: ignore


class TokenizerRegistry:
    """
    统一管理不同模型族的 tokenizer，并提供按模型名自动路由的能力。
    FAST_MODE:是否启用快分词加速处理，TRUE启用，False执行正常的tokenizer分词。
    """
    FAST_MODE = False

    # 可以根据你自己的命名规则再继续加
    # key 是“模型族”，value 是默认的 HF 模型名
    HF_FAMILY_DEFAULTS = {
        "qwen": "Qwen/Qwen2-1.5B",
        "llama": "meta-llama/Meta-Llama-3-8B",
        "deepseek": "deepseek-ai/deepseek-moe-16b",  # 你可以换成自己常用的
    }

    @classmethod
    def detect_family(cls, tokenizer_type: str) -> str:
        """
        根据模型名/类型推断属于哪个族：qwen / llama / deepseek / gpt / other
        """
        name = tokenizer_type.lower()

        if "qwen" in name:
            return "qwen"
        if "llama" in name or "lLaMA".lower() in name:
            return "llama"
        if "deepseek" in name:
            return "deepseek"
        if name.startswith("gpt") or "gpt-3" in name or "gpt-4" in name:
            return "gpt"

        # 兜底归为 other
        return "other"

    # ---------------- GPT 系列（tiktoken） ----------------

    @classmethod
    @lru_cache(maxsize=None)
    def _get_gpt_encoding(cls, model_name: str):
        if tiktoken is None:
            return None

        try:
            return tiktoken.encoding_for_model(model_name)
        except Exception:
            # 如果具体模型不识别，就用通用的 cl100k_base
            try:
                return tiktoken.get_encoding("cl100k_base")
            except Exception:
                return None

    @classmethod
    def _gpt_count_tokens(cls, text: str, model_name: str) -> Optional[int]:
        enc = cls._get_gpt_encoding(model_name)
        if enc is None:
            return None
        # tiktoken 返回的是 list[int]
        return len(enc.encode(text))

    # ---------------- HF 系列（Qwen / LLaMA / DeepSeek） ----------------


    @classmethod
    # @timing
    @lru_cache(maxsize=None)
    def _get_hf_tokenizer(cls, hf_model_name: str):
        if AutoTokenizer is None:
            return None

        try:
            # trust_remote_code=True 方便适配 Qwen/DeepSeek 这类自定义 tokenizer
            return AutoTokenizer.from_pretrained(hf_model_name, trust_remote_code=True,use_fast=True)
        except Exception:
            return None

    @classmethod
    # @timing
    def _hf_count_tokens(cls, text: str, family: str, model_name: str) -> Optional[int]:
        """
        对 Qwen/LLaMA/DeepSeek 这类 HF 模型计数。
        """
        # 先看是不是直接给了完整 HF 模型名（如 'Qwen/Qwen2-1.5B'）
        if "/" in model_name:
            hf_name = model_name
        else:
            # 否则用 family 默认的 HF 名称
            hf_name = cls.HF_FAMILY_DEFAULTS.get(family)

        if hf_name is None:
            return None

        tok = cls._get_hf_tokenizer(hf_name)
        if tok is None:
            return None

        try:
            # 对大部分 HF tokenizer，encode 返回 token id list
            # add_special_tokens=False 避免再加 BOS/EOS 之类的
            return len(tok.encode(text, add_special_tokens=False))
        except Exception:
            return None

    # ---------------- 对外统一接口 ----------------

    @classmethod
    def estimate_tokens(cls, text: str, model_name: str) -> int:
        """
        按模型名自动选择 tokenizer，返回 token 数。
        如果环境里缺少 transformers/tiktoken 或解析失败，则退化为 len(text)。

        :param text: 输入文本
        :param model_name: 模型名或模型类型，如
                           'qwen1.5b' / 'Qwen/Qwen2-1.5B'
                           'llama3-8b'
                           'deepseek-v2'
                           'gpt-4o-mini'
        """
        family = cls.detect_family(model_name)

        # --- 快速近似模式：完全跳过慢 tokenizer ---
        if cls.FAST_MODE:
            print("use Fast tokenizer")
            # 可以按族给一个缩放系数，便于之后细调
            rough_ratio = {
                "deepseek": 1.0,
                "qwen": 1.0,
                "llama": 0.8,
                "gpt": 0.75,
            }.get(family, 1.0)
            return int(len(text) * rough_ratio)

        # 1) GPT 系列 → tiktoken
        if family == "gpt":
            print(f"user tokenizer {model_name} ")
            n = cls._gpt_count_tokens(text, model_name)
            if n is not None:
                return n

        # 2) Qwen / LLaMA / DeepSeek → HF tokenizer
        if family in {"qwen", "llama", "deepseek"}:
            print(f"user tokenizer {model_name} ")
            n = cls._hf_count_tokens(text, family, model_name)
            if n is not None:
                return n

        # 3) 其他 / 都失败 → 退化为按字符数估算
        return len(text)

    @classmethod
    def warmup_tokenizers(cls,model_name:str):
        """
            预加载某个模型对应的 tokenizer，使后续 estimate_tokens 调用不再触发冷启动。
        """
        family = cls.detect_family(model_name)

        if family == "gpt":
            # 只会触发 _get_gpt_encoding 的 lru_cache
            cls._get_gpt_encoding(model_name)
            print("tokenizer warmup successful")
        elif family in {"qwen", "llama", "deepseek"}:
            if "/" in model_name:
                hf_name = model_name
            else:
                hf_name = cls.HF_FAMILY_DEFAULTS.get(family)
            if hf_name is not None:
                cls._get_hf_tokenizer(hf_name)
                print("tokenizer warmup successful")
            else:
                print("warmup failed, please check up model type.")


# 为了用起来更方便，暴露一个顶层函数
def estimate_tokens(text: str, model_name: str) -> int:
    """
    统一入口：估计某模型下文本的 token 数。
    """
    return TokenizerRegistry.estimate_tokens(text, model_name)
