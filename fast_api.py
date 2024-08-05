import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import subprocess
import shlex
from datetime import datetime
from queue import Queue
import threading
import uuid

app = FastAPI()
task_queue = Queue()  # 创建任务队列
task_lock = threading.Lock()  # 创建锁以同步访问任务队列
tasks = {}  # 存储任务状态

handler_method = ["./TxPortMap_linux_x64", "./FastjsonScan_linux_amd64", "./f403_linux_amd64"]

# 定义基本的输入数据模型
class InputData(BaseModel):
    text: str

# 定义任务状态和输出的响应模型
class TaskResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    output: str = ""
    error: str = None
def banner():
    return print("""___      ___                                         ____    ___      _____________            ____                                
`MM\     `M'                                        6MMMMb   `MM\     `M'`MMMMMMMMM           6MMMMb\                              
 MMM\     M                                        8P    Y8   MMM\     M  MM      \          6M'    `                              
 M\MM\    M            _____   ___  __            6M      Mb  M\MM\    M  MM                 MM         ____      ___    ___  __   
 M \MM\   M           6MMMMMb  `MM 6MMb           MM      MM  M \MM\   M  MM    ,            YM.       6MMMMb.  6MMMMb   `MM 6MMb  
 M  \MM\  M          6M'   `Mb  MMM9 `Mb          MM      MM  M  \MM\  M  MMMMMMM             YMMMMb  6M'   Mb 8M'  `Mb   MMM9 `Mb 
 M   \MM\ M          MM     MM  MM'   MM          MM      MM  M   \MM\ M  MM    `                 `Mb MM    `'     ,oMM   MM'   MM 
 M    \MM\M          MM     MM  MM    MM          MM      MM  M    \MM\M  MM                       MM MM       ,6MM9'MM   MM    MM 
 M     \MMM          MM     MM  MM    MM          YM      M9  M     \MMM  MM                       MM MM       MM'   MM   MM    MM 
 M      \MM          YM.   ,M9  MM    MM           8b    d8   M      \MM  MM      /          L    ,M9 YM.   d9 MM.  ,MM   MM    MM 
_M_      \M           YMMMMM9  _MM_  _MM_           YMMMM9   _M_      \M _MMMMMMMMM          MYMMMM9   YMMMM9  `YMMM9'Yb._MM_  _MM_
            MMMMMMMM                     MMMMMMMM                                   MMMMMMMM                                       
""")
    
def work_fork(handler, arg):
    # 使用 shlex.quote 来确保参数被正确引用
    quoted_arg = arg
    if handler == "./TxPortMap_linux_x64":
        return [handler, '-i', quoted_arg, '-t1000']
    elif handler == "./FastjsonScan_linux_amd64":
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output_file = f"{timestamp}.txt"
        return [handler, '-u', quoted_arg, '-o', output_file]
    elif handler == "./f403_linux_amd64":
        # 只返回所需的命令和参数
        return [handler, '-u', quoted_arg]
    else:
        raise ValueError("Unsupported handler")
# 线程工作函数
def worker():
    while True:
        args = task_queue.get()  # 从队列中获取任务
        if args is None:
            break  # 如果任务为None，表示没有更多任务，退出线程

        try:
            # 初始化任务ID
            task_id = None
            process = None
            try:
                # 确保参数是字符串形式
                # 使用 shlex.quote 来保证参数被正确引用
                args_str = ' '.join(shlex.quote(str(arg)) for arg in args)
                print(f"Running command: {args_str}")

                # 启动子进程执行命令
                process = subprocess.Popen(args,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT,
                                            text=True)
                task_id = uuid.uuid4()  # 使用uuid生成全局唯一任务ID

                # 存储任务状态
                tasks[task_id] = {
                    'id': task_id,
                    'status': 'running',
                    'output': '',
                    'error': None
                }

                # 读取并记录命令输出
                for line in process.stdout:
                    with task_lock:
                        print(line.strip())  # 打印输出到服务器端命令行
                        tasks[task_id]['output'] += line.strip() + '\n'

                process.wait()
                with task_lock:
                    if process.returncode == 0:
                        tasks[task_id]['status'] = 'completed'
                    else:
                        tasks[task_id]['status'] = 'failed'
                        tasks[task_id]['error'] = f"Command failed with return code {process.returncode}"

            except Exception as e:
                if task_id is not None:
                    with task_lock:
                        tasks[task_id] = {
                            'id': task_id,
                            'status': 'failed',
                            'error': str(e)
                        }
                # 确保即使出现异常，进程也能被正确终止
                if process is not None:
                    process.kill()
                    process.wait()

        except Exception as e:
            # 处理其他异常，例如任务ID生成失败
            print(f"An error occurred: {e}")

        finally:
            task_queue.task_done()  # 标记任务已完成

# 创建线程池
def create_thread_pool(num_threads):
    threads = []
    for _ in range(num_threads):
        thread = threading.Thread(target=worker)
        thread.start()
        threads.append(thread)
    return threads

# 启动线程池
thread_pool = create_thread_pool(len(handler_method))  # 例如创建4个线程

@app.post('/receive-data')
async def receive_data(data: InputData):
    task_ids = []  # 用于存储每个任务的任务ID
    try:
        args = data.text
        if not args:
            raise ValueError("No command provided")

        for handler in handler_method:
            # 为每个handler创建一个带有命令前缀的完整命令列表
            full_command = work_fork(handler,args)
            task_queue.put(full_command)  # 将任务添加到队列

            # 使用uuid生成全局唯一任务ID
            task_id = uuid.uuid4()
            task_ids.append(task_id)
            with task_lock:  # 确保线程安全地添加任务状态
                tasks[task_id] = {
                    'id': task_id,
                    'status': 'queued',  # 初始状态为'queued'
                    'output': '',
                    'error': None
                }
            print(f"Task {task_id} queued")

        return {"message": "Tasks started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get('/task-output/{task_id}')
async def get_task_output(task_id: int):
    with task_lock:
        task = tasks.get(task_id)
    if not task:
        return {"message": "Task not found"}
    return TaskResponse(**task)

if __name__ == '__main__':
    banner()
    uvicorn.run(app, host="127.0.0.1", port=8080)
