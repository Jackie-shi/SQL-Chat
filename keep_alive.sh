#!/usr/bin/env bash

BASE_DIR=$(cd `dirname $0`;pwd)
APP_NAME="llm_rest_api"
PID_DIR="${BASE_DIR}/.pid"
PID_FILE="${PID_DIR}/${APP_NAME}.pid"

mkdir -p $PID_DIR
touch $PID_FILE
cmd="$1"
shift
args=$@

daemon_start() {
    echo "********************************************"
    echo "启动服务..."
    PID=$(cat ${PID_FILE})
    if [ -n "$PID" ] && [ $(ps -p $PID | grep -c $PID) -eq 1 ]; then
        echo "检测到服务已经启动, PID:$PID"
        echo "********************************************"
        exit 0
    fi
    nohup python -u ${BASE_DIR}/llm_rest_api.py $args > ${APP_NAME}.log 2>&1 &
    echo $! > ${PID_FILE}
    echo "********************************************"
}

daemon_status() {
    echo "********************************************"
    PID=$(cat ${PID_FILE})
    if [ -n "$PID" ] && [ $(ps -p $PID | grep -c $PID) -eq 1 ]; then
        echo "进程 $CHECK_PID 存在."
    else
        echo "进程 $CHECK_PID 不存在."
    fi
    echo "********************************************"
}

daemon_stop() {
    echo "********************************************"
    echo "停止服务..."
    PID=$(cat ${PID_FILE})
    if [ -n "$PID" ] && [ $(ps -p $PID | grep -c $PID) -eq 1 ]; then
        kill  $(cat ${PID_FILE})
        rm "${PID_FILE}"
        echo "${APP_NAME} stopped"
    else
        echo "${APP_NAME} is not running"
    fi
    echo "********************************************"
}
daemon_restart() {
    echo "********************************************"
    daemon_stop
    daemon_start
    echo "********************************************"
}

case $cmd in
start)
    daemon_start
    ;;
status)
    daemon_status
    ;;
stop)
    daemon_stop
    ;;
restart)
    daemon_restart
    ;;
*)
    echo "Usage: ./keep_alive.sh {start|status|stop|restart}"
    exit 1
    ;;
esac
