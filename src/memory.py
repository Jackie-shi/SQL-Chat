"""Memory module, which is used to store chat history
"""

import os
from typing import Dict, List, Union, Set, Any, Tuple
import datetime

from pydantic import BaseModel, Field

from mysql import MySQLDatabase
from logger import logger


class Memory(BaseModel):
    """Base model for Memory
    """
    storage: Any = Field(description="Storage backend")

    def __init__(self, storage: Any):
        super().__init__(storage=storage)

    def save(self):
        pass

    def search(self):
        pass

class LongTermMemory(Memory):
    """Inherit from Memory, which is used to store the chat history per user
    storage: MySQL
    """
    def __init__(self):
        storage = MySQLDatabase()
        super().__init__(storage=storage)

    def save(self, content: Union[Dict[str, str], List[str]], chat_id: int) -> None:
        timestamp = int(datetime.datetime.now().timestamp())

        if isinstance(content, Dict):
            memory = f"Question: {content.get('Q', 'null')}\tAnswer: {content.get('A', 'null')}"
        elif isinstance(content, List):
            memory = "\n".join(content)
                
        self.storage.batch_insert(
            table="user_memory",
            res_list=[chat_id, memory, timestamp],
            col_list=["chat_id", "memory", "timestamp"],
            is_replace=False,
        )

        logger.info(f"User-{chat_id} chat history insert done.")

    def search(self, chat_id: int, top_k: int = 3) -> Union[List, None]:
        fetch_sql = f"SELECT memory, timestamp FROM user_memory WHERE chat_id={chat_id} ORDER BY timestamp DESC"
        flag, result = self.storage.fetch(sql=fetch_sql)
        if flag:
            memory_contents: List[str] = [item[0] for item in result]

            qa_pair: List[Tuple[str]] = []
            for memory in memory_contents:
                q, a = memory.strip().split('\t')
                qa_pair.append((q.strip(), a.strip()))
            return qa_pair[:top_k]
        else:
            return None
        

