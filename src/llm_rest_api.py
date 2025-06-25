"""FlaskAPI runing module
"""

import json
import argparse
from typing import Dict, Any

from flask import *

from model.model_zoo import ModelZoo
from sql_react_prune import SQLChatAgent
from knn_icl import KNNSchema
from globals import *
from logger import logger

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
    # parse the input from the request body
    if not request.data:
        abort(404)        
    data = request.data.decode('utf-8')
    query = json.loads(data)
    if 'query' not in query or 'chatId' not in query:
        abort(400)
    query, chat_id = query['query'], int(query['chatId'])
    logger.info(f"Query: {query}")
    
    # Main workflow
    try:
        reuslt = sql_chat_agent.kickoff(query, chat_id)
    except:
        pass
    
    return jsonify({'msg': 'OK', 'ref': 200, 'data': reuslt, 'chatId': chat_id})

def pre_process():
    model_zoo: Dict[str, Any] = ModelZoo().get_model_zoo()
    
    global sql_chat_agent
    sql_chat_agent = SQLChatAgent(
        model=model_zoo
    )
    
    return app
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=54292, help='Production: 54292; Test: 57329')   
    args = parser.parse_args()
    app = pre_process()
    app.run(host='0.0.0.0', port=int(args.port))
