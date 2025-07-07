import asyncio
import sys
from typing import List, Dict
from peer_manager import PeerManager
from message import Handshake, MessageType, Have
from peer import Peer
from piece_manager import PieceManager
import random
class TorrentClient:
    def __init__(self, info_hash: bytes, my_id: str, pieceManager: PieceManager, listen_port: int):
        self.info_hash = info_hash
        self.my_id = my_id
        self.pieceManager = pieceManager
        self.peer_manager = PeerManager(pieceManager)
        self.peer_connections: Dict[str, asyncio.Task] = {}
        self.peerObjects: Dict[str, Peer] = {}
        self.MAX_UNCHOKED_PEERS = 8
        self._running = True
        self.port = listen_port
        self.server = None
        self.pieceManager.on_piece_complete = self.broadcast_have

    async def remove_peer(self, peer_id: str):
        if peer_id in self.peer_connections:
            self.peer_connections[peer_id].cancel()
            try:
                await self.peer_connections[peer_id]
            except:
                pass
            del self.peer_connections[peer_id]
        if peer_id in self.peerObjects:
            peer = self.peerObjects[peer_id]
            if peer.writer:
                try:
                    peer.writer.close()
                    await peer.writer.wait_closed()
                except:
                    pass
            if(peer_id in self.peerObjects):
                del self.peerObjects[peer_id]
        self.peer_manager.remove_peer(peer_id)
    
    async def broadcast_have(self, piece_idx: int):
        for peer_id, peer in list(self.peerObjects.items()):
            if peer.writer and not peer.writer.is_closing() and peer.has_handshaked:
                try:
                    await peer.send_message(peer.writer, MessageType.HAVE, piece_idx)
                except Exception as e:
                    await self.remove_peer(peer_id)

    async def start_downloading(self, peer_list: List):
        for p in peer_list:
            ip, port, peer_id = p[0], p[1], p[2]
            
            if peer_id and peer_id in self.peer_connections:
                await self.remove_peer(peer_id)
                
            peer = Peer(self.info_hash, self.my_id, self.peer_manager)
            peer.peer_id = peer_id
            self.peerObjects[peer_id] = peer
            
            task = asyncio.create_task(peer.connect_to_peer(ip, port))
            self.peer_connections[peer_id] = task
            
            def done_callback(t):
                if peer_id in self.peer_connections:
                    self.peer_connections[peer_id].cancel()
                    
            
            task.add_done_callback(done_callback)

    async def updateChokeStatus(self, interval=10.0):
        while self._running:
            try:
                active_peers = []
                for peer in self.peerObjects.values():
                    if not peer.has_handshaked or peer.writer is None:
                        continue
                        
                    if peer.peer_id == b'-PY0001-000000000000':
                        continue
                        
                    rate = (peer.get_upload_rate() if self.pieceManager.get_metrics()["left"] == 0 else peer.get_download_rate())
                    
                    peer_state = self.peer_manager.peers[peer.peer_id]
                    active_peers.append((peer, rate, peer_state.interested))

                active_peers.sort(key=lambda x: (x[2], x[1]), reverse=True)
                
                unchoked_peers = set()
                
                regular_slots = [p for p, _, interested in active_peers if interested][:3]
                unchoked_peers.update(regular_slots)
                
                remaining = [p for p, _, interested in active_peers if interested and p not in unchoked_peers]
                if remaining:
                    unchoked_peers.add(random.choice(remaining))

                for peer in self.peerObjects.values():
                    if peer.writer is None:
                        continue
                        
                    try:                        
                        if (peer in unchoked_peers or peer.peer_id == b'-PY0001-000000000000'):
                            await peer.send_message(peer.writer, MessageType.UNCHOKE)
                            self.peer_manager.set_peer_unchoked(peer.peer_id, True)
                        else:
                            await peer.send_message(peer.writer, MessageType.CHOKE)
                            self.peer_manager.set_peer_unchoked(peer.peer_id, False)
                    except Exception as e:
                        await self.remove_peer(peer.peer_id)
                        
            except Exception as e:
                print(f"Error in choke update: {e}")
                
            await asyncio.sleep(interval)

    async def request_loop(self, interval=.5):
        while self._running:
            try:
                await self.peer_manager.request_blocks()
            except Exception as e:
                print(f"Error in request loop: {e}")
            await asyncio.sleep(interval)

    async def run(self, peer_list: List):
        try:
            self.server = await asyncio.start_server(
                self.handle_incoming_connection,
                host='0.0.0.0',
                port=self.port
            )
            async with self.server:
                await asyncio.gather(
                    self.start_downloading(peer_list),
                    self.updateChokeStatus(),
                    self.request_loop(),
                    self.server.serve_forever()
                )
        except Exception as e:
            print(f"Error in torrent client: {e}")
        finally:
            self._running = False
            if self.server:
                self.server.close()
                await self.server.wait_closed()

    def get_peer_connections(self) -> Dict[str, asyncio.Task]:
        return self.peer_connections

    async def handle_incoming_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer_info = writer.get_extra_info('peername')        
        if not peer_info:
            writer.close()
            return

        try:
            data = await reader.readexactly(68)
            handshake = Handshake.decode(data)
            
            if handshake.info_hash != self.info_hash:
                writer.close()
                return
                
            peer_id = handshake.peer_id
            
            if not peer_id or peer_id == self.my_id:
                writer.close()
                return
                
            our_handshake = Handshake(self.info_hash, self.my_id)
            writer.write(our_handshake.encode())
            await writer.drain()
            
            peer = Peer(self.info_hash, self.my_id, self.peer_manager)
            peer.peer_ip, peer.peer_port = peer_info
            peer.peer_id = peer_id
            peer.has_handshaked = True
            self.peerObjects[peer_id] = peer
            self.peer_manager.add_peer(peer_id, writer)
            peer.writer = writer
            
            bitfield = self.pieceManager.get_bitfield()
            await peer.send_message(writer, MessageType.BITFIELD, bitfield)
            
            task = asyncio.create_task(peer.handle_peer_messages(reader, writer))
            self.peer_connections[peer_id] = task
            task.add_done_callback(lambda _: asyncio.create_task(self.remove_peer(peer_id)))
            await task
            
        except Exception as e:
            print(f"Error handling incoming connection: {e}")
            if 'peer_id' in locals() and peer_id:
                await self.remove_peer(peer_id)