import datetime
import logging
import json
import socket
from dataclasses import dataclass
from pathlib import Path

# set the logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nginx_clone")
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)

@dataclass
class Request:
    method: str
    path: str
    handler_name: str = None
    handler_function: callable = None
    headers: dict = None

class InvalidRequestFormat(Exception):
    pass

with open("./config.json") as f:
    config = json.loads(f.read())

PORT = config.get("port", 8000)
HOST = config.get("host", "127.0.0.1")
ROOT = Path(config.get("root", "."))
HANDLERS = config.get("routes", {})

def http_response(body, status_code=200, context_type="text/html"):
    if isinstance(body, dict):
        body = json.dumps(body, indent=4).encode("utf-8")
        context_type = "application/json"
    elif isinstance(body, str):
        body = body.encode("utf-8")

    response_header = [
        f"HTTP/1.1 {status_code} OK",
        f"Content-Type: {context_type}; charset=utf-8",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    return "\n".join(response_header) + "\n\n" + body.decode("utf-8")

def hello_handler(req): return http_response("<h1>Hello, World!</h1>", 200, "text/html")
def root_handler(req):  return http_response("Welcome to the nginx clone", 200, "text/plain")
def time_handler(req):
    return http_response({"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

ROUTE_TABLE = {"root_handler": root_handler,
               "hello_handler": hello_handler,
               "time_handler": time_handler}

def parse_request(data: bytes, addr):
    data = data.decode("utf-8", errors="ignore")
    request_line, *rest = data.split("\n")
    method, path, _ = request_line.split(maxsplit=2)
    headers = {}
    for line in rest:
        if ":" in line:
            k, v = line.split(": ", 1)
            headers[k.strip()] = v.strip()

    handler_name = HANDLERS.get(path)
    handler_fn = ROUTE_TABLE.get(handler_name)
    logger.info(f"[{addr[0]}] {method} {path}")
    return Request(method, path, handler_name, handler_fn, headers)

def http_text_response(file_path):
    with open(file_path, "rb") as f:
        return http_response(f.read(), 200, "text/plain")

logger.info(f"Starting server on {HOST}:{PORT}")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_server:
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind((HOST, PORT))
    tcp_server.listen(5)
    logger.info(f"Server is running on http://{HOST}:{PORT}")
    while True:
        client_socket, addr = tcp_server.accept()
        with client_socket:
            req_data = client_socket.recv(1024)
            if not req_data:
                continue
            request = parse_request(req_data, addr)

            if request.handler_function:
                response = request.handler_function(request)
            elif request.method == "GET":
                path = (ROOT / Path(request.path.lstrip("/"))).resolve()
                if path.is_file():
                    response = http_text_response(path)
                else:
                    response = http_response("Path not found", 404, "text/plain")
            else:
                response = http_response("Path not found", 404, "text/plain")

            client_socket.sendall(response.encode("utf-8"))
            logger.info(f"Response sent to {addr[0]}")
