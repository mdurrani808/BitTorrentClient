from enum import IntEnum
import struct

class MessageType(IntEnum):
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7
    CANCEL = 8
    PORT = 9
    
class Message:
    '''
    <length prefix><message ID><payload>
    length prefix - 4 bytes
    Message ID - 1 byte
    payload
    '''
    def encode(self) -> bytes:
        raise NotImplementedError("Put on Performance Improvement Plan!")
    
    @staticmethod
    def decode(encoded_bytes : bytes):
        totalLen = struct.unpack(">I", encoded_bytes)[0]
        # keep-alive message <len=000>
        if totalLen == 0:
            return (None, None)
        
        message_id = encoded_bytes[4]
        payload = encoded_bytes[5: 4 + totalLen]

        msg_type = MessageType(message_id)
        # A bit redundant since all 4 decodes also get's the type but if 
        # we need to optimize we can just update the offset in the subclasses
        if msg_type is MessageType.CHOKE:
            return Choke.decode()
        elif msg_type is MessageType.UNCHOKE:
            return Unchoke.decode()
        elif msg_type is MessageType.INTERESTED:
            return Interested.decode()
        elif msg_type is MessageType.NOT_INTERESTED:
            return NotInterested.decode()
        elif msg_type is MessageType.HAVE:
            return Have.decode(encoded_bytes)
        elif msg_type is MessageType.BITFIELD:
            return BitField.decode(encoded_bytes)
        elif msg_type is MessageType.REQUEST:
            return Request.decode(encoded_bytes)
        elif msg_type is MessageType.PIECE:
            return PieceMessage.decode(encoded_bytes)
        elif msg_type is MessageType.CANCEL:
            return Cancel.decode(encoded_bytes)
        elif msg_type is MessageType.PORT:
            return Port.decode(encoded_bytes)
        else:
            ValueError("huh, how? Good luck.")

class Handshake(Message):
    '''
    <pstrlen><pstr><reserved><info hash><peer id>
    Total Length = 49 + length of pstr
    pstrlen = 19
    pstr = "BitTorrent protocol"
    reserved = 8 bytes (Should just be all 0s)
    info_hash = 20 bytes
    peer_id = 20 bytes
    '''
    def __init__(self, info_hash : bytes, peer_id : bytes):
        self.pstr = b"BitTorrent protocol" # Add b prefix to make it byte encoded
        self.psrtlen = 19
        self.info_hash = info_hash
        self.reserved = bytes(8) # 8 bytes of all 0s
        self.peer_id = peer_id
    
    def encode(self) -> bytes:
        return struct.pack(">B", 19) + self.pstr + self.reserved + self.info_hash + self.peer_id.encode()  # no need to pack, it's already in bytes

    @staticmethod
    def decode(encoded_bytes : bytes):
        pstrlen = encoded_bytes[0]
        # 1 byte for len, 19 for pstr, and to skip info hash and 8 to skip reserved bytes 
        encoding_offset = 1 + pstrlen + 8 

        info_hash = encoded_bytes[encoding_offset: encoding_offset + 20]
        peer_id = encoded_bytes[encoding_offset + 20: encoding_offset + 40]

        return Handshake(info_hash, peer_id)

class KeepAlive(Message):
    '''
    <length = 0>
    '''
    def encode(self) -> bytes:
        return struct.pack(">I", 0)

    @staticmethod
    def decode():
        return KeepAlive()

class Choke(Message):
    '''
    <length = 1><id = 0>
    '''
    def encode(self) -> bytes:
        encoding_len = 1
        return struct.pack(">IB", encoding_len, MessageType.CHOKE)

    @staticmethod
    def decode():
        return Choke()

class Unchoke(Message):
    '''
    <length = 1><id = 1>
    '''
    def encode(self) -> bytes:
        encoding_len = 1
        return struct.pack(">IB", encoding_len, MessageType.UNCHOKE)

    @staticmethod
    def decode():
        return Unchoke()

class Interested(Message):
    '''
    <length = 1><id = 2>
    '''
    def encode(self) -> bytes:
        encoding_len = 1
        return struct.pack(">IB", encoding_len, MessageType.INTERESTED)

    @staticmethod
    def decode():
        return Interested()

class NotInterested(Message):
    '''
    <length = 1><id = 3>
    '''
    def encode(self) -> bytes:
        encoding_len = 1
        return struct.pack(">IB", encoding_len, MessageType.NOT_INTERESTED)

    @staticmethod
    def decode():
        return NotInterested()

class Have(Message):
    '''
    <length = 5><id = 4><piece index>
    Variable Length
    '''
    def __init__(self, piece_index : int):
        self.piece_index = piece_index

    def encode(self) -> bytes:
        encoding_len = 5
        return struct.pack(">IBI", encoding_len, MessageType.HAVE, self.piece_index)

    @staticmethod
    def decode(encoded_bytes : bytes):
        # extract 4 byte piece index from the offset of 5
        piece_index = struct.unpack(">I", encoded_bytes[5: 9])[0]

        return Have(piece_index)

        

# Sent immediately after Handshake and before any other messages
# Variable Length
class BitField(Message):
    '''
    <length = 1 + X><id = 5><bitfield>
    Variable Length
    '''
    def __init__(self, bitfield : bytes):
        self.bitfield = bitfield

    def encode(self) -> bytes:
        encoding_len = 1 + len(self.bitfield)
        return struct.pack(">IB", encoding_len, MessageType.BITFIELD) + self.bitfield # no need to pack, it's already in bytes
    
    @staticmethod
    def decode(encoded_bytes : bytes):
        length = struct.unpack(">I", encoded_bytes[:4])[0]
        bitfield = encoded_bytes[5: 4 + length]

        return BitField(bitfield)

class Request(Message):
    '''
    <length = 13><id = 6><index><begin><block>
    Variable Length
    '''
    def __init__(self, index : int, begin : int, length : int):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self) -> bytes:
        encoding_len = 13
        return struct.pack(">IBIII", encoding_len, MessageType.REQUEST, self.index, self.begin, self.length)

    @staticmethod
    def decode(encoded_bytes : bytes):
        index, begin, length = struct.unpack(">III", encoded_bytes[5: 17]) # Skip length and message ID

        return Request(index, begin, length)


# Renamed class to PieceMessage since we already defined Piece class in a different file
class PieceMessage(Message):
    '''
    <length = 9 + X><id = 7><index><begin><block>
    Variable Length
    '''
    def __init__(self, index : int, begin : int, block : int):
        self.index = index
        self.begin = begin
        self.block = block

    def encode(self) -> bytes:
        header = struct.pack(">II", self.index, self.begin) # 8 bytes = two 4 byte integer
        encoding_len = 1 + len(header) + len(self.block)
        return struct.pack(">IB", encoding_len, MessageType.PIECE) + header + self.block
    
    @staticmethod
    def decode(encoded_bytes : bytes):
        length = struct.unpack(">I", encoded_bytes[:4])[0]
        index, begin = struct.unpack(">II", encoded_bytes[5:13])
        block = encoded_bytes[13: + 4 + length]

        return PieceMessage(index, begin, block)

# Used to cancel block requests
# Identical payload to request
class Cancel(Message):
    '''
    <length = 13><id = 8><index><begin><block>
    Variable Length
    '''
    def __init__(self, index : int, begin : int, length : int):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self) -> bytes:
        encoding_len = 13
        return struct.pack(">IBIII", encoding_len, MessageType.CANCEL, self.index, self.begin, self.length)

    @staticmethod
    def decode(encoded_bytes : bytes):
        index, begin, length = struct.unpack(">III", encoded_bytes[5: 17]) # Skip length and message ID

        return Cancel(index, begin, length)


class Port(Message):
    '''
    <length = 3><id = 9><listen port>
    Variable Length
    '''
    def __init__(self, listen_port : int):
        self.listen_port = listen_port # 2 bytes

    def encode(self) -> bytes:
        encoding_len = 3
        return struct.pack(">IBH", encoding_len, MessageType.PORT, self.listen_port)
    
    @staticmethod
    def decode(encoded_bytes : bytes):
        port = struct.unpack(">H", encoded_bytes[5: 7])[0]

        return Port(port)

