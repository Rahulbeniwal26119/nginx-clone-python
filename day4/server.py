import argparse
import socket
import threading

from connection import handle_request
from settings import settings
from handlers import _

def start_server():
    print(f"Starting server on {settings.HOST}:{settings.PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_server:
        tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_server.bind((settings.HOST, settings.PORT))
        tcp_server.listen(5)
        settings.logger.info(
            f"Server is running on http://{settings.HOST}:{settings.PORT}"
        )
        while True:
            client_socket, addr = tcp_server.accept()
            # Run a single thread for single client
            threading.Thread(
                target=handle_request,
                args=(
                    client_socket,
                    addr,
                ),
                daemon=True,  # To ensure thread exists when main thread exists
            ).start()


def main():
    parser = argparse.ArgumentParser(description="Nginx Clone")
    parser.add_argument("--port", type=int, help="Port to run the server on")
    parser.add_argument("--host", type=str, help="Host to run the server on")

    args = parser.parse_args()

    if args.port:
        settings.configure(PORT=args.port)

    if args.host:
        settings.configure(HOST=args.host)

    start_server()


if __name__ == "__main__":
    main()
