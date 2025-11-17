# 定义任务和任务批次的信息结构

from dataclasses import dataclass
from CacheRoute.core.tokenizer_registry import estimate_tokens
from typing import Dict, Any

"""
定义CacheRoute整体系统的交互数据结构体 -> Class Request
    
    Class Request:
      |  Request_ID:用户任务的唯一标识ID
      |__Request_type：请求类型，如request，control，update等
      |  
      |__Class Prompt: 记录用户问题的基本信息，如具体问题，模型类型，问题长度等
      |   |  model
      |   |  user_prompt
      |   |__token_length
      |
      |__Class Service： 映射用户问题的服务需求，如是否支持PD分离，是否支持知识注入，TTFT，E2E和TPOT的SLO需求
      |   |  Enable_PD_Disaggregation
      |   |  Enable_kv_know_injection
      |   |  Enable_compress_injection
      |   |  Knowledge_block_num
      |   |  Knowledge_List
      |   |  Knowledge_length
      |   |  SLO_TTFT
      |   |  SLO_E2E
      |   |__SLO_TPOT
      |  
      |__Class Task： 记录调度相关的任务信息，如KDN知识服务器的IP地址，PD池代理的IP地址，端口号
          |  User_addr
          |  KDN_server_addr
          |  default_know_addr
          |  P_proxy_addr
          |  D_proxy_addr
          |  P_proxy_port
          |__D_proxy_port
"""


@dataclass
class Prompt:
    """
        定义用户问题的基本信息
            model<任务模型，str>
            user_prompt<用户问题，str>
            token_length<问题的token长度>
            bs<任务组的batch_size，通常情况下默认1>
    """
    model: str
    user_prompt: str
    token_length: int = 0
    bs: int = 1
    # model_type: str = ""


    @classmethod
    def extract_prompt_info(cls, model: str, user_prompt: str) -> "Prompt":
        """
            根据 user_prompt 自动计算 token_length，并返回 Task 实例。
            model<任务模型，str>
            user_prompt<用户问题，str>

            输入：user_prompt
            输出：class prompt
        """
        seq_length = estimate_tokens(user_prompt, model)
        print(f"Process: get task seq_length complete, seq_length={seq_length}")

        return cls(
            model=model,
            # model_type=cls.model_type,
            user_prompt=user_prompt,
            token_length=seq_length,
            bs=cls.bs,
        )



@dataclass
class Service:
    """
        定义问题服务的SLO基本信息，通过用户IP地址映射具体服务等级，支持映射模块出于安全、个性化等方面的扩展
            Enable_PD_Disaggregation<是否允许问题进行PD分离处理，默认为True>
            Enable_kv_know_injection<是否允许调用远端知识的KVCache，默认为True>
            Enable_compress_injection<是都允许进行KVCache的有损压缩，默认为True>
            Knowledge_block_num<任务注入知识块的top数量，默认为3>
            Knowledge_List<知识块列表，里面的元素是Knowledge_ID,表征一个具体的知识块>
            Knowledge_length<任务注入知识库的token长度，默认为0>
            SLO_TTFT<任务组的TTFT SLO需求，即问题开始推理至产生提一个token所需要的时间，默认2000ms>
            SLO_E2E<任务从开始Prefill到结束Decode所需的完整时间，ms>
            SLO_TPOT<任务组的TPOT SLO需求，即自回归推理阶段平均生成默认20ms>
    """
    Enable_PD_Disaggregation: bool = True
    Enable_kv_know_injection: bool = True
    Enable_compress_injection: bool = True
    Knowledge_block_num: int = 3
    Knowledge_length: int = 0
    SLO_TTFT: int = 2000
    SLO_E2E: int = 3000
    SLO_TPOT: int = 20

    # TODO：在data文件夹内新增一个SLO的映射yaml，编写一个classmethod来根据user_addr映射出具体的SLO指标
    @classmethod
    def mapping_slo_info(cls, user_addr: str) -> Dict[str, Any]:
        if user_addr.startswith("10.0."):
            return {
                "Enable_PD_Disaggregation": False,
                "SLO_TTFT": 200,
                "SLO_TPOT": 5
            }
        elif user_addr.startswith("192.168."):
            return {
                "Enable_PD_Disaggregation": False,
                "SLO_TTFT": 1000,
                "SLO_TPOT": 15
            }
        else:
            return {
                "Enable_PD_Disaggregation": True,
                "SLO_TTFT": 2000,
                "SLO_TPOT": 20
            }

    # TODO:输入user_prompt,输出所需知识的块数量，知识块ID，以及整体长度



@dataclass
class Task:
    """
        定义任务调度基本信息
            User_addr：用户的IP地址，表征用户身份
            KDN_server_addr<任务根据知识需求挑选出的最合适的KDN服务器地址>
            default_know_addr<默认的知识注入服务器，采用文本的注入方式>
            P_proxy_addr<处理任务的P池代理IP地址，默认为本地换回地址>
            P_proxy_port<处理任务的P池代理端口号，默认为8080>
            D_proxy_addr<处理任务的D池代理IP地址，默认为本地换回地址>
            D_proxy_port<处理任务的D池代理端口号，默认为8080>
    """
    User_addr: str
    P_proxy_addr: str = "127.0.0.1"
    P_proxy_port: int = 8080
    D_proxy_addr: str = "127.0.0.1"
    D_proxy_port: int = 8080

    # TODO：调度算法，输出PD池地址。
    # @classmethod
    # def Scheduler(cls) -> Dict[str, Any]:

    # TODO：LLM系统和知识服务器的配对选择，输入知识需求，输出最佳服务器和最佳LLM系统
    # @classmethod
    # def knowledge_oriented_task_routing(cls) -> Dict[str, Any]:


@dataclass
class Request:
    """
        主结构体，用于描述任务的所有需求
            Request_ID：用户任务的唯一标识ID
            Request_type：请求类型，如request，control，update等
            Prompt<用于处理用户内容的相关信息>
            Service<用于处理用户服务的相关信息>
            Task<用于记录调度任务时的相关信息>
    """
    Request_ID: int
    Request_type: str
    Prompt: Prompt
    Service: Service
    Task: Task

    @classmethod
    def build_request(cls, raw_data: Dict, user_addr: str) -> "Request":
        """
            将原始用户请求信息转换为完整的 Request 对象。
            用户的raw_data 包含 model + user_prompt
        """

        model = raw_data["model"]
        user_prompt = raw_data["user_prompt"]
        request_type = "request"
        # TODO：TaskID的更新变化，对于收到的每个新的任务ID号加1，直到超过65535后回到1从新编号。编号的状态保持需要在调度器做
        request_id = 1

        prompt_obj = Prompt.extract_prompt_info(model, user_prompt)

        slo_mapping = Service.mapping_slo_info(user_addr)
        service_obj = Service(
            Enable_PD_Disaggregation = slo_mapping["Enable_PD_Disaggregation"],
            SLO_TTFT = slo_mapping["SLO_TTFT"],
            SLO_TPOT = slo_mapping["SLO_TPOT"],
        )
        task_obj = Task(
            User_addr=user_addr
        )

        request_obj = Request(
            Request_type=request_type,
            Request_ID=request_id,
            Prompt=prompt_obj,
            Service=service_obj,
            Task=task_obj
        )

        return request_obj

    # TODO:request类的JSON格式封装与解封装传输

    def __repr__(self):
        return (
            f"Request(\n"
            f"  Request_ID={self.Request_ID},\n"
            f"  Request_type={self.Request_type},\n"
            f"--------Prompt--------\n"
            f"  model={self.Prompt.model},\n"
            f"  user_prompt={self.Prompt.user_prompt},\n"
            f"  token_length={self.Prompt.token_length},\n"
            f"--------Service--------\n"
            f"  Enable_PD={self.Service.Enable_PD_Disaggregation},\n"
            f"  SLO_TTFT(ms)={self.Service.SLO_TTFT},\n"
            f"  SLO_E2E(ms)={self.Service.SLO_E2E},\n"
            f"  SLO_TPOT(ms)={self.Service.SLO_TPOT},\n"
            f"--------Task--------\n"
            f"  User_addr={self.Task.User_addr},\n"
            f"  P_proxy_addr={self.Task.P_proxy_addr},\n"
            f"  D_proxy_addr={self.Task.D_proxy_addr},\n"
            f"  P_proxy_port={self.Task.P_proxy_port},\n"
            f"  D_proxy_port={self.Task.D_proxy_port},\n"
            f")"
        )