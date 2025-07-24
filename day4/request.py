import gzip
import logging

import urllib.parse as urlparse
from dataclasses import dataclass
from routes import get_handler

logger = logging.getLogger(__name__)


@dataclass
class Request:
    method: str
    path: str
    query_params: dict = None
    handler_function: callable = None
    headers: dict = None


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

    handler_fn = get_handler(path)
    logger.info(f"[{addr[0]}] {method} {path}")

    # Enough changes for the request parsing
    return Request(method, path, query_params, handler_fn, headers)

def parse_range(range_header: str, file_size: int):
    """
        bytes=500-999
        bytes=500- (from 500 to end)
        bytes=-500 (last 500 bytes)
    """

    try:
        unit, _, spec = range_header.partition("=")
        # Range Header Example: bytes=0-499
        if unit.strip() != "bytes":
            raise ValueError("Invalid range unit")
        start, _, end = spec.partition("-")
        if start == "" and end == "":
            # bytes=-
            raise ValueError("Range header must specify a range")

        if start == "":
            length = int(end)
            if length < 0:
                # bytes=--500
                raise ValueError("Invalid range length")
            # -500
            end = file_size - 1
            start = max(0, file_size - length)
        else:
            start = int(start)
            end = int(end) if end else file_size - 1
            if start > end:
                # bytes=500-400
                raise ValueError("Start cannot be greater than end")
        
        if start < 0 or end >= file_size:
            raise ValueError("Invalid range values")
        return start, end
    except ValueError as e:
        logger.error(f"Invalid Range Header: {range_header} - {e}")
        return None, None

def gzip_if_needed(content, mime, accept):
    if "gzip" in accept and (
        mime.startswith("text/") or
        mime.endswith("json")
    ):
        gz = gzip.compress(content, compresslevel=6)
        return gz, {
            "Content-Encoding": "gzip",
            "Content-Length": str(len(gz)),
            "Vary": "Accept-Encoding"
        }
    
    return content, {
        "Content-Length": str(len(content))
    }
        
