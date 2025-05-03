from flask import *
import json
from sql_react_prune import agent_stream_prune
from database_react import Database_LLM, QuestionClassify_LLM, StraitAnswer_LLM
import argparse
from knn_icl import KNNQA, KNNSchema
from globals import *
from langchain_community.chat_models import AzureChatOpenAI
from openai import AzureOpenAI
from langchain_openai import ChatOpenAI
import os
import re
import time
from utils import get_context, map_table_url
import traceback

API_KEY= 'sk-78U3YlBuZGAIIX7eB4Ed08F86f4f4817B70617E0E2D8B2Cc'
MAX_LENGTH = 5

app = Flask(__name__)
app.debug = True
 
@app.errorhandler(404)
def not_found_error(error):
    return make_response(jsonify({'msg': 'Not Found', 'ref': 404, 'data':'', 'chatId':-1}), 404)

@app.errorhandler(400)
def bad_request_error(error):
    return make_response(jsonify({'msg': 'Bad Request', 'ref': 400, 'data':'', 'chatId':-1}), 400)

@app.errorhandler(500)
def internet_fail_error(error):
    return make_response(jsonify({'msg': 'Internal Server Error', 'ref': 500, 'data':'', 'chatId':-1}), 500)

@app.route('/query',methods=['post'])
def query():
    if not request.data:
        abort(404)        
    data = request.data.decode('utf-8')
    query = json.loads(data)
    if 'query' not in query or 'chatId' not in query:
        abort(400)
    query, chat_id = query['query'], int(query['chatId'])
    logger.info(f"Query: {query}")
    # 获得该chat_id对应的历史QA记录，支持多轮应答
    context_l = get_context(chat_id)
    
    # 对用户问题进行基本判断，如果与KI3无关，则直接回答
    question_classify = QuestionClassify_LLM(model)
    content = question_classify.run(query, context_l)
    logger.info(f"RAG Content: {content}")
    
    pattern = r'output:\s*"(.*?)"'
    m = re.search(pattern, content, re.IGNORECASE)
    if m:
        rag_query = m.group(1).strip()
    else:
        rag_query = query
    logger.info(f"RAG Query: {rag_query}")
    if 'false' in content.lower():
        try:
            strait_answer = StraitAnswer_LLM(model=model)
            answer = strait_answer.run(query)
        except Exception as e:
            logger.info(traceback.format_exc())
            abort(500)
    else:
        # 生成sql
        try:
            info_tuple = knowledge.create_structured_table_schema(rag_query, exclude_list=[], k=3) # context, table_list
            flag, result, sql = agent_stream_prune(query, rag_query, info_tuple, context_l, model, knowledge)
        except Exception as e:
            logger.info(traceback.format_exc())
            abort(500)
        
        if flag:
            pattern = r'\bfrom\s+([a-zA-Z_][a-zA-Z0-9_]*)\b'
            m = re.findall(pattern, sql.lower())
            url = ''
            if m:
                selected_table = m[0]
                try:
                    url = map_table_url(selected_table, DATA2URL)
                except Exception as e:
                    logger.info(traceback.format_exc())
                    url = ''
            result = result.strip('"')
            if url:
                answer = f"{result}\n\nIf you want to learn more, please go to the following website for further information.\nReference Links: {url}"
            else:
                answer = f"{result}"
            logger.info(answer)
            logger.info('\n\n<=============== End ================>\n\n')
        else:
            answer = "I'm so sorry that I can't answer your question based on the data I have currently. If you have any other internet related questions, please feel free to ask!"
            
    return jsonify({'msg': 'OK', 'ref': 200, 'data': answer, 'chatId': chat_id})

def pre_process():
    # 加载本地RAG模型
    global knowledge
    knowledge = KNNSchema()
    # 创建OPENAI实例
    global model
    model = ChatOpenAI(model="gpt-4o", openai_api_key=API_KEY, openai_api_base='https://aiproxy.lmzgc.cn:8080/v1', temperature=0)
    return app
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=54292, help='正式54292/测试57329')   
    args = parser.parse_args()
    app = pre_process()
    app.run(host='0.0.0.0', port=int(args.port))
