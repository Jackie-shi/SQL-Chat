import json
import re
import time
import pandas as pd
import concurrent.futures
import threading

from sklearn.neighbors import NearestNeighbors
from sentence_transformers import SentenceTransformer
from FlagEmbedding import BGEM3FlagModel
from FlagEmbedding import FlagReranker
from transformers import AutoModel
from multiprocessing import Process, Manager
import faiss
import pickle
import torch

from mysql import MySQLDatabase
from .globals import *

MODEL_PATH = './model/bge-m3' # need to be changed
SQL_TIMEOUT = 5
def execute_sql(sql):
    mysql = MySQLDatabase(in_product=True)
    if 'create' in sql.lower() or 'delete' in sql.lower() or 'drop' in sql.lower() or 'insert' in sql.lower():
        return 'Execute fail. You can\'t modify these tables! Your wrong SQL is \"{sql}\".'
    if 'limit' not in sql.lower():
        sql = sql.rstrip(';')
        sql += ' LIMIT 5;'
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(mysql.fetch, sql)
        try:
            result = future.result(timeout=SQL_TIMEOUT)
        except concurrent.futures.TimeoutError:
            return 'Timeout', 'Timeout'
    # result = mysql.fetch(sql)

    return_card = "<Execute result>\n{s}\n</Execute result>"
    if result[0]:
        s = 'Execute success. The SQL is correct.'
        final_result = result[1]
    else:
        pattern = r"[\s\S]*\([\s\S]*,([\s\S]*)\)"
        error_info = result[1]
        m = re.search(pattern, error_info)
        if m:
            s = f'Execute fail. The Error is {m.group(1).strip()}. Your wrong SQL is \"{sql}\", you need to modify it.'
            final_result = ''
    return return_card.format(s=s), final_result


def load_cache(file_path):
    try:
        with open(file_path, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return {}

def save_cache(file_path, cache):
    with open(file_path, 'wb') as f:
        pickle.dump(cache, f)

class KNNQA(object):
    """
    Archived
    """
    def __init__(self, QA_path) -> None:
        self.df = pd.read_csv(QA_path)
        # Load model directly
        
        self.model = AutoModel.from_pretrained("microsoft/MiniLM-L12-H384-uncased")
    
    def get_topk_question(self, query, k=5):
        questions = self.df['Q'].values.tolist()
        questions.append(query)
        embeddings = self.model.encode(questions, convert_to_tensor=True)
        nrnb = NearestNeighbors(n_neighbors=k).fit(embeddings[:-1])
        distances, indices = nrnb.kneighbors(embeddings[-1].reshape(1, -1)) # indices: [[i1, i2, ...]]

        top_qa = self.df.iloc[indices[0], :].values.tolist()
        return top_qa
    
    def create_demonstration(self, query, k=5):
        top_qa = self.get_topk_question(query, k) # [[q, a], [q, a], ...]
        qa_prompt = []
        for i in range(len(top_qa)-1,-1,-1):
            q_template = f"Question: {top_qa[i][0]} \n"
            a_template = top_qa[i][1]
            qa_prompt.append(q_template + a_template)
        qa_sumup_prompt = ""
        for idx, item in enumerate(qa_prompt):
            qa_sumup_prompt += f"Example{idx+1}\n" + "\n" + item + "\n\n" 
        
        return qa_sumup_prompt

class KNNSchema(object):
    """
    RAG：召回和用户问题最相关的Table schema信息
    """
    def __init__(self) -> None:
        self.model = SentenceTransformer(MODEL_PATH)
        self.cache = load_cache('./model/embedding_cache.pkl')

    def get_embeddings(self, texts):
        embeddings = []
        for text in texts:
            if text in self.cache:
                embeddings.append(self.cache[text])
            else:
                embedding = self.model.encode(text, convert_to_tensor=True).cpu().data.numpy()
                self.cache[text] = embedding
                embeddings.append(embedding)
        save_cache('embedding_cache.pkl', self.cache)
        return torch.tensor(embeddings)

    def get_topk_knowledge_v2(self, query, exclude_list=[], k=5):
        with open(TABLE_JSON_PATH, 'r') as f:
            self.data = json.load(f)
        new_schema_list = []
        descr_list = []
        table_name_list = []
        for table_name in self.data.keys():
            if table_name in exclude_list:
                continue
            item = self.data[table_name]
            descr, cols = item['description'], item['column_info']
            s = f"Table name is {table_name}. It contais the following columns:"
            cols_format = []
            for idx, col in enumerate(cols):
                c = f"{idx+1}.{col[0]}, means {col[1]}"
                cols_format.append(c)
            col_str = '\t'.join(cols_format)
            new_schema_list.append(s+col_str)
            descr_list.append(descr)
            table_name_list.append(table_name)

        concat_list = [item1+'\n'+item2 for item1, item2 in zip(new_schema_list, descr_list)]
        concat_list.append(query)
        new_schema_list.append(query) # 平均长度300
        descr_list.append(query)
        
        # schema_embeddings = self.model.encode(new_schema_list, convert_to_tensor=True)
        # descr_embeddings = self.model.encode(descr_list, convert_to_tensor=True)
        # concat_embeddings = self.model.encode(concat_list, convert_to_tensor=True)
        concat_embeddings = self.get_embeddings(concat_list).cpu().data.numpy()

        
        # # schema
        # nrnb = NearestNeighbors(n_neighbors=k).fit(schema_embeddings[:-1])
        # distances1, indices1 = nrnb.kneighbors(schema_embeddings[-1].reshape(1, -1))
        # # description
        # nrnb = NearestNeighbors(n_neighbors=k).fit(descr_embeddings[:-1])
        # distances2, indices2 = nrnb.kneighbors(descr_embeddings[-1].reshape(1, -1))
        # both
        nrnb = NearestNeighbors(n_neighbors=k).fit(concat_embeddings[:-1])
        distances3, indices3 = nrnb.kneighbors(concat_embeddings[-1].reshape(1, -1))
        top_table_list = [table_name_list[idx] for idx in list(indices3[0])]
        return top_table_list
    
    def create_structured_table_schema(self, query, exclude_list=[], k=5):
        with open(TABLE_JSON_PATH, 'r') as f:
            self.data = json.load(f)
        top_knowledge_tables = self.get_topk_knowledge_v2(query, exclude_list, k)
        all_table_prompt_list = []
        one_table_schema_card = "# Table: {table_name}\tTable description: {descr}"
        one_column_card = "## Column {idx}: {col_name}, {col_comment}. Value examples: [{sample_data}]"
        evidence_card = "<Evidence>\n{s}\n"
        evidence_l = []
        for table_name in top_knowledge_tables:
            descr, column_list = self.data[table_name]['description'], self.data[table_name]['column_info']
            evidence = self.data[table_name]['evidence']
            if evidence != '':
                evidence_l.append(evidence.strip())
            column_sumpup = []
            for idx, col in enumerate(column_list):
                column_sumpup.append(one_column_card.format(
                    idx=idx+1,
                    col_name=col[0],
                    col_comment=col[1],
                    sample_data=col[2]
                ))
            column_prompt = '\n'.join(column_sumpup)
            all_table_prompt_list.append(one_table_schema_card.format(table_name=table_name, descr=descr.strip())+'\n'+column_prompt+'\n')
        if evidence_l != []:
            evidence_s = evidence_card.format(s=';'.join(evidence_l))
        else:
            evidence_s = evidence_card.format(s='No extra evidence.')
        final_schema = '<Table Schema>\n' + '\n'.join(all_table_prompt_list) + '\n'

        return final_schema+'\n'+evidence_s, top_knowledge_tables
    
    def get_topk_knowledge_from_column(self, query, exclude_list=[], k=5):
        table2column = {}
        id2table = {}
        id2column = {}
        all_column_list = []
        idx = 0
        for table_name in self.data.keys():
            if table_name in exclude_list:
                continue
            column_list = self.data[table_name]['column_info']
            for item in column_list:
                id2column[idx] = item
                if table_name not in table2column:
                    table2column[table_name] = []
                table2column[table_name].append(idx)
                id2table[idx] = table_name
                all_column_list.append(f"The column name is {item[0]}, which means {item[1]}")
                idx += 1
        all_column_list.append(query)
        # column_embeddings = self.bge_model.encode(all_column_list)['dense_vecs']
        column_embeddings = self.model.encode(all_column_list, convert_to_tensor=True)
    
        nrnb = NearestNeighbors(n_neighbors=k).fit(column_embeddings[:-1].cpu().data.numpy())
        distances, indices = nrnb.kneighbors(column_embeddings[-1].cpu().data.numpy().reshape(1, -1))
        target_column = [id2column[idx] for idx in list(indices[0])]
        # print(target_column)
        target_table = [id2table[idx] for idx in list(indices[0])]
        return list(set(target_table))

    def create_structured_table_schema_2(self, query, exclude_list=[], k=5):
        def rerank(table_list):
            reranker = FlagReranker('./model/bge-reranker-large', use_fp16=True)
            content_l = []
            for table_name in table_list:
                item = self.data[table_name]
                descr, cols = item['description'], item['column_info']
                s = f"Table name is {table_name}. It contais the following columns:"
                cols_format = []
                for idx, col in enumerate(cols):
                    c = f"{idx+1}.{col[0]}, means {col[1]}"
                    cols_format.append(c)
                col_str = '\t'.join(cols_format)
                content_l.append([query, s+col_str+'\n'+descr])
            score = reranker.compute_score(content_l)
            new_score = score.copy()
            new_score.sort(reverse=True)
            top_score = new_score[:k]
            result = []
            for item in top_score:
                idx = score.index(item)
                result.append(table_list[idx])
            # print(result)
            return result


        top_knowledge_tables = self.get_topk_knowledge_v2(query, exclude_list, k=5)
        top_tables_from_column = self.get_topk_knowledge_from_column(query, exclude_list, k=5)
        total_table_list = list(set(top_knowledge_tables + top_tables_from_column))
        # total_table_list = top_tables_from_column
        final_table_list = rerank(total_table_list)
        # final_table_list = total_table_list

        final_table_column = dict()

        all_table_prompt_list = []
        one_table_schema_card = "# Table: {table_name}\tTable description: {descr}"
        one_column_card = "## Column {idx}: {col_name}, {col_comment}. Value examples: [{sample_data}]"
        evidence_card = "<Evidence>\n{s}\n"
        evidence_l = []
        # for i in range(len(top_knowledge)):
        for table_name in final_table_list:
            # table_name = top_knowledge[i][0]
            descr, column_list = self.data[table_name]['description'], self.data[table_name]['column_info']
            evidence = self.data[table_name]['evidence']
            final_table_column[table_name] = {
                'description': descr,
                'column_info': column_list
            }
            # descr, column_list = final_table_column[table_name]['description'], final_table_column[table_name]['column_info']
            # evidence = final_table_column[table_name]['evidence']
            if evidence.strip() != '':
                evidence_l.append(evidence.strip())
            column_sumpup = []
            for idx, col in enumerate(column_list):
                column_sumpup.append(one_column_card.format(
                    idx=idx+1,
                    col_name=col[0],
                    col_comment=col[1],
                    sample_data=col[2]
                ))
            column_prompt = '\n'.join(column_sumpup)
            all_table_prompt_list.append(one_table_schema_card.format(table_name=table_name, descr=descr.strip())+'\n'+column_prompt+'\n')
        if evidence_l != []:
            evidence_s = evidence_card.format(s=';'.join(evidence_l))
        else:
            evidence_s = evidence_card.format(s='No extra evidence.')
        final_schema = '<Table Schema>\n' + '\n'.join(all_table_prompt_list) + '\n'

        return final_schema+'\n'+evidence_s
