# encoder: https://pypi.org/project/bencode.py/
import bencodepy as b
import hashlib
from urllib.parse import urlparse, urlunparse

class Torrent:
    def __init__(self, filepath : str):
        self.filepath = filepath
        self.piece_idx = -1
        self.info = {}
        self.parseFile()

    # parse a given torrent file and establish instance vars
    def parseFile(self):
        # open and read file
        file = open(self.filepath, "rb")
        content = file.read()
        # begin reading and filling instance vars
        file_content = b.decode(content)
        self.info = file_content[b'info']
        self.tracker_url_parse = urlparse(file_content[b'announce'].decode('utf-8'))
        self.tracker_base_url = self.tracker_url_parse.netloc.split(":")[0]
        self.tracker_port = 6969 if len(self.tracker_url_parse.netloc.split(":")) == 1 else  int(self.tracker_url_parse.netloc.split(":")[-1])
        
        self.piece_len = self.info[b'piece length']
        self.filename = self.info[b'name'].decode('utf-8')
        self.file_len = self.info[b'length'] if b'length' in self.info.keys() else self.info[b'files'][0][b'length']
        
        # fill with SHA-1 hash values of each piece, NOT 
        pieces_str = self.info[b'pieces']
        self.pieces = [pieces_str[i:i+20] for i in range(0, len(pieces_str), 20)]
        

    # returns the size of each piece in bytes
    def getPieceLen(self):
        return self.piece_len
    
    # returns the next SHA-1 hash value for the corresponding piece, None if none left
    # returns as bytes, not string
    def nextPieceHash(self):
        self.piece_idx += 1
        if self.piece_idx >= len(self.pieces):
            return None
        return self.pieces[self.piece_idx]

    # based on id, get the hash of piece
    # returns as bytes, not string
    def getPieceHash(self, id):
        if id >= len(self.pieces):
            return None
        return self.pieces[id]

    # return advertised file name (advisory)
    def getFileName(self):
        return self.filename

    # return total size of file in bytes
    def getFileSize(self):
        return self.file_len

    # returns the URL for the tracker we need to contact
    def getTrackerURL(self):
        # return self.tracker_base_url
        return self.tracker_url_parse.geturl()
    
    def getInfoHash(self):
        return hashlib.sha1(b.encode(self.info)).digest()

    def getTrackerPort(self):
        return self.tracker_port
    
    def getPieces(self):
        return self.pieces
    
    def canScrape(self):
        path = self.tracker_url_parse.path

        # Find the last slash in the path
        last_slash_index = path.rfind('/')
        if last_slash_index == -1:
            return False

        last_segment = path[last_slash_index + 1:]

        # Check if the last path segment starts with 'announce'
        if not last_segment.startswith('announce'):
            return False
        return True
