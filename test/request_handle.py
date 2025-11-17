import time
from CacheRoute.model import model_config
from CacheRoute.core import Request
from CacheRoute.core import TokenizerRegistry


"""
    输入一个用户问题，检验构建request结构体的能力
    输入：用户问题
    输出：完整的class request
"""

if __name__ == "__main__":
    # 调度器预热tokenizer
    TokenizerRegistry.warmup_tokenizers("DeepseekV3")

    # 提取任务信息，用tokenizer分词器计算seq长度
    start = time.perf_counter()
    raw_data = {
        "model": "DeepseekV3",
        "user_prompt": "请根据下面的需求为我生成一个高性能的调度策略，并解释其中的关键步骤。"
    }
    request = Request.build_request(raw_data,"192.168.0.167")
    end = time.perf_counter()
    print(request)
    time = (end - start) * 1000
    print(f"build_request_info 耗时：{time:.4f} ms")

    # 读取任务的模型参数
    # model_config = model_config.get_config_by_model(request.Prompt.model)
    # print(model_config)