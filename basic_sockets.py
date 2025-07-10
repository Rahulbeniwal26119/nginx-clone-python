import json
import socket

with open("./config.json", "r") as f:
    config = json.load(f)

HOST = config.get("host", "127.0.0.1")
PORT = config.get("port", 8000)
ROOT = config.get("root", ".")

# Let's create a socket first
tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# SOCK_STREAM means we are using TCP
# AF_INET means we are using IPv4

# set options to reuse the address so that we will not errors like "Address already in use"
tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# bind the socket to the host and port
tcp_socket.bind((HOST, PORT))

print(f"Server is running on http://{HOST}:{PORT} with root directory {ROOT}")

# For now set connection limit to 1, later we can make our server non blocking with threading
tcp_socket.listen(1)

print(f"Waiting for incoming connections on {HOST}:{PORT}...")

# Accept the incoming connection
client_socket, client_address = tcp_socket.accept()

# Read the request once (sufficient for simple HTTP GET)
data = client_socket.recv(1024)
request = data.decode("utf-8", errors="ignore")
print(f"From client {client_address}:\n{request.rstrip()}")

# Now let's return some response back to client
response = f"Hello world from {HOST}:{PORT}!\n"
response_headers = [
    "HTTP/1.1 200 OK",  # PROTOCOL VERSION and STATUS CODE
    "Content-Type: text/plain; charset=utf-8",
    f"Content-Length: {len(response)}",
    "Connection: close",  # Close the connection after response
]

response_message = "\n".join(response_headers) + "\n\n" + response

# Send the response back to client
client_socket.sendall(response_message.encode("utf-8"))  # change to byte string
client_socket.close()

tcp_socket.close()

print("Server has been shut down.")
