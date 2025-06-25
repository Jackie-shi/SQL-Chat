from __future__ import annotations
import re
import os
from typing import List, Union, Any, Dict, Tuple, Optional, Set
import json
import time
import traceback
from collections import defaultdict

from pydantic import BaseModel, Field, model_validator, ConfigDict
from cachetools import cached, TTLCache
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage
)
from langchain_openai import ChatOpenAI

from utils import parse_by_pydantic, dag_post_process
from memory import LongTermMemory
from bases import BaseLLM, BaseTool
from tools import RAGTool, SQLGeneratorTool, RefineTool
from dag_scheduler import DAGScheduler, ThreadedDAGExecutor, AsyncDAGExecutor, TaskResult, TaskStatus
from globals import *
from prompt import prompts
from logger import logger


FINAL_ANSWER_ACTION = "Final Answer:"

class DAGStyleOutput(BaseModel):
    questions: str
    dag: str

class RewriteOutput(BaseModel):
    query: str = Field(description="The rewrited query")
    flag: bool = Field(description="Whether need to fetch from database")

class StraitAnswer(BaseModel):
    answer: str

class SQLAnswer(BaseModel):
    sql: str

class QuestionDAGLLM(BaseLLM):
    def run(self, query: str, **kwargs):
        chat_history: Union[None, List] = kwargs.get("chat_history", None)
        if not chat_history:
            history_qa = "None"
        else:
            history_qa = '\n'.join([f"{idx+1}. {item[0]}\t{item[1]}" for idx, item in enumerate(chat_history)])

        message = [
            SystemMessage(content=prompts.query_dag_prompt),
            HumanMessage(content=f"Historical Q&As:\n{history_qa}\nQuery: {query}")
        ]
        content = self.model.invoke(message).content
        try:
            # Parse the content as JSON format
            parsed_content: Dict = parse_by_pydantic(content, DAGStyleOutput)
            return DAGStyleOutput(**parsed_content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON content: {e}")
            # Return default values if parsing fails
            return DAGStyleOutput(questions="", dag="")
        except Exception as e:
            logger.error(f"Error processing content: {e}")
            return DAGStyleOutput(questions="", dag="")

class QuestionRewriteLLM(BaseLLM):
    def run(self, query: str):
        message = [
            SystemMessage(content=prompts.query_rewrite_prompt),
            HumanMessage(content=f"Query: {query}")
        ]
        content = self.model.invoke(message).content
        try:
            # Parse the content as JSON format
            parsed_content: Dict = parse_by_pydantic(content, RewriteOutput)
            return RewriteOutput(**parsed_content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON content: {e}")
            # Return default values if parsing fails
            return RewriteOutput(query=query, flag=False)
        except Exception as e:
            logger.error(f"Error processing content: {e}")
            return RewriteOutput(query=query, flag=False)


class StraitAnswerLLM(BaseLLM):
    def run(self, query):
        message = [
            SystemMessage(content=prompts.strait_answer_prompt),
            HumanMessage(content=f"Query: {query} ")
        ]
        content = self.model.invoke(message).content
        try:
            # Parse the content as JSON format
            parsed_content = parse_by_pydantic(content, StraitAnswer)
            return StraitAnswer(**parsed_content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON content: {e}")
            # Return default values if parsing fails
            return StraitAnswer(answer="")
        except Exception as e:
            logger.error(f"Error processing content: {e}")
            return StraitAnswer(answer="")


class SQLGenLLM(BaseLLM):
    def run(self, query, **kwargs):
        table_schema = kwargs.get("table_schema", "")
        formatted_prompt = prompts.sql_generation_prompt.format(table_schema=table_schema)

        message = [
            SystemMessage(content=formatted_prompt),
            HumanMessage(content=f"Query: {query} ")
        ]
        content = self.model.invoke(message).content
        try:
            # Parse the content as JSON format
            parsed_content = parse_by_pydantic(content, SQLAnswer)
            return SQLAnswer(**parsed_content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON content: {e}")
            # Return default values if parsing fails
            return SQLAnswer(sql="")
        except Exception as e:
            logger.error(f"Error processing content: {e}")
            return SQLAnswer(sql="")


class SQLChatAgent(BaseModel):
    """SQLChat Agent
    """
    model_zoo: Dict[str, Any] = Field(description="The language model sets")
    knowledge: Optional[Any] = Field(default=None, description="Knowledge base for the agent")
    
    question_dag_llm: Optional[QuestionDAGLLM] = Field(default=None, description="Question split into DAG LLM")
    question_classify_llm: Optional[QuestionRewriteLLM] = Field(default=None, description="Question classification LLM")
    strait_answer_llm: Optional[StraitAnswerLLM] = Field(default=None, description="Strait answer LLM")
    sql_answer_llm: Optional[SQLAnswer] = Field(default=None, description="Gen SQL LLM")
    long_term_memory: Optional[LongTermMemory] = Field(default=None, description="Long term memory")
    tool_set: Optional[List[BaseTool]] = Field(default=None, description="Tool sets")
    tool_descriptions: Optional[List[str]] = Field(default=None, description="Tool name: Tool description & The args info")
    tool2args: Optional[Dict[str, dict]] = Field(default=None, description="Map tool name to its callable function input args")
    tool2func: Optional[Dict[str, callable]] = Field(default=None, description="Map tool name to its callable function")

    def __init__(self, model_zoo: Dict[str, Any], knowledge: Optional[Any] = None):
        super().__init__(model_zoo=model_zoo, knowledge=knowledge)

    @model_validator(mode="after")
    def prepare(self) -> "SQLChatAgent":
        logger.info("Prepare LLMs for pipeline")
        self.question_dag_llm: QuestionDAGLLM = QuestionDAGLLM(self.model_zoo['gpt'])
        self.question_classify_llm: QuestionRewriteLLM = QuestionRewriteLLM(self.model_zoo['gpt'])
        self.strait_answer_llm: StraitAnswerLLM = StraitAnswerLLM(self.model_zoo['gpt'])
        self.sql_answer_llm: SQLAnswer = SQLAnswer(self.model_zoo['gpt'])

        self._initialize_memory()
        self._initialize_tools()
        return self

    def _initialize_memory(self) -> None:
        logger.info("Start initializing memory.")
        self.long_term_memory: LongTermMemory = LongTermMemory()
        
    def _initialize_tools(self) -> None:
        logger.info("Start initializing tools.")
        self.tool_set = [
            RAGTool(),
            RefineTool(),
            SQLGeneratorTool()
        ]
        self.tool_descriptions: List[str] = []
        self.tool2args: Dict[str, dict] = {}
        # Get tools description and tools name
        for tool in self.tool_set:
            args_json: Dict = tool.args_schema.model_json_schema()
            input_args: Dict[Dict[str, str]] = defaultdict(lambda: defaultdict())
            for attr, items in args_json["properties"].items():
                input_args[attr]["type"] = items["type"]
            self.tool_descriptions.append(
                f"{tool.name}: {tool.description}. The args: {json.dumps(input_args)}"
            )
            self.tool2args[tool.name] = input_args

        # Get tool2func
        self.tool2func = {tool.name: tool.run for tool in self.tool_set}

    # execute a single query and got the answer
    def _dql_needed_execute(self, query: str, external_info: Union[str, None]) -> Tuple[bool, str]:
        def extract_input_args(tool_input: str) -> Dict:
            """Extract input args from the json style string
            """
            try:
                if not tool_input:
                    return {}
                # Try to parse as JSON first
                try:
                    parsed_input = json.loads(tool_input)
                    if isinstance(parsed_input, dict):
                        return parsed_input
                except json.JSONDecodeError:
                    pass
                # Use regex to extract all key-value pairs
                result = {}
                
                # Pattern to match "key": "value" or 'key': 'value' or key: "value" or key: 'value'
                pattern = r'["\']?(\w+)["\']?\s*:\s*["\']([^"\']*)["\']'
                matches = re.findall(pattern, tool_input)
                
                for key, value in matches:
                    result[key] = value
                
                return result       
            except Exception as e:
                logger.error(f"Error extracting input args: {e}")
                return {}
        def extract_action_and_input(text: str) -> Tuple[str, Dict]:
            pattern = r"Action\s*\d*\s*:[\s]*(.*?)[\s]*Action\s*\d*\s*Input\s*\d*\s*:[\s]*(.*)"
            action_match = re.search(pattern, text, re.DOTALL)
            if action_match:
                action = action_match.group(1)
                clean_action = action.strip().split('*').strip()

                action_input = action_match.group(2).strip()
                tool_input = action_input.strip(" ").strip('"')
                tool_input = tool_input.replace('"""', '"')
                tool_input = tool_input.replace("'''", '"')
                tool_input = extract_input_args(tool_input)
            else:
                clean_action, tool_input = "", {}
            return clean_action, tool_input
 
        user_prompt = f'Question: {query}'
        model = self.model_zoo["gpt"]
        messages = [
            SystemMessage(content=prompts.sql_react_prompt.format(
                tools="\n".join(self.tool_descriptions),
                tool_names=",".join([tool.name for tool in self.tool_set]),
                external_info=external_info if external_info else "None"
            )),
            HumanMessage(content=user_prompt)
        ]

        max_check_time, max_rag_time = 3, 5
        react_round = 0
        # record the rag results, and exclude these tables during the next retrival
        rag_table_record: List[str] = []
        logger.info(user_prompt)

        while True:
            if react_round >= max_check_time+max_rag_time:
                return False, ''
            
            react_round += 1

            content = model.invoke(messages).content # AI answer
            
            messages.append(AIMessage(content=content))
            logger.info(f"==========answer============\n{content}")

            # Final answer
            if FINAL_ANSWER_ACTION in content:
                # Extract final answer from the content
                final_answer_pattern = r"Final Answer:\s*(.*)"
                final_answer_match = re.search(final_answer_pattern, content, re.DOTALL)
                if final_answer_match:
                    final_answer = final_answer_match.group(1).strip()
                    return True, final_answer
                else:
                    # Parse error. Let LLM re-try.
                    observation = f"Invalid parse. You need to give your final answer using the format: \"Final Answer: \"."
                    logger.info(f"Observation: {observation}")
                    messages.append(HumanMessage(content=f"Observation: {observation}"))
                    continue
            
            action, action_input = extract_action_and_input(content)

            if action not in [tool.name for tool in self.tool_set]:
                # Tool not in our tool_set. Let LLM re-try.
                observation = f"Invalid tool name. The tool you use must be in {','.join([tool.name for tool in self.tool_set])}."
                logger.info(f"Observation: {observation}")
                messages.append(HumanMessage(content=f"Observation: {observation}"))
                continue
            
            tool_func: callable = self.tool2func[action]
            tool_args_schema: Dict = self.tool2args[action]
            real_func_args = {}

            for key, items in tool_args_schema.items():
                if key in action_input:
                    arg_type: str = items['type']
                    value = action_input[key]
                    if arg_type == "string":
                        real_func_args[key] = str(value)
                    elif arg_type == "integer":
                        real_func_args[key] = int(value)
                    elif arg_type == "number":
                        real_func_args[key] = float(value)
                    elif arg_type == "boolean":
                        real_func_args[key] = True if value.lower() == 'true' else False
                else:
                    break
            if action == "Retrieve_table":
                real_func_args["table_list_record"] = rag_table_record
                
            if len(real_func_args) != len(tool_args_schema):
                observation = f"Invalid input args for {action}. The valid input args is {json.dumps(tool_args_schema)}."
            else:
                observation = tool_func(**real_func_args)

            logger.info(f"Observation: {observation}")
            messages.append(HumanMessage(content=f"Observation: {observation}"))

    def _single_query_kickoff(self, query: str, external_info: Union[str, None]):
        rewrite_output: RewriteOutput = self.question_classify_llm.run(query=query)
        if not rewrite_output.flag:
            # Answer the query straitforward
            try:
                strait_answer: StraitAnswer = self.strait_answer_llm.run(query)
            except Exception as e:
                logger.info(traceback.format_exc())
                strait_answer = StraitAnswer(answer="")
            finally:
                answer = strait_answer.answer
        else:
            rewrite_query = rewrite_output.query
            try:
                flag, result = self._dql_needed_execute(rewrite_query, external_info=external_info)
            except Exception as e:
                logger.info(traceback.format_exc())
            
            if flag:
                answer = f"{result}"
            else:
                answer = "I'm so sorry that I can't answer your question based on the data I have currently. If you have any other internet related questions, please feel free to ask!"
        
        logger.info(answer)
        logger.info('\n\n<=============== Single ================>\n\n')
        return answer

    def _format_dag_results(self, results: Dict[int, TaskResult], idx2question: Dict[int, str]) -> str:
        """格式化DAG执行结果"""
        answer_parts = []
        
        # 按任务ID排序输出结果
        for task_id in sorted(idx2question.keys()):
            question = idx2question[task_id]
            
            if task_id in results:
                result = results[task_id]
                if result.status == TaskStatus.COMPLETED:
                    answer_parts.append(f"Q{task_id}: {question}")
                    answer_parts.append(f"A{task_id}: {result.answer}")
                else:
                    answer_parts.append(f"Q{task_id}: {question}")
                    answer_parts.append(f"A{task_id}: [FAILED] {result.error or 'Unknown error'}")
            else:
                answer_parts.append(f"Q{task_id}: {question}")
                answer_parts.append(f"A{task_id}: [NOT EXECUTED]")
            
            answer_parts.append("")  # 空行分隔
    
        return "\n".join(answer_parts)

    def execute_dag_threaded(self, idx2question: Dict[int, str], node_dependency: Dict[int, Set[int]]) -> str:
        """多线程执行DAG任务"""
        # 创建调度器
        scheduler = DAGScheduler(max_concurrent_tasks=10)
        scheduler.add_tasks(idx2question, node_dependency)
        
        # 创建执行器
        executor = ThreadedDAGExecutor(scheduler, self._single_query_kickoff)
        
        # 执行DAG
        results = executor.execute_dag()
        
        # 整合结果
        return self._format_dag_results(results, idx2question)

    def kickoff(self, query: str, chat_id: int):
        """The workflow of the project
        """
        # Obtain the chat history for query filling
        chat_history: Union[List[Tuple[str, str]], None] = self.long_term_memory.search(chat_id=chat_id)
        question_dag_output: DAGStyleOutput = self.question_dag_llm.run(query=query, chat_history=chat_history)
        idx2question, node_dependency = dag_post_process(
            questions=question_dag_output.questions,
            dependencies=question_dag_output.dag
        )

        if len(idx2question) == 1:
            single_question = list(idx2question.values())[0]
            answer = self._single_query_kickoff(single_question, external_info=None)
        else:
            answer = self.execute_dag_threaded(idx2question, node_dependency)
        
        logger.info(answer)
        logger.info('\n\n<=============== DAG Execution Complete ================>\n\n')
        return answer 


        
