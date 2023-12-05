__author__ = 'alexisgallepe, L-ING'

import math
import hashlib
import random
import string
from bcoding import bencode, bdecode
import os
import aiohttp
from ltorrent_async.tracker import TRACKERS_LIST
from ltorrent_async.log import Logger

class Magnet2TorrentException(Exception):
    pass

class Torrent(object):
    def __init__(self, custom_storage=None, stdout=Logger):
        self.torrent_file = {}
        self.total_length: int = 0
        self.piece_length: int = 0
        self.pieces: int = 0
        self.info_hash: str = ''
        self.peer_id: str = ''
        self.announce_list = []
        self.file_names = []
        self.number_of_pieces: int = 0
        self.custom_storage = custom_storage
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()

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

    async def load_from_magnet(self, magnet_link):
        server_url = "https://magnet2torrent.com/upload/"
        headers={'User-Agent': 'Mozilla/5.0 (Platform; Security; OS-or-CPU; Localization; rv:1.4) Gecko/20030624 Netscape/7.1 (ax)'}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(server_url, data={'magnet': magnet_link}, headers=headers, ssl=False) as response:
                try:
                    contents = bdecode(await response.content.read())
                except TypeError:
                    raise Magnet2TorrentException("Failed to decode response content from magnet2torrent.com")

        return self.load(contents=contents)
    
    def load_from_path(self, path):
        with open(path, 'rb') as file:
            contents = bdecode(file)
        return self.load(contents=contents)

    def init_files(self):
        root = self.torrent_file['info']['name']
        if 'files' in self.torrent_file['info']:
            if not self.custom_storage and not os.path.exists(root):
                os.mkdir(path=root, mode=0o0766 )
            for file in self.torrent_file['info']['files']:
                path_file = os.path.join(root, *file["path"])
                if not self.custom_storage and not os.path.exists(path=os.path.dirname(path_file)):
                    os.makedirs(name=os.path.dirname(path_file))
                self.file_names.append({"path": path_file , "length": file["length"]})
                self.total_length += file["length"]
        else:
            self.file_names.append({"path": root , "length": self.torrent_file['info']['length']})
            self.total_length = self.torrent_file['info']['length']

    def get_trakers(self):
        trackers_list = TRACKERS_LIST
        if 'announce-list' in self.torrent_file:
            for sub_announce_list in self.torrent_file['announce-list']:
                trackers_list.extend(sub_announce_list)
        elif "announce" in self.torrent_file:
            return trackers_list.append(self.torrent_file['announce'])
        return trackers_list

    def generate_peer_id(self):
        return '-qBXYZ0-' + ''.join(random.sample(string.ascii_letters + string.digits, 12))
