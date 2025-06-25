from __future__ import annotations
from typing import Any, Union, Dict

from langchain_openai import ChatOpenAI

API_KEY= 'sk-78U3YlBuZGAIIX7eB4Ed08F86f4f4817B70617E0E2D8B2Cc'

class ModelZoo:
    
    def get_model_zoo(self) -> Dict[str, Any]:
        return {
            'gpt': self.gen_gpt()
        }
    
    def gen_gpt(self, model_name: Union[str, None] = None):
        if not model_name:
            model = ChatOpenAI(model="gpt-4o", openai_api_key=API_KEY, openai_api_base='https://aiproxy.lmzgc.cn:8080/v1', temperature=0)
        else:
            model = ChatOpenAI(model=model_name, openai_api_key=API_KEY, openai_api_base='https://aiproxy.lmzgc.cn:8080/v1', temperature=0)
        return model