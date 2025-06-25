import pandas as pd
import json
import pdb
import re
from typing import List, Dict, Any, Set
from pydantic import BaseModel
from collections import defaultdict

import datetime

from mysql import MySQLDatabase

def parse(s):
    '''
    "CREATE TABLE `as_bgp_status` (\n  `asn` int unsigned NOT NULL COMMENT 'AS number',\n  `as_name` varchar(100) DEFAULT NULL COMMENT 'AS name',\n  `collect_time` date DEFAULT NULL COMMENT 'collection time',\n  `orgname` varchar(500) DEFAULT NULL COMMENT 'organization name',\n  `region` char(2) DEFAULT NULL COMMENT 'country 2-letter code',\n  `rir` varchar(10) DEFAULT NULL COMMENT 'rir name',\n  `customers` int DEFAULT NULL COMMENT 'number of customers for this AS',\n  `ip_num` bigint DEFAULT NULL COMMENT 'number of declared ipv4 addresses',\n  `ip_cover_ratio` double DEFAULT NULL COMMENT 'ipv4-level ROA coverage rate',\n  `covered_by_roa` tinyint DEFAULT NULL COMMENT 'whether this AS is covered by ROA',\n  `ipv6_num` double DEFAULT NULL COMMENT 'number of ipv6 addresses',\n  `ipv6_cover_ratio` double DEFAULT NULL COMMENT 'ipv6-level ROA coverage rate',\n  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,\n  `update_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT 'auto-incremented primary key, no business meaning',\n  PRIMARY KEY (`id`),\n  KEY `idx_asn` (`asn`) USING BTREE\n) ENGINE=InnoDB AUTO_INCREMENT=113866 DEFAULT CHARSET=utf8mb3 ROW_FORMAT=DYNAMIC COMMENT='AS Basic Information';"
    '''
    l = s.strip().split('\n')
    result = []
    for line in l:
        line = line.strip()
        if line.startswith('`') and ('create_time' not in line and 'update_time' not in line):
            pattern = r"`([\s\S]*)`[\s\S]*COMMENT \'([\s\S]*)\'[\s\S]*"
            m = re.search(pattern, line)
            if m:
                result.append([m.group(1).strip(), m.group(2).strip()])
    return result

def sample_data(table_name, col_list):
    mysql = MySQLDatabase()
    result = []
    for col_item in col_list:
        col, descr = col_item
        sql = f'select {col} from {table_name} limit 5;'
        r = mysql.fetch(sql)[1]
        example_s = ','.join(list(map(lambda x:str(x).strip(), [item[0] for item in r])))
        result.append([col, descr, example_s])
    return result

def trans_from_csv_to_json():
    path = './new_table_info.csv'
    df = pd.read_csv(path)
    # pdb.set_trace()
    d = {}
    for idx, row in df.iterrows():
        table_name = row['table']
        schema = row['schema']
        description = row['description']
        evidence = row['evidence'] if str(row['evidence']) != 'nan' else ''
        column_list = parse(schema) # [[col1, comm1], [col2, comm2]]
        column_example_list = sample_data(table_name, column_list)
        d[table_name] = {
            'description': description,
            'column_info': column_example_list,
            'evidence': evidence
        }

    data = json.dumps(d)
    with open('new_table_info.json', 'w') as f:
        f.write(data)

def add_tables():
    path = './table_info.csv'
    df = pd.read_csv(path)
    sql_obj = MySQLDatabase()
    sql = 'show tables;'
    result = sql_obj.fetch(sql)[1]
    target_table_l = [item[0] for item in result if 'roa' in item[0] or 'rpki' in item[0]]
    for table_name in target_table_l:
        sql = f'show create table {table_name};'
        result = sql_obj.fetch(sql)[1]
        schema = result[0][1]
        df.loc[df.shape[0]] = [table_name, schema, ' ', ' ']
    df.to_csv('./new_table_info.csv', index=False)

def get_context(chat_id):
    sql_obj = MySQLDatabase(in_product=True)
    sql = f"select content,content_type from user_ai_chat_detail where chat_id={chat_id} order by create_time;"
    result = sql_obj.fetch(sql)
    context_l = []
    if result[0]:
        last_q = None
        print(result[1])
        for item in result[1]:
            content, content_type = item[0], int(item[1])
            if content_type == 1:
                last_q = content
            elif content_type == 2 and last_q != None:
                context_l.append(f"Question:{last_q}\nAnswer:{content}")
                last_q = None
    # 获得最近的10个历史窗口数据
    return context_l[:10]

def map_table_url(table_name, map: dict):
    split_name: List = table_name.strip().split('_')
    key_l = ['_'.join(split_name[:i])+'_' for i in range(1,len(split_name))]
    # 最长前缀匹配
    key_l.reverse()
    if table_name in map:
        return map[table_name]
    else:
        for key in key_l:
            if key in map:
                return map[key]
    return ''

def parse_by_pydantic(content: str, base_model: BaseModel):
    """Parse the content by BaseModel schema
    """
    # {'properties': {'x': {'title': 'X', 'type': 'string'}, 'y': {'title': 'Y', 'type': 'integer'}}, 'required': ['x', 'y'], 'title': 'H', 'type': 'object'}
    model_schema: Dict = base_model.model_json_schema()
    required_attrs: List[str] = model_schema["required"]
    pattern_zoo = [
        r'["\']?{attr}["\']?\s*:\s*"([^"]*)"',
        r'["\']?{attr}["\']\s*:\s*([^,\n\r]+)',
    ]
    parsed_data: Dict[str, Any] = {}
    
    for attr in required_attrs:
        # First try to match quoted string values
        for pattern in pattern_zoo:
            pattern = pattern.format(attr=attr)
            match = re.search(pattern, content)
            if match:
                parsed_data[attr] = match.group(1)
                break
    if len(parsed_data) != required_attrs:
        raise json.JSONDecodeError()
    
    properties: Dict = model_schema["properties"]
    for key, value in parsed_data.items():
        attr_type = properties[key]["type"]
        if attr_type == "string":
            parsed_data[key] = str(value)
        elif attr_type == "integer":
            parsed_data[key] = int(value)
        elif attr_type == "number":
            parsed_data[key] = float(value)
        elif attr_type == "boolean":
            parsed_data[key] = True if value.lower() == 'true' else False
    
    return parsed_data

def dag_post_process(questions: str, dependencies: str):
    idx2question: Dict[int, str] = defaultdict()
    node_dependency: Dict[int, Set[int]] = defaultdict(set)
    lines = questions.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line:
            # Match pattern like "1. question text"
            match = re.match(r'^(\d+)[.]\s*(.+)$', line)
            if match:
                idx = int(match.group(1))
                question = match.group(2).strip()
                idx2question[idx] = question
    
    for dependency in dependencies.strip().split('\n'):
        dependency = dependency.strip()
        tmp_l = [int(idx) for idx in dependency.split('->')]
        if len(tmp_l) > 1:
            # 1 -> 2 2: [1]
            node_dependency[tmp_l[1]].add(tmp_l[0])
    
    return idx2question, node_dependency


