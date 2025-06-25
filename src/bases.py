from typing import Any, Union, Optional
from pydantic import BaseModel, Field, model_validator

from logger import logger

import inspect
from langchain_openai import ChatOpenAI


class BaseLLM(BaseModel):
    model: Any = Field(description="The language model to use")

    def __init__(self, model: Any):
       super().__init__(model=model)
    
    def run(self, query: str, **kwargs):
        """Run the LLM
        """

class BaseTool(BaseModel):
    name: str = Field(description="The tool name")
    description: str = Field(description="The info about the functionality of the tool and when should be used")
    tool_llm: Optional[Any] = Field(description="The LLm will be used in the tool")
    args_schema: Optional[BaseModel] = Field(description="The input args of the tool")

    def __init__(self, name: str, description: str, tool_llm: Optional[Any] = None):
        super().__init__(name=name, description=description, tool_llm=tool_llm)
    
    @model_validator(mode="after")
    def _get_tool_args(self):
        """Generate tool input args from self.run
        """
        class_name = f"{self.__class__.__name__}Schema"
        logger.info(f"Creating schema for {class_name}")
        
        self.args_schema = type(
            class_name,
            (BaseModel,),
            {
                "__annotations__": {
                    k: v
                    for k, v in self.run.__annotations__.items()
                    if k != "return"
                },
            },
        )

        return self

    def run(self, **kwargs):
        """Execute the tool
        """