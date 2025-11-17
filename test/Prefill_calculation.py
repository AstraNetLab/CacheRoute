import numpy as np
import matplotlib.pyplot as plt
import time
from CacheRoute.model import model_config
from CacheRoute.core import Prompt
from CacheRoute.core import MLAmodel
from CacheRoute.core import TokenizerRegistry


"""
    输入一个用户问题，检验自动分词并提取模型信息的能力
    输入：Class Prompt
    输出：完整的class prompt以及读取的模型信息，以及预计要计算的时间
"""

if __name__ == "__main__":
    device_flops = 419
    device_type = "RTX5090"
    network_bw = 0.250
    mfu = 0.5
    cof = 0.7

    # 调度器预热tokenizer
    TokenizerRegistry.warmup_tokenizers("DeepseekV3")

    # 提取任务信息，用tokenizer分词器计算seq长度
    start = time.perf_counter()
    task = Prompt.extract_prompt_info(
        model="DeepseekV3",
        user_prompt="这有一个苹果，它又大又圆还汁水充足。",
    )
    end = time.perf_counter()
    print(task)
    time = (end - start) * 1000
    print(f"extract_task_info 耗时：{time:.4f} ms")



    # 读取任务的模型参数
    model_config = model_config.get_config_by_model(task.model)
    print(model_config)

    # 计算量估计
    layer_flops = MLAmodel.calc_mla_layer_flops(model_config, task)
    print(f"Layer Computation of {task.model} for {task.token_length} length question is: {layer_flops} TFLOPS ")

    prefill_flops = MLAmodel.calc_mla_prefill_flops(model_config, task)
    print(f"Prefill Computation of {task.model} for {task.token_length} length question is: {prefill_flops} TFLOPS ")

