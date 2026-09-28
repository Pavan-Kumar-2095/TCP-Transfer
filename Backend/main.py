from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import socket
import os
import threading
import time
import uuid

API_PORT = 8000
TRANSFER_PORT = 5000
CHUNK_SIZE = 64 * 1024

app = FastAPI(title="File Transfer API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

DEVICE_NAME = socket.gethostname()

jobs = {}
jobs_lock = threading.Lock()

def create_job():
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "starting",
        "status_text": "Preparing transfer...",
        "percent": 0,
        "transferred": 0,
        "total": 0,
        "speed": 0,
        "eta": None,
        "current_file": "",
        "message": "",
        "error": None,
        "started_at": time.time()
    }
    with jobs_lock:
        jobs[job_id] = job
    return job_id

def update_job(job_id, **values):
    with jobs_lock:
        if job_id not in jobs:
            return
        jobs[job_id].update(values)

def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return None
        return dict(job)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

@app.get("/")
async def root():
    return {"name": "File Transfer API", "status": "online"}

@app.get("/info")
async def info():
    return {
        "username": DEVICE_NAME,
        "device_name": DEVICE_NAME,
        "ip": get_local_ip()
    }

class SendData(BaseModel):
    file: str
    receiverIP: str
    sendPath: str

class ReceiveData(BaseModel):
    senderIP: str
    receiveIP: str
    destination: str

@app.get("/transfer/{job_id}")
async def transfer_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return {
            "status": "failed",
            "message": "Transfer job not found."
        }
    return job

def recv_exact(conn, size):
    data = b""
    while len(data) < size:
        chunk = conn.recv(min(CHUNK_SIZE, size - len(data)))
        if not chunk:
            raise ConnectionError("Connection closed.")
        data += chunk
    return data

def calculate_progress(job_id, transferred, total, started_at, current_file=""):
    elapsed = max(time.time() - started_at, 0.001)
    speed = transferred / elapsed

    if total > 0:
        percent = (transferred / total) * 100
        remaining = total - transferred
        eta = remaining / speed if speed > 0 else None
    else:
        percent = 0
        eta = None

    update_job(
        job_id,
        percent=percent,
        transferred=transferred,
        total=total,
        speed=speed,
        eta=eta,
        current_file=current_file
    )

def receive_files(job_id, save_dir, receive_ip, sender_ip):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        os.makedirs(save_dir, exist_ok=True)

        server.bind((receive_ip, TRANSFER_PORT))
        server.listen(1)

        update_job(
            job_id,
            status="waiting",
            status_text="Waiting for sender..."
        )

        print()
        print("========================================")
        print("Receiver started")
        print("IP:", receive_ip)
        print("Port:", TRANSFER_PORT)
        print("Waiting for:", sender_ip)
        print("========================================")
        print()

        while True:
            conn = None

            try:
                conn, addr = server.accept()

                print("Connection from:", addr[0])

                if addr[0] != sender_ip:
                    print("Rejected:", addr[0])
                    conn.close()
                    continue

                update_job(
                    job_id,
                    status="connecting",
                    status_text="Sender connected..."
                )

                transfer_type = recv_exact(conn, 1).decode()

                if transfer_type == "F":
                    name_len = int.from_bytes(recv_exact(conn, 4), "big")
                    filename = os.path.basename(
                        recv_exact(conn, name_len).decode()
                    )
                    size = int.from_bytes(recv_exact(conn, 8), "big")

                    filepath = os.path.join(save_dir, filename)

                    update_job(
                        job_id,
                        status="transferring",
                        status_text="Receiving file...",
                        total=size,
                        transferred=0,
                        current_file=filename,
                        started_at=time.time()
                    )

                    received = 0
                    started_at = time.time()

                    with open(filepath, "wb") as file:
                        while received < size:
                            chunk = conn.recv(
                                min(CHUNK_SIZE, size - received)
                            )

                            if not chunk:
                                raise ConnectionError(
                                    "Connection lost while receiving."
                                )

                            file.write(chunk)
                            received += len(chunk)

                            calculate_progress(
                                job_id,
                                received,
                                size,
                                started_at,
                                filename
                            )

                    update_job(
                        job_id,
                        status="completed",
                        status_text="Transfer complete",
                        percent=100,
                        transferred=size,
                        total=size,
                        eta=0,
                        current_file=filename,
                        message="File received successfully."
                    )

                    break

                elif transfer_type == "D":
                    name_len = int.from_bytes(recv_exact(conn, 4), "big")

                    folder = os.path.basename(
                        recv_exact(conn, name_len).decode()
                    )

                    folder_path = os.path.join(save_dir, folder)
                    os.makedirs(folder_path, exist_ok=True)

                    count = int.from_bytes(
                        recv_exact(conn, 4),
                        "big"
                    )

                    files_metadata = []
                    total_size = 0

                    for _ in range(count):
                        path_len = int.from_bytes(
                            recv_exact(conn, 4),
                            "big"
                        )

                        relative = os.path.normpath(
                            recv_exact(conn, path_len).decode()
                        )

                        if (
                            relative == ".."
                            or relative.startswith(".." + os.sep)
                            or os.path.isabs(relative)
                        ):
                            raise ValueError("Unsafe path.")

                        size = int.from_bytes(
                            recv_exact(conn, 8),
                            "big"
                        )

                        files_metadata.append((relative, size))
                        total_size += size

                    transferred_total = 0
                    started_at = time.time()

                    update_job(
                        job_id,
                        status="transferring",
                        status_text="Receiving folder...",
                        total=total_size,
                        transferred=0,
                        started_at=started_at
                    )

                    for relative, size in files_metadata:
                        filepath = os.path.join(folder_path, relative)
                        directory = os.path.dirname(filepath)

                        if directory:
                            os.makedirs(directory, exist_ok=True)

                        update_job(
                            job_id,
                            current_file=relative
                        )

                        received = 0

                        with open(filepath, "wb") as file:
                            while received < size:
                                chunk = conn.recv(
                                    min(CHUNK_SIZE, size - received)
                                )

                                if not chunk:
                                    raise ConnectionError(
                                        "Connection lost while receiving folder."
                                    )

                                file.write(chunk)
                                received += len(chunk)
                                transferred_total += len(chunk)

                                calculate_progress(
                                    job_id,
                                    transferred_total,
                                    total_size,
                                    started_at,
                                    relative
                                )

                    update_job(
                        job_id,
                        status="completed",
                        status_text="Transfer complete",
                        percent=100,
                        transferred=total_size,
                        total=total_size,
                        eta=0,
                        message="Folder received successfully."
                    )

                    break

                else:
                    raise ValueError("Unknown transfer type.")

            except Exception as e:
                print("Receive error:", e)

                update_job(
                    job_id,
                    status="failed",
                    status_text="Transfer failed",
                    error=str(e),
                    message=str(e)
                )

                break

            finally:
                if conn:
                    conn.close()

    except Exception as e:
        print("Receiver error:", e)

        update_job(
            job_id,
            status="failed",
            status_text="Receiver failed",
            error=str(e),
            message=str(e)
        )

    finally:
        server.close()

@app.post("/receive")
async def receive(data: ReceiveData):
    job_id = create_job()

    thread = threading.Thread(
        target=receive_files,
        args=(
            job_id,
            data.destination,
            data.receiveIP,
            data.senderIP
        ),
        daemon=True
    )

    thread.start()

    return {
        "status": "success",
        "job_id": job_id,
        "message": "Receiver started. Waiting for sender."
    }

def send_file(job_id, receiver_ip, path):
    client = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        update_job(
            job_id,
            status="connecting",
            status_text="Connecting to receiver..."
        )

        client.connect((receiver_ip, TRANSFER_PORT))

        filename = os.path.basename(path)
        size = os.path.getsize(path)

        client.sendall(b"F")

        name = filename.encode()

        client.sendall(
            len(name).to_bytes(4, "big")
        )

        client.sendall(name)

        client.sendall(
            size.to_bytes(8, "big")
        )

        sent = 0
        started_at = time.time()

        update_job(
            job_id,
            status="transferring",
            status_text="Sending file...",
            total=size,
            transferred=0,
            current_file=filename,
            started_at=started_at
        )

        with open(path, "rb") as file:
            while True:
                chunk = file.read(CHUNK_SIZE)

                if not chunk:
                    break

                client.sendall(chunk)
                sent += len(chunk)

                calculate_progress(
                    job_id,
                    sent,
                    size,
                    started_at,
                    filename
                )

        update_job(
            job_id,
            status="completed",
            status_text="Transfer complete",
            percent=100,
            transferred=size,
            total=size,
            eta=0,
            current_file=filename,
            message="File sent successfully."
        )

    except Exception as e:
        print("Send error:", e)

        update_job(
            job_id,
            status="failed",
            status_text="Transfer failed",
            error=str(e),
            message=str(e)
        )

    finally:
        client.close()

def send_folder(job_id, receiver_ip, path):
    client = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        update_job(
            job_id,
            status="connecting",
            status_text="Connecting to receiver..."
        )

        client.connect((receiver_ip, TRANSFER_PORT))

        folder = os.path.abspath(path)

        folder_name = os.path.basename(
            folder.rstrip(os.sep)
        )

        name = folder_name.encode()

        client.sendall(b"D")

        client.sendall(
            len(name).to_bytes(4, "big")
        )

        client.sendall(name)

        files = []

        for root, dirs, names in os.walk(folder):
            for filename in names:
                full = os.path.join(root, filename)

                relative = os.path.relpath(
                    full,
                    folder
                )

                size = os.path.getsize(full)

                files.append(
                    (full, relative, size)
                )

        total_size = sum(
            item[2]
            for item in files
        )

        client.sendall(
            len(files).to_bytes(4, "big")
        )

        for full, relative, size in files:
            relative_bytes = relative.encode()

            client.sendall(
                len(relative_bytes).to_bytes(4, "big")
            )

            client.sendall(relative_bytes)

            client.sendall(
                size.to_bytes(8, "big")
            )

        transferred_total = 0
        started_at = time.time()

        update_job(
            job_id,
            status="transferring",
            status_text="Sending folder...",
            total=total_size,
            transferred=0,
            started_at=started_at
        )

        for full, relative, size in files:
            update_job(
                job_id,
                current_file=relative
            )

            sent = 0

            with open(full, "rb") as file:
                while True:
                    chunk = file.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    client.sendall(chunk)

                    sent += len(chunk)
                    transferred_total += len(chunk)

                    calculate_progress(
                        job_id,
                        transferred_total,
                        total_size,
                        started_at,
                        relative
                    )

        update_job(
            job_id,
            status="completed",
            status_text="Transfer complete",
            percent=100,
            transferred=total_size,
            total=total_size,
            eta=0,
            message="Folder sent successfully."
        )

    except Exception as e:
        print("Folder send error:", e)

        update_job(
            job_id,
            status="failed",
            status_text="Transfer failed",
            error=str(e),
            message=str(e)
        )

    finally:
        client.close()

@app.post("/send")
async def send(data: SendData):
    path = data.sendPath

    if data.file == "file":
        if not os.path.isfile(path):
            return {
                "status": "error",
                "message": "That is not a valid file."
            }

    elif data.file == "folder":
        if not os.path.isdir(path):
            return {
                "status": "error",
                "message": "That is not a valid folder."
            }

    else:
        return {
            "status": "error",
            "message": "Invalid transfer type."
        }

    job_id = create_job()

    if data.file == "file":
        thread = threading.Thread(
            target=send_file,
            args=(
                job_id,
                data.receiverIP,
                path
            ),
            daemon=True
        )
    else:
        thread = threading.Thread(
            target=send_folder,
            args=(
                job_id,
                data.receiverIP,
                path
            ),
            daemon=True
        )

    thread.start()

    return {
        "status": "success",
        "job_id": job_id,
        "message": "Transfer started."
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=API_PORT
    )
