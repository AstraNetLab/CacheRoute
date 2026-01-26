### 260126 大更新：重构scheduler，proxy和request部分的知识库维护部分，不再依赖本地yaml预设值。而是实现scheduler启动时抓取KDN服务器中的知识索引，构建自己的知识清单。
---
具体优化内容：<br>
---
(1)KDN_server的/search/text支持按field回传，而不是每次都回传整个结构体<br>
(2)KDN_server支持/snapshot整个知识库状态用于scheduler更新<br>
(3)更新scheduler，摒弃之前的本地yaml构建方式，支持启动初始化从kdn进行snapshot抓取并构建知识清单。<br>
---
涉及修改文件:<br>
`kdn_server/text_db.py`<br>
`kdn_server/kdn_api.py`<br>
