# Hello Everyone, Welcome to second day of the Nginx clone project.
# Today we will going to implement the support for query parameter and
# adding support for static file serving (almost any type).

# Let's start

import datetime
import logging
import json
import socket
from dataclasses import dataclass
from pathlib import Path
import urllib.parse as urlparse
import mimetypes

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
    query_params: dict = None
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

HTTP_STATUS_CODES = {
    200: "OK",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
    403: "Forbidden",
}


def http_response(body, status_code=200, context_type="text/html"):
    # let's change this method to always return bytes

    if isinstance(body, dict):
        body = json.dumps(body, indent=4).encode("utf-8")
        context_type = "application/json"
    elif isinstance(body, str):
        body = body.encode("utf-8")

    response_header = [
        f"HTTP/1.1 {status_code} {HTTP_STATUS_CODES.get(status_code, 'Unknown')}",
        f"Content-Type: {context_type}; charset=utf-8",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    headers_response = ("\n".join(response_header) + "\n\n").encode("utf-8")
    return headers_response + body


def hello_handler(req):
    return http_response("<h1>Hello, World!</h1>", 200, "text/html")


def root_handler(req):
    return http_response("Welcome to the nginx clone", 200, "text/plain")


def time_handler(req):
    # Let's change the time handler to also return the query_params so we know if they are working
    return http_response(
        {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query_params": req.query_params,
        }
    )


ROUTE_TABLE = {
    "root_handler": root_handler,
    "hello_handler": hello_handler,
    "time_handler": time_handler,
}


def parse_request(data: bytes, addr):
    # Adding support for parsing the request data for query parameters
    data = data.decode("utf-8", errors="ignore")
    request_line, *rest = data.split("\n")
    method, path, _ = request_line.split(maxsplit=2)
    # path will contains the query parameters seperated by ?
    path, _, query = path.partition("?")
    query_params = urlparse.parse_qs(query)

    headers = {}
    for line in rest:
        if ":" in line:
            k, v = line.split(": ", 1)
            headers[k.strip()] = v.strip()

    handler_name = HANDLERS.get(path)
    handler_fn = ROUTE_TABLE.get(handler_name)
    logger.info(f"[{addr[0]}] {method} {path}")

    # Enough changes for the request parsing
    return Request(method, path, query_params, handler_name, handler_fn, headers)


# Not let's us make a function which will return a response for static files


def static_file_response(file_path):
    # check if file exists first
    path = Path(file_path).resolve()
    if not path.exists():
        return http_response(HTTP_STATUS_CODES[404], 404, "text/plain")
    elif not path.is_relative_to(Path(ROOT).resolve()):
        # if trying to access a file whose permission not granted
        return http_response(HTTP_STATUS_CODES[403], 403, "text/plain")

    # guess the mime type
    mime, _ = mimetypes.guess_type(file_path)
    if not mime:
        mime = "application/octet-stream"

    # read the file and take the content
    with open(file_path, "rb") as f:
        # what is file is very big we will see how we can
        # stream data efficiently
        content = f.read()

    # Ok we are done with this let's make change in main loop
    return http_response(content, 200, mime)


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
                    response = static_file_response(path)
                else:
                    response = http_response("Path not found", 404, "text/plain")
            else:
                response = http_response("Path not found", 404, "text/plain")

            client_socket.sendall(response)
            logger.info(f"Response sent to {addr[0]}")
