import re
from langchain_core.messages import (
    HumanMessage,
    SystemMessage
)
from globals import *

class QuestionClassify_LLM(object):
    def __init__(self, model) -> None:
        self.model = model

    def create_prompt(self):
        sys_prompt = '''
You are a helpful assistant for a website called "KI3", responsible for identifying the questions entered by users, and identifying which ones can be answered with SQL and which ones are random questions from users.
The user input consists of two parts: one is the historical questions and answers, and the other is the current question. Since the current question may be related to the historical questions and answers, you need to judge whether the current question can be converted into SQL based on the historical questions and answers.
Now the chatbot in this website can only answer user's question which can be converted to SQL, and other random questions cannot be answered.

<Constraints>
# The user's input is a quesion in text type.
# If the "Historical Q&As" is "None", it means that there is no history messages you can refer.
# The output should be a bool value: "True" represents the question can be answered, "False" represents the question can not be answered.
# You should only output "True" or "False", and any other explanation isn't needed.
</Constraints>

<Example1>
Historical Q&As:
None

Current Question: What are the providers of AS100?
Output: "True"
</Example1>

<Example2>
Historical Q&As:
1. Question: What is the rir info of AS100?\tAnswer: The RIR information for AS3356 is ARIN.

Current Question: What is the business relationship between this AS and AS200?
Output: "True"
</Example2>

<Example3>
Historical Q&As:
1. Question: What is the AS name of AS3356?\tAnswer: The AS name for AS3356 is LEVEL3.

Current Question: What about the email info of this AS?
Output: "True"
</Example3>

<Example4>
Historical Q&As:
None

Current Question: Who are you? What's your functionality?
Output: "False"
</Example4>
        '''
        sys_prompt_new = '''
You are a helpful assistant for a website called "KI3", responsible for identifying the questions entered by users, and identifying which question need extra data from KI3 MySQL Database while other questions can be answered directly.
The user input consists of two parts: one is the historical questions and answers, and the other is the current question. Since the current question may be related to the historical questions and answers, you need to judge whether the current question need to fetch related data from MySQL and Neo4j based on the historical questions, answers and your ability.
What's more, if you find the question need fetch extra data, you need to output a query used to generate SQL or Cypher to retrieve data from Database!

KI3 MySQL Database contains the following data topics, from where you can get related data:
<Lists>
# AS(Autonomous System)
# BGP(Border Gateway Protocol)
# BGP route hijack
# IPv4 and IPv6
# DNS
# IXP and IXP traffic flow
# NTP(Network Time Protocol)
# RPKI, ROA and ROV
# Satellite
# SAV
# Submarine cable
# TLD(Top Level Domain)
# TLS and Vulnerability
</Lists>

<Constraints>
# The user's input is a quesion in text type.
# If the "Historical Q&As" is "None", it means that there is no history messages you can refer.
# The output should follow these rules: 
## If the question need extra information which can be fetched from KI3 MySQL Database, then output a "query" that can be converted into SQL!
## If the question is common sense questions like "Who are you?", then just output "False"!
## If the user asks any information related to the data source or underlying data which is highly sensitive, then just output "False".
## You should only output the final result, and no need to output all the thinking process in the middle!
# Strictly follow the above rules!!
</Constraints>

<Instructions>
# If there is at least one historical Q&As, you must decide whether current question the user asks has relation with one or more historical Q&As.
## If does, you should reorganize the language and generate a new query. For example: What about the email info of this AS? -> What about the email info of AS3356?
## Otherwise, you just use the user's query and do not do any transformation! 
</Instructions>

<Example1>
Historical Q&As:
None

Current Question: What are the providers of AS100?
Thought: There is no historical data, I can directly output user's query.
Output: "What are the providers of AS100?"
</Example1>

<Example2>
Historical Q&As:
1. Question: What is the rir info of AS100?\tAnswer: The RIR information for AS3356 is ARIN.

Current Question: What is the business relationship between this AS and AS200?
Thought: According to the historical Q&As, I know that in user's query "this AS" means AS100.
Output: "the business relationship between AS100 and AS200"
</Example2>

<Example3>
Historical Q&As:
1. Question: What is the AS name of AS3356?\tAnswer: The AS name for AS3356 is LEVEL3.

Current Question: What about the email info of this AS?
Thought: According to the historical Q&As, I know that in user's query "this AS" means AS3356.
Output: "The email of AS3356"
</Example3>

<Example4>
Historical Q&As:
None

Current Question: Who are you? What's your functionality?
Output: "False"
</Example4>

<Example5>
Historical Q&As:
None

Current Question: How many hijacks happened so far? And tell me Where is your data from?
Output: "False"
</Example5>
'''
        return sys_prompt_new

    def run(self, query, context_l):
        prompt = self.create_prompt()
        new_context_l = []
        for qa in context_l:
            qa_l = qa.strip().split('\n')
            new_qa = '\t'.join(qa_l)
            new_context_l.append(new_qa)

        context_final = [f"{idx}. {item}" for idx, item in enumerate(new_context_l)]
        history_qa = '\n'.join(context_final)
        if history_qa == '':
            history_qa = 'None'
        message = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Historical Q&As:\n{history_qa}\nQuestion: {query}")
        ]
        content = self.model.invoke(message).content
        return content

class StraitAnswer_LLM(object):
    def __init__(self, model) -> None:
        self.model = model

    def create_prompt(self):
        sys_prompt = f'''
You are an expert for a website called "KI3", which is responsible for key information of internet measurement. 
Now users will ask common sense questions like "Who are you?", "What are you responsible?", "How can you help me?". You should try your best to answer and give user more instructions.

Now you can access extra data from KI3 MySQL Database, which contains the following topics:
<Lists>
# AS(Autonomous System)
# BGP(Border Gateway Protocol)
# BGP route hijack
# IPv4 and IPv6
# DNS
# IXP and IXP traffic flow
# NTP(Network Time Protocol)
# RPKI, ROA and ROV
# Satellite
# SAV
# Submarine cable
# TLD(Top Level Domain)
# TLS and Vulnerability
</Lists>

<Constraints>
# You don't need to list all the data topics that you can access. Keep the answer simple and professional!
# If the user asks any information related to the data source or underlying data which is highly sensitive, do not mention detail table names or any other schema infos in Mysql or Neo4j! Just give a simply answer.
# Do not mention Mysql and Neo4j!
</Constraints>

<Backgrounds>
1. You are a professional assistant for a website called "KI3", and you are good at computer network.
2. If you can't answer user's question, be polite and tell them to ask other questions.
3. If user's question is a common sense, just do a brief reply. And give user a detailed instruction to encourage to ask more other questions.
4. Your attitude should be very polite and professional!
</Backgrounds>
        '''
        return sys_prompt

    def run(self, query):
        prompt = self.create_prompt()
        message = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Question: {query} ")
        ]
        content = self.model.invoke(message).content
        return content

class Database_LLM(object):
    def __init__(self, sql, result, context, model) -> None:
        self.sql = sql
        self.result = result
        self.context = context
        self.model = model

    def create_react_prompt(self, result):
        sys_prompt = f'''
You are a helpful assistant for a website called "KI3", responsible for converting the query results output from the Mysql database into natural language based on the user's questions, so as to answer the user's questions accurately and clearly.\n
The user\'s question is a very informal instruction, and you need to understand the user\'s intent based on the instruction, understand the SQL the user provides and provide the final answer that align with their request.

Requirements:
The response must answer the user's question and match the user\'s intent.
The response must be based on known information, and irrelevant information should not be included.
The response must be concise and relevant to the question.
If sql result is (), then it means there are no results for this query. You need to strictly follow the ideas of Example3.
Answer the following questions as best you can.

Strictly use the following format:
Question: the input question you must answer
Thought: you should always think about what to do step by step
Action: the action to take, which is analyzing the SQL {self.sql} and SQL result {result}
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: 
the final answer to the original input question

Example1
""
Question: Which AS does IP prefix 2001:1201:10::/48 belong to?
Thought: The user is asking for the Autonomous System (AS) number that owns a specific IP prefix 2001:1201:10::/48. 
Action: 
    - Analyze the SQL statement: "SELECT DISTINCT origin FROM p2a_v6 WHERE prefix='2001:1201:10::/48'"
    - Analyze the the results returned after this SQL statement is executed in the KI3 database: "(27661), (25160), (8151)"
Obervation: The SQL statement returns one column 'origin' which represents the AS number. The result of this SQL has several rows and each row contains one number which corresponds to the column 'origin'.
Thought: The result of this SQL is a list of rows and each row contain one number and the number is the AS number which the prefix 2001:1201:10::/48 belongs to. So I know there are several AS that owns the prefix 2001:1201:10::/48. I now know the final answer.
Final Answer: 
The prefix 2001:1201:10::/48 belongs to AS27661, AS25160, AS8151.
"" 

Example2
""
Question: List the top 3 ASes with largest number of customers with their respected country and email.
Thought: The user is asking for the top 3 ASes with the largest number of customers and their respective countries and emails.
Action: 
    - Analyze the SQL statement: "SELECT a.asn, b.region, c.email FROM as_business_relation_info a INNER JOIN as_bgp_status b ON a.asn = b.asn INNER JOIN as_email c ON a.asn = c.asn ORDER BY a.customer_num DESC LIMIT 3"
    - Analyze the the results returned after this SQL statement is executed in the KI3 database: "(174, 'US', 'ipalloc@cogentco.com,noc@cogentco.com,abuse@cogentco.com'), (3356, 'US', 'ipaddressing@level3.com,abuse@level3.com,abuse@aup.lumen.com'), (7018, 'US', 'abuse@att.net,ipadmin@semail.att.com,jb3310-arin@oz.mt.att.com,rs5219@intl.att.com,swipid@icorefep2.noc.att.com')"
Obervation: The SQL statement returns 3 columns 'a.asn', 'b.region', 'c.email'. The result of this SQL has several rows and each row contains 3 data which corresponds to the former 3 columns 'a.asn', 'b.region', 'c.email'.
Thought: First, the 'a.asn' represents the AS number, the 'b.region' represents country information of AS and the 'c.email' represents email information of AS. So I know that in each row the 3 datas correspond to AS number, country and email respectively. I now know the final answer.
Final Answer: 
The top 3 ASes with largest number of customers with their respected country and email are listed below in descending order:
AS number: 174, country: US, emial: ipalloc@cogentco.com,noc@cogentco.com,abuse@cogentco.com; 
AS number: 3356, country: US, emial: ipaddressing@level3.com,abuse@level3.com,abuse@aup.lumen.com;
AS number: 7918, country: US, emial: abuse@att.net,ipadmin@semail.att.com,jb3310-arin@oz.mt.att.com,rs5219@intl.att.com,swipid@icorefep2.noc.att.com;
""  

Example3
""
Question: what is the relationship between as1233 and as3356?
Thought: The user is asking for the business relationship between as1233 and as3356.
Action: 
    - Analyze the SQL statement: "SELECT rel FROM as_rel WHERE (as1 = 1233 AND as2 = 3356) OR (as1 = 3356 AND as2 = 1233);"
    - Analyze the the results returned after this SQL statement is executed in the KI3 database: "()"
Obervation: The SQL statement returns 1 column 'rel'. The result of this SQL is () which means there are no results for this query.
Thought: The result is () so there is no relationship between as1233 and as3356. I now know the final answer.
Final Answer: 
There is no relationship between as1233 and as3356.
""

Begin!\n\n
        ''' 
        # Extra knowledge:{self.context}
        return sys_prompt

    def extract_answer(self, s):
        regex = r"Final Answer:([\s\S]*)"
        pattern = re.compile(regex)
        find = pattern.search(s)
        if find:
            result = find.group(1).strip()
        return result

    def re_struct(self, r):
        result = []
        for item in r:
            item = list(map(str, list(item)))
            row = ','.join(item)
            result.append(f'[{row}]')

        return ','.join(result)

    # @cached(cache=TTLCache(maxsize=128, ttl=600))
    def generate(self, query):
        result = self.re_struct(self.result)
        prompt = self.create_react_prompt(result)
        message = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Question: {query} ")
        ]
        content = self.model.invoke(message).content
        answer = self.extract_answer(content)
        return answer

