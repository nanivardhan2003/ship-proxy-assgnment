import socket
import select
import threading
import argparse

shared_conn = None
lock = threading.Lock()

def read_http_message(conn):
    """Read full HTTP request or response from socket."""
    headers = b''
    while b'\r\n\r\n' not in headers:
        data = conn.recv(4096)
        if not data:
            return None
        headers += data
    header_end = headers.find(b'\r\n\r\n') + 4
    header_bytes = headers[:header_end]
    body = headers[header_end:]

    header_str = header_bytes.decode(errors='ignore').lower()
    content_length = 0
    chunked = 'chunked' in header_str

    for line in header_str.split('\r\n'):
        if line.startswith('content-length:'):
            content_length = int(line.split(':')[1].strip())

    if content_length > 0:
        while len(body) < content_length:
            data = conn.recv(content_length - len(body))
            if not data:
                return None
            body += data
    elif chunked:
        while True:
            chunk_header = b''
            while b'\r\n' not in chunk_header:
                data = conn.recv(1)
                if not data:
                    return None
                chunk_header += data
            chunk_size = int(chunk_header[:-2], 16)
            if chunk_size == 0:
                conn.recv(2)  # Trailing \r\n
                break
            chunk = b''
            while len(chunk) < chunk_size:
                data = conn.recv(chunk_size - len(chunk))
                if not data:
                    return None
                chunk += data
            body += chunk
            conn.recv(2)  # \r\n after chunk

    return header_bytes + body

def proxy_thread(browser_conn, addr):
    while True:
        try:
            request = read_http_message(browser_conn)
            if not request:
                break

            with lock:
                shared_conn.sendall(request)
                first_line = request.decode(errors='ignore').split('\r\n')[0]

                if 'CONNECT' in first_line:
                    # Handle HTTPS tunneling
                    response = read_http_message(shared_conn)
                    if response:
                        browser_conn.sendall(response)
                    socks = [browser_conn, shared_conn]
                    while True:
                        r, _, e = select.select(socks, [], socks, 60)
                        if e or not r:
                            break
                        for in_sock in r:
                            out_sock = shared_conn if in_sock == browser_conn else browser_conn
                            data = in_sock.recv(4096)
                            if not data:
                                break
                            out_sock.sendall(data)
                else:
                    # Handle HTTP response
                    response = read_http_message(shared_conn)
                    if response:
                        browser_conn.sendall(response)
                    else:
                        browser_conn.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
        except ConnectionResetError:
            break  # Handle client disconnection gracefully

    browser_conn.close()

def main(server_host, server_port):
    global shared_conn
    shared_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    shared_conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    shared_conn.connect((server_host, server_port))
    print(f'Connected to server at {server_host}:{server_port}')

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client.bind(('0.0.0.0', 8080))
    client.listen(10)
    print('Proxy client listening on port 8080')

    while True:
        browser_conn, addr = client.accept()
        thread = threading.Thread(target=proxy_thread, args=(browser_conn, addr))
        thread.daemon = True
        thread.start()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', required=True, help='Server address, e.g., localhost:8888')
    args = parser.parse_args()
    server_host, server_port = args.server.split(':')
    server_port = int(server_port)
    main(server_host, server_port)