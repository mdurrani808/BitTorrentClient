from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Callable
import hashlib
import asyncio

@dataclass(frozen=True)
class Block:
    piece_idx: int
    offset: int
    length: int
    data: Optional[bytes] = None

@dataclass
class Piece:
    idx: int
    hash: bytes
    length: int
    blocks: Dict[int, bytes] = None
    received_blocks: int = 0
    is_complete: bool = False
    
    def __post_init__(self):
        if self.blocks is None:
            self.blocks = {}

class PieceManager:
    def __init__(self, block_size: int, hashes: List[bytes], filepath: str, 
                 total_length: int, piece_length: int):
        self.block_size = block_size
        self.piece_length = piece_length
        self.total_length = total_length
        self.num_pieces = len(hashes)
        self.total_downloaded = 0
        self.total_uploaded = 0
        self.pieces: Dict[int, Piece] = {}
        self.completed_pieces: Set[int] = set()
        self.pending_blocks: Dict[int, Set[int]] = {}
        self.on_piece_complete: Optional[Callable[[int], None]] = None
        
        for idx, piece_hash in enumerate(hashes):
            piece_length = self.piece_length
            if idx == self.num_pieces - 1:
                piece_length = self.total_length - (self.piece_length * idx)
            
            self.pieces[idx] = Piece(idx, piece_hash, piece_length)
            self.pending_blocks[idx] = set()

        self.file_handle = open(filepath, "wb+")
        self.file_handle.truncate(total_length)

    def get_bitfield(self) -> bytes:
        bitfield_length = (self.num_pieces + 7) // 8
        bitfield = bytearray(bitfield_length)
        for piece_idx in self.completed_pieces:
            byte_idx = piece_idx // 8
            bit_idx = 7 - (piece_idx % 8)
            bitfield[byte_idx] |= (1 << bit_idx)
        return bytes(bitfield)

    def select_blocks(self, peer_bitfield: bytes, num_blocks: int = 1) -> List[Block]:
        selected_blocks = []
        try:
            for piece_idx in range(self.num_pieces):
                if piece_idx in self.completed_pieces:
                    continue
                    
                byte_idx = piece_idx // 8
                bit_idx = 7 - (piece_idx % 8)
                
                if byte_idx < len(peer_bitfield) and peer_bitfield[byte_idx] & (1 << bit_idx):
                    piece = self.pieces[piece_idx]
                    offset = piece.received_blocks * self.block_size
                    
                    if offset >= piece.length or offset in self.pending_blocks[piece_idx]:
                        continue
                        
                    block_length = min(self.block_size, piece.length - offset)
                    if block_length <= 0:
                        continue
                        
                    selected_blocks.append(Block(piece_idx, offset, block_length))
                    self.pending_blocks[piece_idx].add(offset)
                    
                    if len(selected_blocks) >= num_blocks:
                        break
        except Exception as e:
            print(f"Error in select_blocks: {e}")
            return []
                        
        return selected_blocks

    async def recv_block(self, piece_idx: int, offset: int, data: bytes) -> None:
        if piece_idx not in self.pieces:
            return

        piece = self.pieces[piece_idx]
        if piece.is_complete or offset in piece.blocks:
            return

        piece.blocks[offset] = data
        piece.received_blocks += 1
        self.total_downloaded += len(data)
        self.pending_blocks[piece_idx].discard(offset)

        if len(piece.blocks) * self.block_size >= piece.length:
            piece_data = b''.join(piece.blocks[offset] for offset in sorted(piece.blocks.keys()))
            if hashlib.sha1(piece_data).digest() == piece.hash:
                piece.is_complete = True
                self.completed_pieces.add(piece_idx)
                for offset in piece.blocks.keys():
                    piece.blocks[offset] = None
                
                await self.write_piece(piece_idx, piece_data)

                if self.on_piece_complete:
                    await self.on_piece_complete(piece_idx)
            else:
                piece.blocks.clear()
                piece.received_blocks = 0
                self.pending_blocks[piece_idx].clear()

    async def write_piece(self, piece_idx: int, data: bytes) -> None:
        def blocking_io():
            self.file_handle.seek(piece_idx * self.piece_length)
            self.file_handle.write(data)
            self.file_handle.flush()
        await asyncio.to_thread(blocking_io)

    def get_block(self, index: int, begin: int, length: int) -> Optional[bytes]:
        if not (0 <= index < self.num_pieces and 
                0 <= begin < self.piece_length and 
                0 < length <= self.piece_length - begin):
            return None
            
        if index not in self.completed_pieces:
            return None
            
        self.file_handle.seek(index * self.piece_length + begin)
        data = self.file_handle.read(length)
        if data:
            self.total_uploaded += len(data)
        return data

    def get_metrics(self) -> dict:
        completed_length = len(self.completed_pieces) * self.piece_length
        if self.completed_pieces and max(self.completed_pieces) == self.num_pieces - 1:
            completed_length = completed_length - self.piece_length + self.pieces[self.num_pieces - 1].length
        left = max(0, self.total_length - completed_length)
        return {
            "uploaded": self.total_uploaded,
            "downloaded": self.total_downloaded,
            "left": left
        }