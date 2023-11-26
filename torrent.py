import math

__author__ = 'alexisgallepe'

import hashlib
import time
from bcoding import bencode, bdecode
import os
import requests


class Torrent(object):
    def __init__(self):
        self.torrent_file = {}
        self.total_length: int = 0
        self.piece_length: int = 0
        self.pieces: int = 0
        self.info_hash: str = ''
        self.peer_id: str = ''
        self.announce_list = ''
        self.file_names = []
        self.number_of_pieces: int = 0

    def load(self, contents):
        self.torrent_file = contents
        self.piece_length = self.torrent_file['info']['piece length']
        self.pieces = self.torrent_file['info']['pieces']
        raw_info_hash = bencode(self.torrent_file['info'])
        self.info_hash = hashlib.sha1(raw_info_hash).digest()
        self.peer_id = self.generate_peer_id()
        self.announce_list = self.get_trakers()
        self.init_files()
        self.number_of_pieces = math.ceil(self.total_length / self.piece_length)

        assert(self.total_length > 0)
        assert(len(self.file_names) > 0)

        return self

    def load_from_magnet(self, magnet_link):
        server_url = "https://magnet2torrent.com/upload/"
        response = requests.post(server_url, data={'magnet': magnet_link})
        print(response.status_code)
        print(response.headers)
        contents = bdecode(response.content)
        return self.load(contents)
    
    def load_from_path(self, path):
        with open(path, 'rb') as file:
            contents = bdecode(file)
        return self.load(contents)

    def init_files(self):
        root = self.torrent_file['info']['name']

        if 'files' in self.torrent_file['info']:
            for file in self.torrent_file['info']['files']:
                path_file = os.path.join(root, *file["path"])

                self.file_names.append({"path": path_file , "length": file["length"]})
                self.total_length += file["length"]

        else:
            self.file_names.append({"path": root , "length": self.torrent_file['info']['length']})
            self.total_length = self.torrent_file['info']['length']

    def get_trakers(self):
        if 'announce-list' in self.torrent_file:
            return self.torrent_file['announce-list']
        else:
            return [[self.torrent_file['announce']]]

    def generate_peer_id(self):
        seed = str(time.time())
        return hashlib.sha1(seed.encode('utf-8')).digest()
