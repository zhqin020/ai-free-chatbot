# make_chat_request_payload 代码生成模板

## 1. 生成函数模板

```python
def make_chat_request_payload(document_text: str, msg_id_prefix: str):
    """
    自动生成的请求 payload 构造函数。
    :param document_text: 文本内容
    :param msg_id_prefix: 消息 ID 前缀
    :return: dict
    """
    if not hasattr(make_chat_request_payload, "count"):
        make_chat_request_payload.count = 1
    make_chat_request_payload.count += 1

    ret_json = '''{ret_json}'''
    prompt = f"""{prompt}"""
    return {
        "external_id": f"{msg_id_prefix}-{{int(time.time())}}-{{make_chat_request_payload.count}}",
        "prompt": prompt,
        "document_text": document_text
    }
```

- 其中 {ret_json}、{prompt} 由前端动态填充。
- 支持多行字符串与嵌套结构。

## 2. 生成逻辑建议
- 前端将 JSON 模板转为格式化字符串，填入 ret_json。
- prompt 区域直接填入用户输入。
- 代码区实时渲染上述模板。

---

如需支持更多参数或自定义字段，可扩展模板参数。