import asyncio
import socket
from typing import List, Tuple, Dict, Any
import bencodepy
from enum import IntEnum
from urllib.parse import urlparse
import ssl
import certifi

class Event(IntEnum):
    STARTED = 0
    STOPPED = 1
    COMPLETED = 2

class Tracker:
    def __init__(self, tracker_port: int, tracker_url, client_port, peer_id: bytes, info_hash):
        self.peer_id: bytes = peer_id
        self.tracker_port: int = tracker_port
        self.client_port = client_port
        self.info_hash = info_hash
        self.tracker_url = tracker_url

    async def announce(self, uploaded, downloaded, left, compact) -> Tuple[List[Tuple[str, int, str]], int]:
        # request = "GET /announce?"
        # params = "&".join([
        #     f"peer_id={self.peer_id}",
        #     f"port={self.client_port}",
        #     f"uploaded={uploaded}",
        #     f"downloaded={downloaded}",
        #     f"left={left}",
        #     f"compact={1 if compact else 0}",
        #     f"info_hash={''.join(['%' + f'{b:02x}' for b in self.info_hash])}"
        # ])
        # request = request+params
        
        # headers_str = "\r\n".join([
        #         f"Host: {self.tracker_url}",
        #         f"Accept: */*",
        #         f"Accept-Encoding: deflate, gzip"
        #     ])
        
        # http_request = request + "\r\n" + headers_str + "\r\n\r\n"
        
        # reader, writer = await asyncio.open_connection(self.tracker_url, self.tracker_port)
        
        # writer.write(http_request.encode())
        # await writer.drain()
        url = urlparse(self.tracker_url)
        scheme = url.scheme 
        use_ssl = scheme == "https"
        hostname = url.hostname
        path = url.path or "/announce"
        port = url.port or (443 if scheme == "https" else 80)

        params = "&".join([
            f"peer_id={self.peer_id}",
            f"port={self.client_port}",
            f"uploaded={uploaded}",
            f"downloaded={downloaded}",
            f"left={left}",
            f"compact={1 if compact else 0}",
            f"info_hash={''.join(['%' + f'{b:02x}' for b in self.info_hash])}"
        ])
        request_line = f"GET {path}?{params} HTTP/1.1"

        headers_str = "\r\n".join([
            f"Host: {hostname}",
            f"Accept: */*",
            f"Accept-Encoding: deflate, gzip"
        ])

        http_request = request_line + "\r\n" + headers_str + "\r\n\r\n"

        if scheme == "https":
            context = ssl.create_default_context(cafile=certifi.where())
            reader, writer = await asyncio.open_connection(hostname, port, ssl=context)
        else:
            reader, writer = await asyncio.open_connection(hostname, port)
            
        writer.write(http_request.encode())
        await writer.drain()
        
        chunks = []
        while True:
            chunk = await reader.read(2048)
            if not chunk:
                break
            chunks.append(chunk)
        
        writer.close()
        await writer.wait_closed()
        
        response = b''.join(chunks)
        try:
            if b'\r\n\r\n' in response:
                headers_part, body = response.split(b'\r\n\r\n', 1)
            else:
                body = response
                
            if b'd8:interval' in body:
                body = body[body.index(b'd8:interval'):]
            
            bencode_dict = bencodepy.decode(body)
            
            peers: List[Tuple[str, int, str]] = []
            if isinstance(bencode_dict[b"peers"], list):
                for peer in bencode_dict[b"peers"]:               
                        peers.append(
                            (
                            peer[b"ip"].decode("ascii"), 
                            int(peer[b"port"]),
                            peer[b"peer id"]
                            )
                        )
            else:
                peers_data = bencode_dict[b"peers"]
                for i in range(0, len(peers_data), 6):
                    ip_bytes = peers_data[i:i+4]
                    ip = socket.inet_ntoa(ip_bytes)
                    port = (peers_data[i+4] << 8) | peers_data[i+5]
                    peers.append((ip, port, ""))

            interval = bencode_dict[b"interval"]
            return (peers, interval)
        except Exception:
            if b'peers' in response and b'interval' in response:
                try:
                    bencode_dict = bencodepy.decode(response)
                    peers_data = bencode_dict[b"peers"]
                    peers = []
                    for i in range(0, len(peers_data), 6):
                        ip_bytes = peers_data[i:i+4]
                        ip = socket.inet_ntoa(ip_bytes)
                        port = (peers_data[i+4] << 8) | peers_data[i+5]
                        peers.append((ip, port, ""))
                    return (peers, bencode_dict[b"interval"])
                except:
                    raise
            raise
        
    async def scrape(self) -> dict:
        # Parse the tracker URL
        url = urlparse(self.tracker_url)
        hostname = url.hostname
        scheme = url.scheme
        port = url.port or (443 if scheme == "https" else 80)

        request = f"GET /scrape?info_hash={''.join(['%' + f'{x:02x}' for x in self.info_hash])}"

        headers_str = "\r\n".join([
            f"Host: {hostname}",
            "Accept: */*",
            "Accept-Encoding: deflate, gzip"
        ])
        
        http_request = request + "\r\n" + headers_str + "\r\n\r\n"

        if scheme == "https":
            context = ssl.create_default_context(cafile=certifi.where())
            reader, writer = await asyncio.open_connection(hostname, port, ssl=context)
        else:
            reader, writer = await asyncio.open_connection(hostname, port)

        writer.write(http_request.encode())
        await writer.drain()
        
        chunks = []
        while True:
            chunk = await reader.read(2048)
            if not chunk:
                break
            chunks.append(chunk)

        writer.close()
        await writer.wait_closed()

        response = b''.join(chunks)
        try:
            if b'\r\n\r\n' in response:
                _headers_part, body = response.split(b'\r\n\r\n', 1)
            else:
                body = response
            bencode_dict = bencodepy.decode(body)
            return bencode_dict[b"files"]
        except:
            bencode_dict = bencodepy.decode(response)
            return bencode_dict[b"files"]