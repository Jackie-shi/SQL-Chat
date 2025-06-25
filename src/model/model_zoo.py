from __future__ import annotations
from typing import Any, Union, Dict

from langchain_openai import ChatOpenAI

API_KEY= '<your api key>'

class ModelZoo:
    
    def get_model_zoo(self) -> Dict[str, Any]:
        return {
            'gpt': self.gen_gpt()
        }
    
    def gen_gpt(self, model_name: Union[str, None] = None):
        if not model_name:
            model = ChatOpenAI(model="gpt-4o", openai_api_key=API_KEY, openai_api_base='https://xxx.xx', temperature=0)
        else:
            model = ChatOpenAI(model=model_name, openai_api_key=API_KEY, openai_api_base='https://xxx.xx', temperature=0)
        return model
