import asyncio
import socket
import struct
import time
from message import BitField, Choke, Handshake, Have, Interested, KeepAlive, MessageType, NotInterested, PieceMessage, Request, Unchoke

class Peer:
    def __init__(self, info_hash: bytes, my_id: str, coordinator):
        self.info_hash = info_hash
        self.my_id = my_id
        self.coordinator = coordinator
        self.peer_id = None
        self.peer_ip = None
        self.peer_port = None
        
        self.has_handshaked = False
        self.writer = None
        
        self.bytes_uploaded_interval = 0
        self.bytes_downloaded_interval = 0
        self.upload_rate = 0.0
        self.download_rate = 0.0
        self.last_rate_calc_time = time.time()
        self.last_sent = time.time()
        self.last_received = time.time()

    def updateRates(self): 
        '''Calculates the upload + download rates'''
        now = time.time()
        timeDelta = now - self.lastRateCalcTime

        if timeDelta > 0:
            self.uploadRate = self.bytesUploadedInterval / timeDelta
            self.downloadRate = self.bytesDownloadedInterval / timeDelta
        else:
            # Might happen if we call too rapidly
            self.uploadRate = 0.0
            self.downloadRate = 0.0

        self.bytesUploadedInterval = 0
        self.bytesDownloadedInterval = 0
        self.lastRateCalcTime = time.time()

    async def connect_to_peer(self, peer_ip, peer_port): 
        try:
            # print(f"Attempting to connect to peer {peer_ip}:{peer_port}")
            self.peer_ip = peer_ip
            self.peer_port = peer_port
            
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer_ip, peer_port),
                timeout=5
            )
            #print(f"Connection established to {peer_ip}:{peer_port}")
            self.writer = writer

            if await self.initiate_handshake(reader, writer):
                # print(f"Successfully completed handshake with {peer_ip}:{peer_port}")
                await self.handle_peer_messages(reader, writer)
            else:
                #print(f"Handshake failed with {peer_ip}:{peer_port}")
                if self.peer_id:
                    self.coordinator.remove_peer(self.peer_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Peer {peer_ip}:{peer_port} connection failed: {str(e)}")
            #if self.peer_id:
                #self.coordinator.remove_peer(self.peer_id)
        finally:
            if self.writer:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except:
                    pass
                self.writer = None
                

    async def initiate_handshake(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            handshake = Handshake(self.info_hash, self.my_id)
            writer.write(handshake.encode())
            self.last_sent = time.time()
            await writer.drain()

            data = await reader.readexactly(68)
            recv_handshake = Handshake.decode(data)
            self.peer_id = recv_handshake.peer_id

            if self.info_hash != recv_handshake.info_hash:
                return False

            self.coordinator.add_peer(self.peer_id, writer)
            self.has_handshaked = True

            bitfield = self.coordinator.piece_manager.get_bitfield()
            await self.send_message(writer, MessageType.BITFIELD, bitfield)

            return True

        except Exception as e:
            print(f"{self.peer_ip}:{self.peer_port}:{self.peer_id} Handshake failed: {e}")
            return False

    async def handle_peer_messages(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await self.send_message(writer, MessageType.INTERESTED)
            
            while True:
                await self.read_message(reader, writer)
        finally:
            self.coordinator.remove_peer(self.peer_id)

    async def read_message(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            len_data = await reader.readexactly(4)
            total_len = struct.unpack(">I", len_data)[0]

            if total_len == 0:
                self.last_received = time.time()
                return

            message_data = await reader.readexactly(total_len)
            message_id = message_data[0]
            self.last_received = time.time()
            payload = message_data[1:] if total_len > 1 else None

            match message_id:
                case MessageType.CHOKE:
                    self.coordinator.set_peer_unchoked(self.peer_id, False)
                case MessageType.UNCHOKE:
                    self.coordinator.set_peer_unchoked(self.peer_id, True)
                case MessageType.INTERESTED:
                    self.coordinator.set_peer_interested(self.peer_id, True)
                case MessageType.NOT_INTERESTED:
                    self.coordinator.set_peer_interested(self.peer_id, False)
                case MessageType.BITFIELD:
                    self.coordinator.update_peer_bitfield(self.peer_id, payload)
                case MessageType.HAVE:
                    piece_index = struct.unpack(">I", payload)[0]
                    self.coordinator.update_peer_have(self.peer_id, piece_index)
                case MessageType.PIECE:
                    piece_msg = PieceMessage.decode(len_data + message_data)
                    await self.coordinator.piece_manager.recv_block(
                        piece_msg.index,
                        piece_msg.begin,
                        piece_msg.block
                    )
                    await self.coordinator.handle_block_received(self.peer_id, piece_msg.index, piece_msg.begin)
                    self.bytes_downloaded_interval += len(piece_msg.block)
                case MessageType.REQUEST:
                    if not self.coordinator.is_peer_choked(self.peer_id):
                        request = Request.decode(len_data + message_data)
                        block = self.coordinator.piece_manager.get_block(
                            request.index, request.begin, request.length
                        )
                        if block:
                            block_piece = PieceMessage(request.index, request.begin, block)
                            await self.send_message(writer, MessageType.PIECE, block_piece)
                            self.bytes_uploaded_interval += len(block)

        except Exception as e:
            print(f"{self.peer_ip}:{self.peer_port}:{self.peer_id} Error reading message: {e}")
            raise

    async def send_message(self, writer: asyncio.StreamWriter, message_id, payload=None):
        try:
            
            message = None
            match message_id:
                case -1:
                    message = KeepAlive()
                    
                case MessageType.CHOKE:
                    message = Choke()
                case MessageType.UNCHOKE:
                    message = Unchoke()
                case MessageType.INTERESTED:
                    message = Interested()
                case MessageType.NOT_INTERESTED:
                    message = NotInterested()
                case MessageType.HAVE:
                    message = Have(payload)
                case MessageType.BITFIELD:
                    message = BitField(payload)
                case MessageType.REQUEST:
                    message = Request(payload.piece_idx, payload.offset, payload.length)
                case MessageType.PIECE:
                    message = payload

            if message:
                writer.write(message.encode())
                self.last_sent = time.time()
                await writer.drain()

                if message_id == MessageType.PIECE and payload:
                    self.bytes_uploaded_interval += len(payload.block)
        
        except Exception as e:
            print(f"{self.peer_ip}:{self.peer_port}:{self.peer_id} Error sending message with id: {message_id} -- {e}")


    def get_upload_rate(self) -> float:
        return self.upload_rate
    
    def get_download_rate(self) -> float:
        return self.download_rate
    
    def get_last_sent_time(self) -> float:
        return self.last_sent