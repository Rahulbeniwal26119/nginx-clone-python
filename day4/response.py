import json
import mimetypes
import os
from pathlib import Path

from request import Request, gzip_if_needed, parse_range
from serve_files import make_etag, parse_last_modified_since
from settings import settings
from status_code import HttpResponseCode

logger = settings.logger
CHUNK_SIZE = 64 * 1024  # 64 KB


def http_response(
    body,
    status_code=HttpResponseCode.HTTP_200_OK,
    content_type="text/html",
    extra_headers=None,
    keep_open=True,
):
    if isinstance(body, dict):
        body = json.dumps(body, indent=4).encode("utf-8")
        content_type = "application/json"
    elif isinstance(body, str):
        body = body.encode("utf-8")

    if keep_open:
        connection = "keep-alive"
    else:
        connection = "close"

    # Let content length be determined by the body size
    # or by the caller
    if content_type.startswith("text"):
        final_content_type = f"{content_type}; charset=utf-8"
    else:
        final_content_type = content_type

    response_header = [
        f"HTTP/1.1 {status_code} {HttpResponseCode.HTTP_RESPONSE_MESSAGES.get(status_code, 'Unknown')}",
        f"Content-Type: {final_content_type}",
        f"Connection: {connection}",
    ]
    if extra_headers:
        for k, v in extra_headers.items():
            response_header.append(f"{k}: {v}")

    headers_response = ("\r\n".join(response_header) + "\r\n\r\n").encode("utf-8")
    return headers_response + body


def static_file_response(file_path, request: Request, head_only=False):
    # check if file exists first
    path = Path(file_path).resolve()
    if not path.exists():
        return http_response(
            HttpResponseCode.HTTP_RESPONSE_MESSAGES[
                HttpResponseCode.HTTP_404_NOT_FOUND
            ],
            HttpResponseCode.HTTP_404_NOT_FOUND,
            "text/plain",
        )
    elif not path.is_relative_to(settings.ROOT):
        # if trying to access a file whose permission not granted
        return http_response(
            HttpResponseCode.HTTP_RESPONSE_MESSAGES[
                HttpResponseCode.HTTP_403_FORBIDDEN
            ],
            HttpResponseCode.HTTP_403_FORBIDDEN,
            "text/plain",
        )
    file_stats = path.stat()
    etag, lm = make_etag(file_stats)

    inm = request.headers.get("If-None-Match")
    ims = request.headers.get("If-Modified-Since")

    not_modified = False
    if inm and inm == etag:
        not_modified = True
    if ims:
        try:
            ims_time = parse_last_modified_since(ims)
            not_modified = int(file_stats.st_mtime) <= int(ims_time)
        except Exception as e:
            logger.exception("Failed to validate ims", e)
            not_modified = False

    common_headers = {"ETag": etag, "Last-Modified": lm}

    if not_modified:
        # No need to server file if not modified
        return http_response(
            b"",
            HttpResponseCode.HTTP_304_NOT_MODIFIED,
            content_type="text/plain",
            extra_headers={
                **common_headers,
                "Accept-Ranges": "bytes",
            },
        )

    # guess the mime type
    mime, _ = mimetypes.guess_type(file_path)
    if not mime:
        mime = "application/octet-stream"

    # ------------------- Range Handling -------------------
    resp = may_by_handle_range(path, request, common_headers=common_headers, head_only=head_only)
    if resp:
        return resp

    # --------- Large VS Small File Handling ---------
    if file_stats.st_size > 1_000_000:  # 1 MB
        return stream_large_file(path, request, common_headers=common_headers, head_only=head_only)
    else:
        return serve_small_files(path, mime, headers=common_headers)


def http_text_response(file_path):
    with open(file_path, "rb") as f:
        return http_response(f.read(), HttpResponseCode.HTTP_200_OK, "text/plain")


def may_by_handle_range(file_path: Path, request: Request, common_headers=None, head_only=False):
    size = file_path.stat().st_size
    range_header = request.headers.get("Range")

    if not range_header:
        # If no range header, serve the whole file
        return None

    try:
        start, end = parse_range(range_header, size)
    except ValueError as e:
        logger.error(f"Invalid Range Header: {range_header} - {e}")
        return http_response(
            HttpResponseCode.HTTP_RESPONSE_MESSAGES[
                HttpResponseCode.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE
            ],
            HttpResponseCode.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            "text/plain",
            extra_headers={
                "Content-Range": f"bytes */{size}",
                "Accept-Ranges": "bytes",
            }
        ), None

    content_length = end - start + 1
    mime, _ = mimetypes.guess_type(file_path)
    mime = mime or "application/octet-stream"

    headers = {
        **(common_headers or {}),
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }

    head = http_response(
        b"", HttpResponseCode.HTTP_206_PARTIAL_CONTENT, mime, extra_headers=headers
    )

    if head_only:
        return head

    def send_range_content(sock):
        with file_path.open("rb") as f:
            f.seek(start)
            remaining = content_length
            prev_timeout = sock.gettimeout()
            sock.settimeout(None)
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                sock.sendall(chunk)
                remaining -= len(chunk)
            sock.settimeout(prev_timeout)

    return head, send_range_content


def stream_large_file(
    path: Path,
    request: Request,
    common_headers=None,
    head_only=False
):
    size = path.stat().st_size
    headers = {
        **common_headers,
        "Content-Length": str(size),
        "Accept-Ranges": "bytes",
    }

    head = http_response(
        b"",
        HttpResponseCode.HTTP_200_OK,
        mimetypes.guess_type(path)[0] or "application/octet-stream",
        extra_headers=headers,
    )

    if head_only:
        return head

    if hasattr(os, "sendfile"):

        def sendfile(sock):
            with path.open("rb") as f:
                offset = 0
                size = path.stat().st_size
                while offset < size:
                    sent = os.sendfile(sock.fileno(), f.fileno(), offset, CHUNK_SIZE)
                    if sent == 0:
                        break
                    offset += sent
    else:

        def sendfile(sock):
            # run socket in blocking mode else we will get exception is buffer is full
            prev_timeout = sock.gettimeout()
            sock.settimeout(None)
            with path.open("rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    sock.sendall(chunk)
            sock.settimeout(prev_timeout)

    return head, sendfile


def serve_small_files(path, mime_type, headers=None):
    """
    Serve small files directly by reading them into memory.
    """
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"

    with path.open("rb") as f:
        content = f.read()

    body, gzip_headers = gzip_if_needed(
        content, mime_type, headers.get("Accept-Encoding", "") if headers else ""
    )

    headers.update(gzip_headers)

    return http_response(
        content, HttpResponseCode.HTTP_200_OK, mime, extra_headers=headers
    )
