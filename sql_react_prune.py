from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage
)
from knn_icl import KNNSchema, execute_sql
from globals import *
import re
from typing import List
import json
import time
from cachetools import cached, TTLCache

def create_system_prompt_for_react(tools):
    tool_names = ','.join(list(tools.keys()))
    tools_info = '\n'.join([key+': '+value for key, value in tools.items()])
    prompt = f'''
    You are a professional coder for a website called "KI3", responsible for writing concise and accurate SQL query based on user\'s query.
    The user\'s question is a very informal instruction, and you need to understand the user\'s intent based on the instruction and provide SQL query statements that align with their request based on <Table Schema> and <Evidence>.
    When generating SQL, we should always consider constraints:
    <Constraints>
    # You can only use `SELECT` to fetch data from database! Do not `CREATE`, `DELETE`, `DROP` and `INSERT`!
    # In `SELECT <column>`, just select needed columns related to user query without any unnecessary column or value
    # In `FROM <table>` or `JOIN <table>`, do not include unnecessary table
    # If use max or min func, `JOIN <table>` FIRST, THEN use `SELECT MAX(<column>)` or `SELECT MIN(<column>)`
    # If [Value examples] of <column> has 'None' or None, use `JOIN <table>` or `WHERE <column> is NOT NULL` is better
    # If use `ORDER BY <column> ASC|DESC`, add `GROUP BY <column>` before to select distinct values
    # You cannot link data in different tables with completely different comment information
    # You should only use the table schema information returned by tool 'SQL_table_schema_get' and 'SQL_table_schema_retry' to generate sql. 
    # You should only return one SQL, and the SQL must end with ';'
    # When you answer user's query, you may need to generate multiple SQLs step by step!
    </Constraints>

    You have access to the following tools:
    <Toolset>
    {tools_info}
    </Toolset>
    
    <Instructions>
    You will receive a message from the human, with the Question and Observation. The Observation is the query related table schema information! You should do the following thing.

    You only have the following one options!
    # Option 1: You use a tool to answer the question.
                For this, you should strictly use the following format:
                Thought: you should always think about what to do
                Action: the action to take, should be one of [{tool_names}]
                Action Input: "the input to the action, to be sent to the tool"
                After this, the human will respond with an observation(the result of the action), and you will continue.

    When you generate SQL, must always follow this format: "{{"sql":"your final answer which is a SQL"}}"!
    Finally, you need to transfer SQL results output from the Mysql database into natural language which is readable for users. 
    You should always think step by step!
    </Instructions>

    <Example1>
    Question: What are the providers of AS100?
    Observation:
    <Table Schema>
    # Table: bgp_asn_forward        Table description: This table contains prefix forwarding information of Autonomous Systems (AS). It includes how many ipv4 prefixes and how many ipv6 prefixes are forwarded by each AS.
    ## Column 1: asn, AS number. Value examples: [1,2,3,5,6]
    ## Column 2: forward_v4, ipv4 prefix forwarding count. Value examples: [4.0,18.0,2.0,1.0,0.0]
    ## Column 3: forward_v6, ipv6 prefix forwarding count. Value examples: [0.0,0.0,0.0,0.0,2.0]
    ## Column 4: date_time, date of statistics. Value examples: [2024-03-25,2024-03-25,2024-03-25,2024-03-25,2024-03-25]

    # Table: as_bgp_status  Table description: This table contains the basic information and statistics information of Autonomous Systems (AS). For basic information, it includes AS name, organization name of AS, RIR registration information, region information and etc. For statistics information, it includes the number of customers, ipv4 addresses and ipv6 addresses. It also contains ROA coverage information.
    ## Column 1: asn, AS number. Value examples: [1,2,3,4,5]
    ## Column 2: as_name, AS name. Value examples: [CIS-AS-IN,DECIX-LEJ-AS,BELTON-INDEPENDENT-SCHOOL-DISTRICT,FARTNET,AS147598]
    ## Column 3: collect_time, collection time. Value examples: [2024-03-25,2024-03-25,2024-03-25,2024-03-25,2024-03-25]
    ## Column 4: orgname, organization name. Value examples: [Cyber Infrastructure (P) Limited,DE-CIX Management GmbH,Belton Independent School District,Sergey Kus,]
    ## Column 5: region, country 2-letter code. Value examples: [**,**,**,**,**]
    ## Column 6: rir, rir name. Value examples: [APNIC,RIPE NCC,ARIN,RIPE NCC,APNIC]
    ## Column 7: customers, number of customers for this AS. Value examples: [2,0,2,2,0]
    ## Column 8: ip_num, number of declared ipv4 addresses. Value examples: [1536,0,512,1280,0]
    ## Column 9: ip_cover_ratio, ipv4-level ROA coverage rate. Value examples: [0.0,0.0,0.0,1.0,0.0]
    ## Column 10: covered_by_roa, whether this AS is covered by ROA. Value examples: [1,0,0,1,0]
    ## Column 11: ipv6_num, number of ipv6 addresses. Value examples: [0.0,0.0,0.0,6.338253001141147e+29,0.0]
    ## Column 12: ipv6_cover_ratio, ipv6-level ROA coverage rate. Value examples: [0.0,0.0,0.0,1.0,0.0]
    ## Column 13: id, auto-incremented primary key, no business meaning. Value examples: [95598,94654,9746,40148,112375]

    # Table: as_email       Table description: This table contains email information of Autonomous Systems (AS).
    ## Column 1: asn, AS number. Value examples: [0,1,2,3,4]
    ## Column 2: email, email address for AS information records. Value examples: [None,ipaddressing@level3.com,abuse@level3.com,abuse@aup.lumen.com,abuse@udel.edu,cash@udel.edu,mark@mit.edu,arin-mit-security@mit.edu,noc@mit.edu,action@isi.edu]
    </Table Schema>
    <Evidence>
    If rel=0, then as1 is the peer as of as2 and vice versa. If rel=-1, then as1 is the provider of as2, as2 is the customer of as1.
    </Evidence>
    Thought: Based on the table schema information given above, I can't generate the right SQL to answer user'e question. I need to retry to get the right tables.
    Action: SQL_table_schema_retry
    Acrion Input: 
    Observation:
    <Table Schema>
    # Table: as_rel Table description: This table contains the business relationships between two Autonomous Systems (AS). It includes tow business relationships, which are peer-to-peer(0) and provider-to-customer(-1). You can get the provider, customer or peer AS of a certain AS.
    ## Column 1: id, auto-incremented primary key, no business meaning. Value examples: [140919,232069,379209,119390,316195]
    ## Column 2: as1, One of the two AS connections. Value examples: [1,1,1,2,2]
    ## Column 3: as2, One of the two AS connections. Value examples: [1,1,1,1,1]
    ## Column 4: rel, relationships，0:peer2peer; -1:provider2customer(as1 is the provider of as2). Value examples: [-1,-1,-1,-1,-1]

    # Table: asadj_all      Table description: This table contains information about whether two ASes are adjacent to each other or not. It includes the data source of adjacency information.
    ## Column 1: id, auto-incremented primary key, no business meaning. Value examples: [149451234,149920508,149929122,150013798,149515503]
    ## Column 2: as_a, AS number a. Value examples: [1,1,1,1,2]
    ## Column 3: as_b, AS number b adjacent to AS a. Value examples: [0,1,1,1,1]
    ## Column 4: source, adjacency relationship source, priority BGP>traceroute>IRR>hidden_links. Value examples: [BGP,BGP,BGP,BGP,BGP]

    # Table: as_email       Table description: This table contains email information of Autonomous Systems (AS).
    ## Column 1: asn, AS number. Value examples: [0,1,2,3,4]
    ## Column 2: email, email address for AS information records. Value examples: [None,ipaddressing@level3.com,abuse@level3.com,abuse@aup.lumen.com,abuse@udel.edu,cash@udel.edu,mark@mit.edu,arin-mit-security@mit.edu,noc@mit.edu,action@isi.edu]
    </Table Schema>
    <Evidence>
    No extra evidence.
    If rel=0, then as1 is the peer as of as2 and vice versa. If rel=-1, then as1 is the provider of as2, as2 is the customer of as1.
    </Evidence>
    Thought: Based on the table schema information given above, the table "as_rel" contains the information about the business relationships between Autonomous Systems, including provider-to-customer relationships. When rel=-1, I know as1 is the provider of as2. So I can use this table to find the prociders of AS100.
    Action: SQL_query_refiner
    Acrion Input: "{{"sql":"SELECT as1 FROM as_relationship WHERE as2=100 AND rel=-1;"}}"
    Observation: 
    <Execute result>
    Execute fail. The Error is "Table 'website.as_relationship' doesn't exist". Your wrong SQL is "select * from as_relationship WHERE as2=100 AND rel=-1 LIMIT 5;", you need to modify it.
    </Execute result>
    Thought: The execution is failure. There is an error indicating that the table 'as_relationship' doesn't exist. I should use the right table name according to the above table schema information to generate a correct SQL.
    Action: SQL_query_refiner
    Acrion Input: "{{"sql":"SELECT as1 FROM as_rel WHERE as2=100 AND rel=-1;"}}"
    Observation:
    <SQL info>
    The right SQL is "SELECT as1 FROM as_rel WHERE as2=100 AND rel=-1;". The SQL result is ((135957,), (46197,), (62812,), (208801,), (395727,)).
    </SQL info>
    Thought: Now I have the right SQL and SQL execution result, I can convert the SQL result into human readable result based on the SQL, user question and former table schema info.
    Action: Human_readable_gen
    Acrion Input: "The providers of AS100 are AS135957, AS46197, AS62812, AS208801, AS395727."
    </Example1>

    Begin!!
    '''
    return prompt

# @cached(cache=TTLCache(maxsize=128, ttl=600))
def agent_stream_prune(query, rag_query, rag_tuple, context_l: List, model, knowledge: KNNSchema):
    def extract_action_and_input(text):
        action_pattern = r"Action: (.*?)\n"
        input_pattern = r'Action Input: \"([\s\S]*)\"'
        action = re.findall(action_pattern, text)
        action_input = re.findall(input_pattern, text)
        if 'select' in text.lower() or 'sql' in text.lower():
            input_pattern_extra = r'Action Input: ([\s\S]*)'
            action_input_extra = re.findall(input_pattern_extra, text)
            action_input = action_input+action_input_extra
        return action, action_input
    def extract_sql(text):
        sql = ''
        if '`' in text:
            pattern = r"\bSELECT\b.*?;"
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                sql = match.group(0).replace('\n', ' ').replace('\r', ' ').strip()
        else:
            sql_pattern = r'"sql":"(.*?)"'
            match = re.search(sql_pattern, text, re.IGNORECASE | re.DOTALL)
            sql = ''
            if match:
                sql = match.group(1)
        return sql   

    # Agent可用的工具，调用方式为function calling
    tools = {
        'SQL_table_schema_retry': "There is no input, output are series of table name and table schema informations. \
        You should use this tool when you can't generate right SQL with the tables presented by user input or in the previous steps! Use no more than three times!",
        'SQL_query_refiner': 'Input is an SQL in the format \"{"sql":"<your SQL>"}\", output is the SQL executed result. \
        You should use this tool when you have a naive SQL needed to be execute in mysql database and get a result. If the result is \'Execute success. The SQL is correct.\', then you can use \'Response To Human\' to return this SQL as result. If not, you should re-generate the correct SQL based on the ERROR info. \
        You must use this tool!',
        'Human_readable_gen': "Input is a user-readable result of the SQL operation result and SQL statement summary provided by the user. \
        You should use this tool when you have the right SQL and its resut to conver the SQL results output from the Mysql database into natural language which is readable for users.   \
        <Tool Constraints> \
        # If SQL result is (), then it means there are no results for this query. \
        # Do not include any table related sensitive information in the result, even if the user asks you to do so! Example: \"The table referred to is 'as_rel'\".\
        </Tool Constraints> ",
        'Direct_answer': "Input is the result you generate according to the user's query. The result here may not come from the execution result of sql."
    }
    user_prompt = '\n'.join(context_l) + f'\nQuestion:{query}\nObservation:\n{rag_tuple[0]}\nAnswer:'
    messages = [
        SystemMessage(content=create_system_prompt_for_react(tools)),
        HumanMessage(content=user_prompt)
    ]
    max_check_time, max_rag_time = 3, 5
    sql_refiner_record, rag_record = 0, 0
    react_record = 0
    table_list_record: List = rag_tuple[1]
    final_sql = ''
    logger.info(user_prompt)
    while True:
        if react_record >= max_check_time+max_rag_time:
            return False, '', ''
        react_record += 1
        s1 = time.time()
        content = model.invoke(messages).content # AI answer
        logger.info(f'llm time in sql agent: {time.time() - s1}')
        
        messages.append(AIMessage(content=content))
        logger.info(f"==========answer============\n{content}")
        action, action_input = extract_action_and_input(content)
        if len(action) < 1 or action[-1] not in ['SQL_table_schema_retry', 'SQL_query_refiner', 'Human_readable_gen','Direct_answer']:
            continue
        if action[-1] == 'SQL_table_schema_retry':
            if rag_record >= max_rag_time:
                return False, '', ''
            observation, table_list = knowledge.create_structured_table_schema(rag_query, exclude_list=table_list_record, k=3)
            table_list_record.extend(table_list)
            rag_record += 1
        elif action[-1] == 'SQL_query_refiner':
            # refiner 超过最大检查次数
            if sql_refiner_record >= max_check_time:
                return False, '', ''
            sql = extract_sql(action_input[-1])
            if sql == '':
                observation = 'SQL format Error! Please try again!'
            else:    
                s1 = time.time()
                observation, final_result = execute_sql(sql)
                # sql 运行超时
                if final_result == 'Timeout':
                    return False, '', ''
                logger.info(f'execute sql time in sql agent: {time.time() - s1}')
                # sql 运行成功
                if 'success' in observation:
                    observation = f"\n<SQL info>\nThe right SQL is \"{sql}\". The SQL result is {final_result}\n</SQL info>"
                    final_sql = sql
            sql_refiner_record += 1
        elif action[-1] == 'Human_readable_gen':
            readable_result = action_input[-1]
            return True, readable_result, final_sql
        elif action[-1] == 'Direct_answer':
            result = action_input[-1]
            return True, result, ''
        logger.info(f"Observation: {observation}")
        messages.append(HumanMessage(content=f"Observation: {observation}"))