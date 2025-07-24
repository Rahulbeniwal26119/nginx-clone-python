import socket
from pathlib import Path

from request import parse_request
from response import http_response, static_file_response
from settings import settings
from status_code import HttpResponseCode

logger = settings.logger


def handle_request(client_socket, addr):
    try:
        client_socket.settimeout(0.5)
        while True:
            req_data = client_socket.recv(8 * 1024)
            print(req_data)
            if not req_data:
                logger.info(f"Connection closed by {addr[0]}")
                break
            request = parse_request(req_data, addr)

            if request.handler_function:
                response = request.handler_function(request)
            elif request.method in ("GET", "HEAD"):
                path = (settings.ROOT / Path(request.path.lstrip("/"))).resolve()
                if path.is_file():
                    response = static_file_response(path, request, head_only=request.method == "HEAD")
                else:
                    response = http_response(
                        HttpResponseCode.HTTP_RESPONSE_MESSAGES[
                            HttpResponseCode.HTTP_404_NOT_FOUND
                        ],
                        HttpResponseCode.HTTP_404_NOT_FOUND,
                        "text/plain",
                    )

            else:
                response = http_response(
                    HttpResponseCode.HTTP_RESPONSE_MESSAGES[
                        HttpResponseCode.HTTP_404_NOT_FOUND
                    ],
                    HttpResponseCode.HTTP_404_NOT_FOUND,
                    "text/plain",
                )

            if isinstance(response, tuple):
                head, stream_function = response
                client_socket.sendall(head)
                stream_function(client_socket)
            else:
                client_socket.sendall(response)

            logger.info(f"Response sent to {addr[0]}")

            connection_header = request.headers.get("Connection", "")

            if connection_header == "close":
                logger.info(f"Closing connection to {addr[0]}")
                break
            elif connection_header != "keep-alive":
                logger.info(f"No Keep-Alive header, closing connection to {addr[0]}")
                break

            logger.info(f"Keeping connection alive for {addr[0]}")

    except socket.timeout:
        logger.warning(f"Request from {addr[0]} timed out")
        logger.info(f"Connection closed after timeout for {addr[0]}")
    finally:
        try:
            client_socket.close()
            logger.info(f"Connection to {addr[0]} closed")
        except:
            pass

