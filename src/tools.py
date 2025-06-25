import re
from typing import List, Dict, Union, Any
from pydantic import BaseModel, Field

import concurrent

from bases import BaseTool
from knn_icl import KNNSchema
from sql_react_prune import SQLAnswer
from mysql import MySQLDatabase

class RAGTool(BaseTool):
    name: str = "Retrieve_table"
    description: str = "Retrive the table schema informations for future SQL generation, based on the user's query. Use this tool when you need informations to generate correct SQL."
    
    def __init__(self):
        super().__init__(
            name=self.name,
            description=self.description
        )
        self.knn_schema = KNNSchema()
    
    def run(self, query: str, table_list_record: List[str]):
        """Doing RAG from our Vector Databse
        """
        observation, table_list = self.knn_schema.create_structured_table_schema(query, exclude_list=table_list_record, k=3)
        table_list_record = list(set(table_list_record) | set(table_list))
        return  observation
        

class RefineTool(BaseTool):
    name: str = "Refine_sql"
    description: str = "Recheck the SQL you generated. If the execution result of the SQL has Error, the SQL is needed for further correction. Use this tool when you need to check the correctness of a SQL."

    def run(self, sql: str):
        """Execute the sql and get the feedback from our DB
        """
        SQL_TIMEOUT = 5
        mysql = MySQLDatabase(in_product=True)
        if 'create' in sql.lower() or 'delete' in sql.lower() or 'drop' in sql.lower() or 'insert' in sql.lower():
            return 'Execute fail. You can\'t modify these tables! Your wrong SQL is \"{sql}\".'
        
        # Limit the number of returns
        if 'limit' not in sql.lower():
            sql = sql.rstrip(';')
            sql += ' LIMIT 5;'

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(mysql.fetch, sql)
            try:
                result = future.result(timeout=SQL_TIMEOUT)
            except concurrent.futures.TimeoutError:
                return 'Execute timeout. You should optimize the SQL: "{sql}".'

        if result[0]:
            final_result = result[1]
            s = f'Execute success. The SQL is correct. The result is {final_result}.'
        else:
            pattern = r"[\s\S]*\([\s\S]*,([\s\S]*)\)"
            error_info = result[1]
            m = re.search(pattern, error_info)
            if m:
                s = f'Execute fail. The Error is {m.group(1).strip()}. Your wrong SQL is \"{sql}\", you need to modify it.'
        return s


class SQLGeneratorTool(BaseTool):
    name: str = "SQL_generator"
    description: str = "Generate SQL query based on user's natural language question and table schema information. Use this tool when you need to convert a natural language question into a SQL query."
    def __init__(self, sql_gen_llm: Any):
        super().__init__(
            name=self.name,
            description=self.description,
            tool_llm=sql_gen_llm
        )
    
    def run(self, question: str, table_schema: str):
        """Generate SQL based on question and table schema
        
        Args:
            question: User's natural language question
            table_schema: Database table schema information
            **kwargs: Additional parameters like constraints, examples, etc.
        
        Returns:
            Generated SQL query string
        """
                
        sql_answer: SQLAnswer = self.tool_llm.run(query=question, table_schema=table_schema)
        return sql_answer.sql