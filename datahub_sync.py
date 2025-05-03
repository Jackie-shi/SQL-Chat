import argparse
import json
from typing import Dict, List
import pdb
import random
import time
import re
import pandas as pd

from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph
from datahub.api.entities.dataproduct.dataproduct import DataProduct
from datahub.metadata._schema_classes import *
from datahub.metadata.com.linkedin.pegasus2avro.dataset import EditableDatasetProperties
from datahub.emitter.mce_builder import make_dataset_urn_with_platform_instance
import datahub.api.entities as en
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage
)

from mysql import MySQLDatabase
from utils import info

END_POINT = "http://192.168.17.5:48080"
API_KEY= 'sk-proj-oOwaDHznCtkIeNEhbxoVT3BlbkFJ4BazpkT0XiPHHOA1k50p'
MODEL = ChatOpenAI(model="gpt-4o-mini", openai_api_key=API_KEY, openai_api_base='https://openai.lmzgc.cn/v1', temperature=0)
# 需要对数据进行过滤
NO_MEANING_TABLES = ['ki3_data_source', 'permission_resource', 'permission_role', 'permission_role_resource', 'permission_user', 'permission_user_role', 'sys_operate_log', 'user_ai_chat', 'user_ai_chat_detail','user_contact','user_download', 'user_feedback', 'user_feedback_detail', 'ipv6_anycast_addresses_1', 'ipv6_anycast_addresses_2', 'syn_task_worker', 'iana_ipv4_special_registry_1', 'iana_ipv6_special_registry_1', 'ipv4_recovered_address_space_1', 'ipv4_recovered_address_space_2', 'ipv4_location', 'ipv6_support_domain', 'ki3_notification', 'ki3_paper', 'user_measurement_blockip', 'themis_alarms', 'sav_insertdb_record', 'ki3_dataset']
NO_MEANING_TABLE_PRE = ['zdel', 'ki3', 'user']
NO_MEANING_TABLE_CONTAIN = ['copy']

class DatahubClient:
    def __init__(self, endpoint):
        self.client = DataHubGraph(DatahubClientConfig(server=endpoint, token='eyJhbGciOiJIUzI1NiJ9.eyJhY3RvclR5cGUiOiJVU0VSIiwiYWN0b3JJZCI6InNoaWppYXlpIiwidHlwZSI6IlBFUlNPTkFMIiwidmVyc2lvbiI6IjIiLCJqdGkiOiIxMWEwNmM1Mi0yYzQ5LTRmZmMtYjk3ZS04MjNlYjVkNWNiNzUiLCJzdWIiOiJzaGlqaWF5aSIsImV4cCI6MTczMDk0MzYyMywiaXNzIjoiZGF0YWh1Yi1tZXRhZGF0YS1zZXJ2aWNlIn0.NkFdu4aVefIrXAame-v9kWTu5tscj2mD6DYPQ9YWScc'))
    def get_client(self) -> DataHubGraph:
        return self.client

def get_product_tables() -> List:
    sql = "show tables;"
    tables = [item[0] for item in mysql_product_obj.fetch(sql)[1]]
    result = []
    for table_name in tables:
        prefix = table_name.strip().split('_')[0].strip()
        if prefix not in NO_MEANING_TABLE_PRE and table_name not in NO_MEANING_TABLES:
            for item in NO_MEANING_TABLE_CONTAIN:
                if item in table_name:
                    continue
            result.append(table_name)
    return result

def single_table_info_sync(graph: DataHubGraph, dataset_urn, use_new=True) -> dict:
    final_result = {}
    column_info_l = []
    # Properties
    asset:DatasetPropertiesClass = graph.get_dataset_properties(entity_urn=dataset_urn)
    asset_editable:EditableDatasetProperties = graph.get_aspect(entity_urn=dataset_urn,aspect_type=EditableDatasetProperties) # 在datahub上更改后的对象
    if use_new and asset_editable:
        asset_description = asset_editable.description
    else:
        asset_description = asset.description # mysql表里面comment字段的信息
    meta:SchemaMetadataClass = graph.get_aspect(entity_urn=dataset_urn,aspect_type=SchemaMetadataClass)
    meta_editable:EditableSchemaMetadataClass = graph.get_aspect(entity_urn=dataset_urn,aspect_type=EditableSchemaMetadataClass)
    asset_fields_dict:Dict = {} # key: col, value: {}
    for field in meta.fields:
        fields_to_get = ['description', 'nullable', 'globalTags', 'glossaryTerms']
        field_path = field.fieldPath
        asset_fields_dict[field_path] = {f: getattr(field, f) for f in fields_to_get}
    if use_new and meta_editable:
        editable_field_infos:List[EditableSchemaFieldInfoClass] = meta_editable.editableSchemaFieldInfo
        for info in editable_field_infos:
            fieldPath = info.get('fieldPath')
            # 主要包括 description/tags/terms
            if info.get('description'):
                asset_fields_dict[fieldPath]['description'] = info.get('description')
            if info.get('globalTags'):
                tags = []
                for tag in info.get('globalTags').tags:
                    urn:str = tag.tag
                    tagClass:TagPropertiesClass = graph.get_aspect(urn,aspect_type=TagPropertiesClass)
                    name:str = tagClass.get('name')
                    tags.append(name)
                asset_fields_dict[fieldPath]['globalTags'] = tags
                if info.get('glossaryTerms'):
                    terms = []
                    for term in info.get('glossaryTerms').terms:
                        urn:str = term.urn
                        termClass:GlossaryTermInfoClass = graph.get_aspect(urn,aspect_type=GlossaryTermInfoClass)
                        name:str = termClass.get('name')
                        terms.append(name)
                    asset_fields_dict[fieldPath]['glossaryTerms'] = terms
    
    # Sample values
    sample_values = graph.get_latest_timeseries_value(entity_urn=dataset_urn, aspect_type=DatasetProfileClass, filter_criteria_map={}).fieldProfiles
    for col in sample_values:
        col_name = col.fieldPath
        
        if not col.sampleValues or len(col.sampleValues) < 5:
            sample_value = ''
        else:
            k = 5
            if len(col.sampleValues[0]) >= 100:
                k = 1
            sample_value = ','.join(list(map(lambda x: str(x), random.sample(col.sampleValues, k))))
        column_info = [col_name, asset_fields_dict[col_name]['description'], sample_value]
        column_info_l.append(column_info)

    final_result = {
        "description": asset_description,
        "column_info": column_info_l,
        "evidence": ""
    }
    
    return final_result

def fetch_from_datahub(tables: List) -> dict:
    result = {}
    datahub_client = DatahubClient(END_POINT)
    graph:DataHubGraph = datahub_client.get_client()
    
    for table_name in tables:
        try:
            dataset_urn = make_dataset_urn_with_platform_instance(platform="mysql", platform_instance='website', name=table_name, env="PROD")
            table_info:dict = single_table_info_sync(graph, dataset_urn)
        except Exception as e:
            print(f"Table {table_name}:\t{e}")
            table_info = {}
        result[table_name] = table_info
    return result

def transform_datahub_result(d: dict) -> dict:
    result: dict = {}
    for table_name in d.keys():
        result[table_name] = {}
        if not d[table_name]:
            continue
        for col in d[table_name]['column_info']:
            result[table_name][col[0]] = col[1]
    return result

def run():
    info(f"[Warm] Start!")
    tables = get_product_tables()
    result = fetch_from_datahub(tables)
    new_datahub_dict = transform_datahub_result(result)

    with open('./datahub_cold_raw_info.json', 'r') as f:
        bench_datahub_dict = json.load(f)
    with open('./auto_dump_table_info.json', 'r') as f:
        bench_result = json.load(f)
    # 增量更新
    needed_update_table: List = []
    unchanged_table: List = []

    new_updated_table = list(set(new_datahub_dict.keys()) - set(bench_datahub_dict.keys()))
    needed_update_table.extend(new_updated_table)
    for table_name in bench_datahub_dict.keys():
        if table_name in new_datahub_dict:
            new_col, bench_col = list(new_datahub_dict[table_name].keys()), list(bench_datahub_dict[table_name].keys())
            if set(new_col) - set(bench_col):
                needed_update_table.append(table_name)
            else:
                check_l = [new_datahub_dict[table_name][key]!=bench_datahub_dict[table_name][key] for key in bench_col]
                if sum(check_l) > 0:
                    needed_update_table.append(table_name)
                else:
                    unchanged_table.append(table_name)
    assert len(needed_update_table)+len(unchanged_table)==len(result.keys()), "Length unmatched"

    no_exist_table_l: List = []
    # 更新table_info
    for table_name in result.keys():
        if not result[table_name]:
            no_exist_table_l.append(table_name)
            continue
        if table_name in needed_update_table:
            info(f"[Warm] {table_name} need change")
            try:
                table_descr, table_column_translated = describe_translate(table_name, result[table_name])
            except Exception as e:
                info(f"[Warm Start] {table_name} Error - {e}")
                table_descr = 'Error'
                table_column_translated = 'Error'
                no_exist_table_l.append(table_name)
            
        elif table_name in unchanged_table:
            table_descr, table_column_translated = bench_result[table_name]['description'], bench_result[table_name]['column_info']
        
        result[table_name]['description'] = table_descr
        result[table_name]['column_info'] = table_column_translated
    
    # 删除没有表的情况
    for table_name in no_exist_table_l:
        del result[table_name]
        del new_datahub_dict[table_name]

    # 更新table_raw_info
    new_raw_data_dict = new_datahub_dict
    data = json.dumps(new_raw_data_dict)
    with open('./datahub_cold_raw_info.json', 'w') as f:
        f.write(data)

    data = json.dumps(result)
    with open('./auto_dump_table_info.json', 'w') as f:
        f.write(data)
    info(f"[Warm] Done!")

def run_cold_start():
    info(f"[Cold Start] Start!")
    tables = get_product_tables()
    result = fetch_from_datahub(tables)
    # 保存datahub原始数据
    raw_data_dict = transform_datahub_result(result)
    data = json.dumps(raw_data_dict)
    with open('./datahub_cold_raw_info.json', 'w') as f:
        f.write(data)

    for table_name in result.keys():
        if not result[table_name]:
            del result[table_name]
        try:
            table_descr, table_column_translated = describe_translate(table_name, result[table_name])
        except Exception as e:
            info(f"[Cold Start] {table_name} Error - {e}")
            table_descr = 'Error'
            table_column_translated = 'Error'
        result[table_name]['description'] = table_descr
        result[table_name]['column_info'] = table_column_translated
        time.sleep(1)

    data = json.dumps(result)
    with open('./auto_dump_table_info.json', 'w') as f:
        f.write(data)
    info(f"[Cold Start] Done!\tTotal {len(result.keys())}")

def check_datahub_bad_tables():
    tables = get_product_tables()
    result = fetch_from_datahub(tables)
    df_result = {
        'table': [],
        'miss_count': []
    }
    for table_name in result.keys():
        if not result[table_name]:
            continue
        miss_count = 0
        for col in result[table_name]['column_info']:
            if col[0] not in ['create_time', 'update_time'] and not col[1]:
                miss_count += 1
        if miss_count > 0:
            df_result['table'].append(table_name)
            df_result['miss_count'].append(miss_count)
    df = pd.DataFrame(df_result)
    df.to_csv('./evaluation/datahub_bad_tables.csv')

def toy_run():
    datahub_client = DatahubClient(END_POINT)
    graph:DataHubGraph = datahub_client.get_client()
    dataset_urn = make_dataset_urn_with_platform_instance(platform="mysql", platform_instance='website', name='as_bgp_status', env="PROD")
    asset:DatasetPropertiesClass = graph.get_dataset_properties(entity_urn=dataset_urn)
    asset_table_name = asset.name
    asset_editable:EditableDatasetProperties = graph.get_aspect(entity_urn=dataset_urn,aspect_type=EditableDatasetProperties) # 在datahub上更改后的对象
    asset_description = asset.description # mysql表里面comment字段的信息
    meta:SchemaMetadataClass = graph.get_aspect(entity_urn=dataset_urn,aspect_type=SchemaMetadataClass)
    sample_values = graph.get_latest_timeseries_value(entity_urn=dataset_urn, aspect_type=DatasetProfileClass, filter_criteria_map={})
    pdb.set_trace()

def describe_translate(table_name: str, table_dict: dict):
    def get_describe_prompt():
        sys_prompt = f'''
You are a professional mysql engineer who are good at coding and summarizing. Given a table schema, your task is to write a summary about this table, such as the information it contains.
The user's input is a sql schema information and you should output less than 5 sentences in English.

Requirements:
The response must match the user\'s input.
The response must be based on known information, and irrelevant information should not be included.
The response must be concise and relevant to the question.
The response mush be English!


Example1
""
Input: 
Table name: as_bgp_status
Table comment: AS Basic Information
Table contains the following columns:
1. `asn`, comment: 'AS number'
2. `as_name`, comment: 'AS name'
3. `collect_time`, comment: 'collection time'
4. `orgname`, comment: 'organization name'
5. `region`, comment: 'country 2-letter code'
6. `rir`, comment: 'rir name'
7. `customers`, comment: 'number of customers for this AS'
8. `ip_num`, comment: 'number of declared ipv4 addresses'
9. `ip_cover_ratio`, comment: 'ipv4-level ROA coverage rate'
10. `covered_by_roa`, comment: 'whether this AS is covered by ROA'
11. `ipv6_num`, comment: 'number of ipv6 addresses'
12. `ipv6_cover_ratio`, comment: 'ipv6-level ROA coverage rate'
13. `create_time`, comment: 'None'
14. `update_time`, comment: 'None'
15. `id`, comment: 'auto-incremented primary key, no business meaning'
Output: 
This table contains the basic information and statistics information of Autonomous Systems (AS). For basic information, it contains as name, organization name of as, registration information, region information and etc. For statistics information, it contains the number of customers, ipv4 and ipv6. It also contains ROA coverage information. You can use this table to get basic information about autonomous System(AS).
""        
'''
        user_prompt = '''
Input:
{sql_info}
'''
        return sys_prompt, user_prompt
    def get_translate_prompt():
        sys_prompt = f'''
You are a professional translator from Chinese to English. Given a table create schema, you need to translate the text in Chinese to English and leave other English part unchanged.
The user's input is a sql create schema and you should output the translated result.

Requirements:
The response must match the user\'s input.
The response must be based on known information, and irrelevant information should not be included.
The response must be concise and relevant to the question.

Example 1
Input:
Table name: as_bgp_status
Table comment: AS Basic Information
Table contains the following columns:
1. `asn`, comment: 'as编号'
2. `as_name`, comment: 'as名称'
3. `collect_time`, comment: '收集时间'
4. `orgname`, comment: '组织名称'
5. `region`, comment: '国家/组织2字母代号'
6. `rir`, comment: 'rir名称'
7. `customers`, comment: 'AS的customers 数量'
8. `ip_num`, comment: '已宣告的ipv4数量'
9. `ip_cover_ratio`, comment: 'ipv4级ROA覆盖率'
10. `covered_by_roa`, comment: '该AS收否被ROA覆盖'
11. `ipv6_num`, comment: 'ipv6地址数量'
12. `ipv6_cover_ratio`, comment: 'ipv6级ROA覆盖率'
13. `create_time`, comment: 'None'
14. `update_time`, comment: 'None'
15. `id`, comment: '自增主键，无业务含义'
Output:
Table name: as_bgp_status
Table comment: AS Basic Information
Table contains the following columns:
1. `asn`, comment: 'AS number'
2. `as_name`, comment: 'AS name'
3. `collect_time`, comment: 'collection time'
4. `orgname`, comment: 'organization name'
5. `region`, comment: 'country 2-letter code'
6. `rir`, comment: 'rir name'
7. `customers`, comment: 'number of customers for this AS'
8. `ip_num`, comment: 'number of declared ipv4 addresses'
9. `ip_cover_ratio`, comment: 'ipv4-level ROA coverage rate'
10. `covered_by_roa`, comment: 'whether this AS is covered by ROA'
11. `ipv6_num`, comment: 'number of ipv6 addresses'
12. `ipv6_cover_ratio`, comment: 'ipv6-level ROA coverage rate'
13. `create_time`, comment: 'None'
14. `update_time`, comment: 'None'
15. `id`, comment: 'auto-incremented primary key, no business meaning'
'''
        user_prompt = '''
Input:
{sql_info}
'''
        return sys_prompt, user_prompt
    def format_schema(table_name: str, descr: str, columns: List[List]):
        result = '''
Table name: {table_name}
Table comment: {table_dsr}
Table contains the following columns:
{col_info}
'''        
        col_l = []
        col_dict = {}
        single_col_info = "`{col_name}`, comment: '{col_dsr}'"
        for col in columns:
            col_name, col_dsr = col[0], col[1]
            col_l.append(single_col_info.format(col_name=col_name, col_dsr=col_dsr))
        col_info = '\n'.join([f"{i}. {item}" for i, item in enumerate(col_l)])
        col_dict = {item[0]: item[2] for item in columns}
        return result.format(
            table_name=table_name,
            table_dsr=descr,
            col_info=col_info
        ), col_dict
    def parse_translation(s: str, col_dict: dict):
        pattern = r"`([^`]*)`[\s\S]*comment:\s*'(.*)'"
        result = []
        for line in s.strip().split('\n'):
            if '`' not in line:
                continue
            m = re.search(pattern, line)
            if m:
                col_name, comment = m.group(1).strip(), m.group(2).strip()
                result.append([col_name, comment, col_dict[col_name]])
        return result
    info(f"[Auto-LLM Start] {table_name} starts")
    sql_info, col_dict = format_schema(table_name, table_dict['description'], table_dict['column_info'])    
    # gen describe
    dsr_sys, dsr_user = get_describe_prompt()
    dsr_messages = [
        SystemMessage(content=dsr_sys),
        HumanMessage(content=dsr_user.format(sql_info=sql_info))
    ]
    s1 = time.time()
    dsr_result = MODEL.invoke(dsr_messages).content
    print(f"dsr_time = {int(time.time() - s1)}")
    # translate
    tran_sys, tran_user = get_translate_prompt()
    tran_messages = [
        SystemMessage(content=tran_sys),
        HumanMessage(content=tran_user.format(sql_info=sql_info))
    ]
    s1 = time.time()
    tran_result = MODEL.invoke(tran_messages).content
    col_translated = parse_translation(tran_result, col_dict)
    print(f"tran_time = {int(time.time() - s1)}")
    return dsr_result, col_translated

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', default='warm', help='warm/cold/check')   
    args = parser.parse_args()

    mysql_product_obj = MySQLDatabase(in_product=True)
    if args.mode == 'warm':
        run()
    elif args.mode == 'cold':
        run_cold_start()
    elif args.mode == 'check':
        check_datahub_bad_tables()