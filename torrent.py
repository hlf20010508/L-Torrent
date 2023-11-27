import math

__author__ = 'alexisgallepe'

import hashlib
import time
from bcoding import bencode, bdecode
import os
import requests

from tracker import TRACKERS_LIST


class Torrent(object):
    def __init__(self):
        self.torrent_file = {}
        self.total_length: int = 0
        self.piece_length: int = 0
        self.pieces: int = 0
        self.info_hash: str = ''
        self.peer_id: str = ''
        self.announce_list = []
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
        headers={'User-Agent': 'Mozilla/5.0 (Platform; Security; OS-or-CPU; Localization; rv:1.4) Gecko/20030624 Netscape/7.1 (ax)'}
        response = requests.post(server_url, headers=headers, data={'magnet': magnet_link})
        contents = bdecode(response.content)
        return self.load(contents)
    
    def load_from_path(self, path):
        with open(path, 'rb') as file:
            contents = bdecode(file)
        return self.load(contents)

    def init_files(self):
        # 获取种子中根目录的路径
        root = self.torrent_file['info']['name']
        # 如果有files字段，则表明种子中包含多个文件
        if 'files' in self.torrent_file['info']:
            if not os.path.exists(root):
                # 创建根目录，并定义其权限为没有特殊权限设定（0），所有者读写执行（4+2+1），用户和访客读写（4+2）
                os.mkdir(root, 0o0766 )
            # 遍历根目录下的所有文件路径
            for file in self.torrent_file['info']['files']:
                # 将文件路径的各个部分同根目录拼接起来
                # file["path"]的结构形如["music", "song.mp3"]
                path_file = os.path.join(root, *file["path"])
                # 检查该文件的父路径是否存在，若不存在则创建该父路径
                if not os.path.exists(os.path.dirname(path_file)):
                    os.makedirs(os.path.dirname(path_file))
                # 存储文件路径，并附上文件大小
                self.file_names.append({"path": path_file , "length": file["length"]})
                # 更新种子的总大小
                self.total_length += file["length"]
        # 若没有files字段，说明种子中只有一个文件
        else:
            self.file_names.append({"path": root , "length": self.torrent_file['info']['length']})
            self.total_length = self.torrent_file['info']['length']

    def get_trakers(self):
        trackers_list = TRACKERS_LIST
        if 'announce-list' in self.torrent_file:
            trackers_list.extend(self.torrent_file['announce-list'])
        elif "announce" in self.torrent_file:
            return trackers_list.append(self.torrent_file['announce'])
        return trackers_list

    def generate_peer_id(self):
        seed = str(time.time())
        return hashlib.sha1(seed.encode('utf-8')).digest()
