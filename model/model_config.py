# 读取模型参数信息

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union
import json
import pathlib

try:
    import yaml  # pip install pyyaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False
    yaml = None


# 自动定位到当前脚本的目录，以获取配置文件
PROJECT_ROOT  = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "model" / f"model_configs.yaml"


@dataclass(frozen=True)
class ModelConfig:
    # 定义模型结构体，包含模型的相关参数
    model_type: str                 # 模型类型
    model_layer: int                # 模型层数
    heads: int                      # 模型注意力头数
    qk_head_dim: int                # 每个头的QK向量维度
    v_head_dim: int                 # 每个头的V向量维度，通常与QK相同
    q_lora_rank: int                # Q的LoRA低秩维度
    kv_lora_rank: int               # KV的LoRA低秩维度
    hidden_dim: int                 # 隐藏层维度
    qk_rope_head_dim: int           # 每个头QK向量的RoPE位置维度，即前64维会加入旋转位置编码信息，用于建模序列位置
    n_heads: int
    causal_mask_cof: int = 2        # 开启因果=2，关闭=1
    n_shared_experts: int = 1       # MoE专有，共享专家数量
    n_routed_experts: int = 256     # MoE专有，专家门控可动态选择的专家数量
    moe_inter_dim: int = 2048       # MoE专有，专家层中间维度
    n_activated_experts: int = 8    # MoE专有，每个token实际激活的专家数

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelConfig":
        # 允许配置里缺失 n_heads 时，回退成 heads
        if "n_heads" not in d and "heads" in d:
            d = {**d, "n_heads": d["heads"]}
        # 基本校验（可按需加更多）
        required = [
            "model_layer","heads","qk_head_dim","kv_lora_rank","hidden_dim","q_lora_rank",
            "qk_rope_head_dim","v_head_dim","n_heads"
        ]
        missing = [k for k in required if k not in d]
        if missing:
            raise ValueError(f"ModelConfig 缺少必需字段: {missing}")
        return cls(**d)

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    def __repr__(self):
        return (
            f"ModelConfig(\n"
            f"  model_type={self.model_type},\n"
            f"  heads={self.heads},\n"
            f"  qk_head_dim={self.qk_head_dim},\n"
            f"  kv_lora_rank={self.kv_lora_rank},\n"
            f"  hidden_dim={self.hidden_dim},\n"
            f"  q_lora_rank={self.q_lora_rank},\n"
            f"  qk_rope_head_dim={self.qk_rope_head_dim},\n"
            f"  v_head_dim={self.v_head_dim},\n"
            f"  n_heads={self.n_heads},\n"
            f"  causal_mask_cof={self.causal_mask_cof},\n"
            f"  n_shared_experts={self.n_shared_experts},\n"
            f"  n_routed_experts={self.n_routed_experts},\n"
            f"  moe_inter_dim={self.moe_inter_dim},\n"
            f"  n_activated_experts={self.n_activated_experts}\n"
            f")"
        )


def _load_mapping(path: Union[str, pathlib.Path]) -> Dict[str, Dict[str, Any]]:
    """读取 YAML/JSON，返回 {model_name: {param: value}} 的映射。"""
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到配置文件: {p}")

    if p.suffix.lower() in {".yaml", ".yml"}:
        if not _YAML_OK:
            raise RuntimeError("未安装 pyyaml，无法读取 YAML。请 `pip install pyyaml`")
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    elif p.suffix.lower() == ".json":
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise ValueError(f"不支持的配置格式: {p.suffix}，仅支持 .yaml/.yml/.json")

    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是字典：{模型名: 参数字典}")
    return data


def get_config_by_model(model_name: str,
                            config_path: Union[str, pathlib.Path] = DEFAULT_CONFIG_PATH
                            ) -> ModelConfig:
    """
    根据模型名读取外部文件，返回对应的 ModelConfig。
    """
    # print(DEFAULT_CONFIG_PATH)
    mapping = _load_mapping(config_path)
    key = str(model_name)
    if key not in mapping:
        # 支持大小写/别名模糊匹配
        normalized = {k.lower(): k for k in mapping.keys()}
        if key.lower() not in normalized:
            raise KeyError(f"配置中不存在模型: {model_name}；可用项：{list(mapping.keys())}")
        key = normalized[key.lower()]
    return ModelConfig.from_dict(mapping[key])


