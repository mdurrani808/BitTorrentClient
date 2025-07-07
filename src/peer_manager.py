from dataclasses import dataclass
import asyncio
from typing import Dict, Set
import time
from message import Request
from piece_manager import Block, PieceManager

@dataclass
class PeerState:
    peer_id: str
    bitfield: bytes
    writer: asyncio.StreamWriter
    unchoked: bool = False
    interested: bool = False
    pending_requests: Set[tuple] = None
    request_timestamps: Dict[tuple, float] = None
    
    def __post_init__(self):
        self.pending_requests = set()
        self.request_timestamps = {}

class PeerManager:
    def __init__(self, piece_manager: PieceManager, max_peer_requests: int = 300):
        self.piece_manager = piece_manager
        self.max_peer_requests = max_peer_requests
        self.peers: Dict[str, PeerState] = {}
        self.lock = asyncio.Lock()
        
    def add_peer(self, peer_id: str, writer: asyncio.StreamWriter):
        self.peers[peer_id] = PeerState(peer_id=peer_id, bitfield=None, writer=writer)
        
    def remove_peer(self, peer_id: str):
        if peer_id in self.peers:
            peer = self.peers[peer_id]
            for request in peer.pending_requests:
                piece_idx, offset = request
                self.piece_manager.pending_blocks[piece_idx].discard(offset)
            del self.peers[peer_id]
            
    def update_peer_bitfield(self, peer_id: str, bitfield: bytes):
        if peer_id in self.peers:
            self.peers[peer_id].bitfield = bitfield
            
    def update_peer_have(self, peer_id: str, piece_idx: int):
        if peer_id in self.peers and self.peers[peer_id].bitfield:
            byte_idx = piece_idx // 8
            if byte_idx < len(self.peers[peer_id].bitfield):
                self.peers[peer_id].bitfield = bytearray(self.peers[peer_id].bitfield)
                self.peers[peer_id].bitfield[byte_idx] |= (1 << (7 - (piece_idx % 8)))
                self.peers[peer_id].bitfield = bytes(self.peers[peer_id].bitfield)
    
    def set_peer_unchoked(self, peer_id: str, unchoked: bool):
        if peer_id in self.peers:
            self.peers[peer_id].unchoked = unchoked
            
    def set_peer_interested(self, peer_id: str, interested: bool):
        if peer_id in self.peers:
            self.peers[peer_id].interested = interested

    def is_peer_choked(self, peer_id: str) -> bool:
        return not (peer_id in self.peers and self.peers[peer_id].unchoked)

    async def request_blocks(self):
        async with self.lock:
            current_time = time.time()
            
            peer_list = list(self.peers.items())
            
            for peer_id, peer in peer_list:
                if peer_id not in self.peers:
                    continue
                    
                timed_out = [request for request in peer.pending_requests 
                            if current_time - peer.request_timestamps.get(request, current_time) > 10]
                    
                for request in timed_out:
                    piece_idx, offset = request
                    peer.pending_requests.discard(request)
                    self.piece_manager.pending_blocks[piece_idx].discard(offset)
                    del peer.request_timestamps[request]

            for peer_id, peer in peer_list:
                if peer_id not in self.peers:
                    continue
                    
                if not peer.unchoked or not peer.bitfield:
                    continue
                    
                available_slots = self.max_peer_requests - len(peer.pending_requests)
                if available_slots <= 0:
                    continue
                    
                blocks = self.piece_manager.select_blocks(peer.bitfield, available_slots)
                if not blocks:
                    continue
                    
                for block in blocks:
                    request_key = (block.piece_idx, block.offset)
                    try:
                        message = Request(block.piece_idx, block.offset, block.length)
                        peer.writer.write(message.encode())
                        await peer.writer.drain()
                        peer.pending_requests.add(request_key)
                        peer.request_timestamps[request_key] = time.time()
                    except:
                        self.piece_manager.pending_blocks[block.piece_idx].discard(block.offset)
                        
    async def handle_block_received(self, peer_id: str, piece_idx: int, offset: int):
        if peer_id in self.peers:
            request_key = (piece_idx, offset)
            self.peers[peer_id].pending_requests.discard(request_key)
            if request_key in self.peers[peer_id].request_timestamps:
                del self.peers[peer_id].request_timestamps[request_key]