import socket
import select
import ssl
from urllib.parse import urlparse

PORT = 8888

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

def handle_normal_request(request, client_conn):
    """Handle non-CONNECT HTTP requests."""
    first_line = request.decode(errors='ignore').split('\r\n')[0]
    method, url, _ = first_line.split()
    parsed = urlparse(url)
    host = parsed.netloc.split(':')[0]
    port = int(parsed.netloc.split(':')[1]) if ':' in parsed.netloc else (80 if 'http' in parsed.scheme else 443)

    try:
        target = socket.socket(socket.AF_INET)
        if parsed.scheme == 'https' or 'CONNECT' in first_line:
            context = ssl.create_default_context()
            target = context.wrap_socket(target, server_hostname=host)
        target.connect((host, port))
        target.sendall(request)

        response = read_http_message(target)
        if not response:
            response = b'HTTP/1.1 502 Bad Gateway\r\n\r\n'
        client_conn.sendall(response)
    except Exception as e:
        client_conn.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
    finally:
        target.close()

def handle_connect_request(request, client_conn):
    """Handle CONNECT for HTTPS tunneling."""
    first_line = request.decode(errors='ignore').split('\r\n')[0]
    _, authority, _ = first_line.split()
    host, port = (authority.split(':') if ':' in authority else (authority, '443'))
    port = int(port)

    try:
        target = socket.socket(socket.AF_INET)
        context = ssl.create_default_context()
        target = context.wrap_socket(target, server_hostname=host)
        target.connect((host, port))
        client_conn.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')

        # Bidirectional relay
        socks = [client_conn, target]
        while True:
            r, _, e = select.select(socks, [], socks, 60)
            if e:
                break
            for in_sock in r:
                out_sock = target if in_sock == client_conn else client_conn
                data = in_sock.recv(4096)
                if not data:
                    return
                out_sock.sendall(data)
    except Exception:
        pass
    finally:
        target.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', PORT))
    server.listen(1)
    print(f'Proxy server listening on port {PORT}')
    conn, addr = server.accept()
    print(f'Connected from {addr}')

    while True:
        request = read_http_message(conn)
        if request is None:
            break
        first_line = request.decode(errors='ignore').split('\r\n')[0] if request else ''
        if 'CONNECT' in first_line:
            handle_connect_request(request, conn)
        else:
            handle_normal_request(request, conn)

    conn.close()
    server.close()

if __name__ == '__main__':
    main()