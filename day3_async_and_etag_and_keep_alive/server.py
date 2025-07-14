# Hello Everyone, welcome to day 3 of the Nginx clone project.
# Today we are going to add support for:
# 1. Asynchronous request handling
# 2. ETag support for caching
# 3. Keep-Alive connections

# let's start 
import threading
import datetime
import logging
import json
import socket
from dataclasses import dataclass
from pathlib import Path
import urllib.parse as urlparse
import mimetypes
import email.utils
import hashlib # for digest

# set the logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nginx_clone")
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)

print("testing reload")

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
    304: "Not Modified",
    408: "Request Timeout",
}


def http_response(body, status_code=200, context_type="text/html", extra_headers=None, keep_open=True):
    # let's change this method to always return bytes

    if isinstance(body, dict):
        body = json.dumps(body, indent=4).encode("utf-8")
        context_type = "application/json"
    elif isinstance(body, str):
        body = body.encode("utf-8")
    
    if keep_open:
        connection = "keep-alive"
    else:
        connection = "close"

    response_header = [
        f"HTTP/1.1 {status_code} {HTTP_STATUS_CODES.get(status_code, 'Unknown')}",
        f"Content-Type: {context_type}; charset=utf-8",
        f"Content-Length: {len(body)}",
        f"Connection: {connection}",
    ]
    if extra_headers:
        for k, v in extra_headers.items():
            response_header.append(f"{k}: {v}")

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

def make_etag(file_stats):
    last_modified = file_stats.st_mtime
    size = file_stats.st_size
    etag = hashlib.md5(f"{last_modified}-{size}".encode("utf-8")).hexdigest()
    lm = email.utils.formatdate(last_modified, usegmt=True)
    return etag, lm


def static_file_response(file_path, request: Request):
    # check if file exists first
    path = Path(file_path).resolve()
    if not path.exists():
        return http_response(HTTP_STATUS_CODES[404], 404, "text/plain")
    elif not path.is_relative_to(Path(ROOT).resolve()):
        # if trying to access a file whose permission not granted
        return http_response(HTTP_STATUS_CODES[403], 403, "text/plain")
    file_stats = path.stat()
    etag, lm = make_etag(file_stats)

    # check the headers
    inm = request.headers.get("If-None-Match")
    ims = request.headers.get("Last-Modified-Since")

    not_modified = False
    if inm and inm == etag:
        not_modified = True
    if ims:
        # convert LMS to timestamp
        try:
            ims_time = email.utils.mktime_tz(email.utils.parsedate_tz(ims))
            not_modified = int(file_stats.st_mtime) <= int(ims_time)
        except Exception as e:
            logger.exception("Failed to validate ims", e)
            not_modified = False
    
    extra_headers = {
        "ETag": etag,
        "Last-Modified": lm
    }

    if not_modified:
        # No need to server file if not modified
        return http_response(
            b"",
            304, # My Bad it should be 304 instead of 302
            context_type="text/plain",
            extra_headers=extra_headers
        )

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
    return http_response(content, 200, mime, extra_headers=extra_headers)


def http_text_response(file_path):
    with open(file_path, "rb") as f:
        return http_response(f.read(), 200, "text/plain")

def handle_request(client_socket, addr):
    try:
        client_socket.settimeout(5)
        while True:
            req_data = client_socket.recv(1024)
            if not req_data:
                logger.info(f"Connection closed by {addr[0]}")
                break
            request = parse_request(req_data, addr)

            if request.handler_function:
                response = request.handler_function(request)
            elif request.method == "GET":
                path = (ROOT / Path(request.path.lstrip("/"))).resolve()
                if path.is_file():
                    response = static_file_response(path, request)
                else:
                    response = http_response("Path not found", 404, "text/plain")
            else:
                response = http_response("Path not found", 404, "text/plain")
            
            # we are also going to add support for keep-alive connections
            # Only close the connection where client requests
            if request.headers.get("Connection", "") and request.headers["Connection"] == "close":
                break

            client_socket.sendall(response)
            logger.info(f"Response sent to {addr[0]}")
    except socket.timeout:
        logger.warning(f"Request from {addr[0]} timed out")
        client_socket.sendall(http_response(HTTP_STATUS_CODES[408], 408, "text/plain"))

logger.info(f"Starting server on {HOST}:{PORT}")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_server:
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind((HOST, PORT))
    tcp_server.listen(5)
    logger.info(f"Server is running on http://{HOST}:{PORT}")
    while True:
        client_socket, addr = tcp_server.accept()
        # Run a single thread for single client
        threading.Thread(
            target=handle_request,
            args=(
                client_socket,
                addr,
            ),
            daemon=True # To ensure thread exists when main thread exists
        ).start()

# As you can see a new connection is being established to fetch all associated file
# But we can also re-use the same connection for related css and js files.