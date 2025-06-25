import asyncio
import time
import threading
from typing import Dict, List, Set, Tuple, Optional, Union, Any
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future, as_completed

from logger import logger

class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class TaskResult:
    task_id: int
    question: str
    answer: str
    status: TaskStatus
    execution_time: float
    error: Optional[str] = None

@dataclass
class TaskNode:
    task_id: int
    question: str
    dependencies: Set[int]
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[TaskResult] = None
    start_time: Optional[float] = None
    
class DAGScheduler:
    """基于拓扑排序的DAG任务调度器，支持并行执行和依赖等待"""
    
    def __init__(self, max_concurrent_tasks: int = 3):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[int, TaskNode] = {}
        self.running_tasks: Set[int] = set()
        self.completed_tasks: Set[int] = set()
        self.failed_tasks: Set[int] = set()
        self._lock = threading.Lock()  # 添加线程锁
        
    def add_tasks(self, idx2question: Dict[int, str], node_dependency: Dict[int, Set[int]]):
        """添加任务到调度器"""
        with self._lock:
            self.tasks.clear()
            self.running_tasks.clear()
            self.completed_tasks.clear()
            self.failed_tasks.clear()
            
            # 创建任务节点
            for task_id, question in idx2question.items():
                dependencies = node_dependency.get(task_id, set())
                self.tasks[task_id] = TaskNode(
                    task_id=task_id,
                    question=question,
                    dependencies=dependencies
                )
        
        logger.info(f"Added {len(self.tasks)} tasks to scheduler")
        self._log_dependency_graph()
    
    def _log_dependency_graph(self):
        """记录依赖关系图"""
        logger.info("Task Dependency Graph:")
        for task_id, task in self.tasks.items():
            if task.dependencies:
                deps = ", ".join(map(str, task.dependencies))
                logger.info(f"  Task {task_id}: depends on [{deps}]")
            else:
                logger.info(f"  Task {task_id}: no dependencies (can start immediately)")
    
    def get_ready_tasks(self) -> List[int]:
        """获取所有准备就绪的任务（依赖已满足且未执行）"""
        with self._lock:
            ready_tasks = []
            
            for task_id, task in self.tasks.items():
                if task.status != TaskStatus.PENDING:
                    continue
                    
                # 检查所有依赖是否已完成
                dependencies_satisfied = all(
                    dep_id in self.completed_tasks 
                    for dep_id in task.dependencies
                )
                
                # 检查是否有依赖失败
                has_failed_dependency = any(
                    dep_id in self.failed_tasks 
                    for dep_id in task.dependencies
                )
                
                if dependencies_satisfied and not has_failed_dependency:
                    ready_tasks.append(task_id)
                    task.status = TaskStatus.READY
            
            return ready_tasks
    
    def can_schedule_more_tasks(self) -> bool:
        """检查是否可以调度更多任务"""
        with self._lock:
            return len(self.running_tasks) < self.max_concurrent_tasks
    
    def get_schedulable_tasks(self) -> List[int]:
        """获取可以立即调度的任务"""
        ready_tasks = self.get_ready_tasks()
        with self._lock:
            available_slots = self.max_concurrent_tasks - len(self.running_tasks)
            return ready_tasks[:available_slots]
    
    def start_task(self, task_id: int):
        """标记任务开始执行"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.RUNNING
                self.tasks[task_id].start_time = time.time()
                self.running_tasks.add(task_id)
                logger.info(f"Started task {task_id}: '{self.tasks[task_id].question}'")
    
    def complete_task(self, task_id: int, result: TaskResult):
        """标记任务完成"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.COMPLETED
                self.tasks[task_id].result = result
                self.running_tasks.discard(task_id)
                self.completed_tasks.add(task_id)
                
                execution_time = time.time() - (self.tasks[task_id].start_time or 0)
                logger.info(f"Completed task {task_id} in {execution_time:.2f}s")
    
    def fail_task(self, task_id: int, error: str):
        """标记任务失败"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.FAILED
                self.running_tasks.discard(task_id)
                self.failed_tasks.add(task_id)
                logger.error(f"Failed task {task_id}: {error}")
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        with self._lock:
            total_tasks = len(self.tasks)
            return {
                "total_tasks": total_tasks,
                "completed": len(self.completed_tasks),
                "failed": len(self.failed_tasks),
                "running": len(self.running_tasks),
                "pending": total_tasks - len(self.completed_tasks) - len(self.failed_tasks) - len(self.running_tasks),
                "completion_rate": len(self.completed_tasks) / total_tasks if total_tasks > 0 else 0
            }
    
    def is_execution_complete(self) -> bool:
        """检查是否所有任务都已完成（成功或失败）"""
        with self._lock:
            return (len(self.completed_tasks) + len(self.failed_tasks)) == len(self.tasks)
    
    def get_dependent_tasks(self, failed_task_id: int) -> Set[int]:
        """获取依赖于失败任务的所有下游任务"""
        with self._lock:
            dependent_tasks = set()
            
            def find_dependents(task_id: int):
                for tid, task in self.tasks.items():
                    if task_id in task.dependencies and tid not in dependent_tasks:
                        dependent_tasks.add(tid)
                        find_dependents(tid)  # 递归查找
            
            find_dependents(failed_task_id)
            return dependent_tasks
    
    def get_external_info_for_task(self, task_id: int) -> Union[str, None]:
        """为任务生成外部信息（来自已完成的依赖任务）"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task or not task.dependencies:
                return None
            
            external_info_parts = []
            for dep_id in task.dependencies:
                if dep_id in self.completed_tasks:
                    dep_task = self.tasks[dep_id]
                    if dep_task.result:
                        external_info_parts.append(
                            f"From Question {dep_id} ('{dep_task.question}'): {dep_task.result.answer}"
                        )
            
            return "\n".join(external_info_parts) if external_info_parts else None

class ThreadedDAGExecutor:
    """多线程DAG执行器"""
    
    def __init__(self, scheduler: DAGScheduler, executor_func):
        self.scheduler = scheduler
        self.executor_func = executor_func  # 执行单个任务的函数
        
    def execute_dag(self) -> Dict[int, TaskResult]:
        """多线程执行整个DAG"""
        logger.info("Starting threaded DAG execution...")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.scheduler.max_concurrent_tasks) as executor:
            running_futures = {}  # task_id -> Future
            results = {}
            
            while not self.scheduler.is_execution_complete():
                # 获取可以调度的任务
                schedulable_tasks = self.scheduler.get_schedulable_tasks()
                
                # 启动新任务
                for task_id in schedulable_tasks:
                    external_info = self.scheduler.get_external_info_for_task(task_id)
                    task = self.scheduler.tasks[task_id]
                    
                    # 创建线程任务
                    future = executor.submit(
                        self._execute_single_task, task_id, task.question, external_info
                    )
                    running_futures[task_id] = future
                    self.scheduler.start_task(task_id)
                
                # 等待至少一个任务完成
                if running_futures:
                    # 检查已完成的任务
                    completed_futures = []
                    for task_id, future in list(running_futures.items()):
                        if future.done():
                            completed_futures.append((task_id, future))
                    
                    # 如果没有完成的任务，等待一小段时间
                    if not completed_futures:
                        time.sleep(0.1)
                        continue
                    
                    # 处理完成的任务
                    for task_id, future in completed_futures:
                        try:
                            result = future.result()
                            self.scheduler.complete_task(task_id, result)
                            results[task_id] = result
                        except Exception as e:
                            error_msg = str(e)
                            self.scheduler.fail_task(task_id, error_msg)
                            
                            # 标记依赖于失败任务的下游任务也失败
                            dependent_tasks = self.scheduler.get_dependent_tasks(task_id)
                            for dep_task_id in dependent_tasks:
                                self.scheduler.fail_task(dep_task_id, f"Dependency task {task_id} failed")
                        
                        # 清理已完成的future
                        del running_futures[task_id]
                else:
                    # 没有可运行的任务，可能所有任务都在等待或已完成
                    if not self.scheduler.is_execution_complete():
                        logger.warning("No schedulable tasks available but execution not complete")
                        break
                    
                time.sleep(0.1)  # 短暂休息
        
        execution_time = time.time() - start_time
        summary = self.scheduler.get_execution_summary()
        
        logger.info(f"Threaded DAG execution completed in {execution_time:.2f}s")
        logger.info(f"Execution summary: {summary}")
        
        return results
    
    def _execute_single_task(self, task_id: int, question: str, external_info: Union[str, None]) -> TaskResult:
        """执行单个任务"""
        start_time = time.time()
        
        try:
            # 调用实际的执行函数
            answer = self.executor_func(question, external_info)
            
            execution_time = time.time() - start_time
            
            return TaskResult(
                task_id=task_id,
                question=question,
                answer=answer,
                status=TaskStatus.COMPLETED,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return TaskResult(
                task_id=task_id,
                question=question,
                answer="",
                status=TaskStatus.FAILED,
                execution_time=execution_time,
                error=str(e)
            )
