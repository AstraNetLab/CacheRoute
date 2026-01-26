### 260126 大更新：重构scheduler，proxy和request部分的知识库维护部分，不再依赖本地yaml预设值。而是实现scheduler启动时抓取KDN服务器中的知识索引，构建自己的知识清单。

(1)KDN_server的/search/text支持按field回传，而不是每次都回传整个结构体<br>
(2)KDN_server支持/snapshot整个知识库状态用于scheduler更新<br>
(3)更新scheduler，摒弃之前的本地yaml构建方式，支持启动初始化从kdn进行snapshot抓取并构建知识清单。<br>
(4)更新knowledge_base，支持sha256至int64映射（注：Faiss是通过INT64检索，而KDN形成的是sha256的str表达格式，所以在snap后需要进行映射。）<br>
(5)优化scheduler_CLI，增强信息维护和交互命令行接口<br>
<img width="554" height="509" alt="image" src="https://github.com/user-attachments/assets/696145ea-83ef-4e4a-b575-d1e74175ef72" />

---
涉及修改文件:<br>
`kdn_server/text_db.py`<br>
`kdn_server/kdn_api.py`<br>
`scheduler/__init__.py`<br>
`scheduler/scheduler.py`<br>
`scheduler/kdn_client.py`<br>
`scheduler/scheduler_cli`<br>
`store/knowledge_base.py`<br>
`core/request.py`<br>
`proxy/proxy.py`<br>
`proxy/proxy.py`<br>

