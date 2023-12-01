__author__ = 'alexisgallepe, L-ING'

import time
import os
from threading import Thread
from ltorrent.peers_manager import PeersPool, PeersScraper, PeersManager
from ltorrent.pieces_manager import PiecesManager
from ltorrent.torrent import Torrent
from ltorrent.message import Request


class Client(Thread):
    last_log_line = ""

    def __init__(self, port, torrent_path='', magnet_link='', timeout=1, custom_storage=None):
        Thread.__init__(self)
        self.port = port
        self.torrent_path = torrent_path
        self.magnet_link = magnet_link
        self.timeout = timeout
        self.custom_storage = custom_storage

        self.torrent = {}
        self.peers_pool = None
        self.peers_scraper = None
        self.pieces_manager = None
        self.peers_manager = None

        self.last_update = 0
        self.retries = 0

    def run(self):
        if self.torrent_path:
            self.torrent = Torrent(self.custom_storage).load_from_path(self.torrent_path)
        if self.magnet_link:
            self.torrent = Torrent(self.custom_storage).load_from_magnet(self.magnet_link)
        
        self.peers_pool = PeersPool()

        self.peers_scraper = PeersScraper(self.torrent, self.peers_pool, self.port, timeout=self.timeout)
        self.pieces_manager = PiecesManager(self.torrent, self.custom_storage)
        self.peers_manager = PeersManager(self.torrent, self.pieces_manager, self.peers_pool)

        self.peers_scraper.start()
        self.peers_manager.start()

        if len(self.peers_pool.connected_peers) < 1:
            self._exit_threads()

        self.last_update = time.time()

        while not self.pieces_manager.all_pieces_completed():
            if not self.peers_manager.has_unchoked_peers():
                print("No unchocked peers")
                time.sleep(1)
                continue

            for piece in self.pieces_manager.pieces:
                index = piece.piece_index

                if not self.pieces_manager.pieces[index].is_active:
                    continue

                if self.pieces_manager.pieces[index].is_full:
                    continue

                peer = self.peers_manager.get_random_peer_having_piece(index)
                if not peer:
                    continue

                self.pieces_manager.pieces[index].update_block_status()

                data = self.pieces_manager.pieces[index].get_empty_block()
                if not data:
                    continue

                piece_index, block_offset, block_length = data
                piece_data = Request(piece_index, block_offset, block_length).to_bytes()
                peer.send_to_peer(piece_data)

            self.display_progression()

            time.sleep(0.1)

        self.display_progression()

        print("File(s) downloaded successfully.")

        self._exit_threads()

    def display_progression(self):
        now = time.time()
        if (now - self.last_update) > 60:
            print("Timeout")
            for peer in self.peers_manager.peers_pool.connected_peers.values():
                peer.socket.close()
            self.peers_pool = PeersPool()
            self.peers_scraper.start()
            self.retries += 1
            if self.retries > 3:
                print('Too many retries')
                self._exit_threads()
            self.last_update = time.time()
            return

        number_of_peers = self.peers_manager.unchoked_peers_count()
        percentage_completed = (self.pieces_manager.complete_pieces / self.pieces_manager.number_of_active_pieces) * 100

        current_log_line = "Connected peers: %d - %.2f%% completed | %d/%d pieces" % (
            number_of_peers,
            percentage_completed,
            self.pieces_manager.complete_pieces,
            self.pieces_manager.number_of_active_pieces
        )

        if current_log_line != self.last_log_line:
            self.last_update = now
            print(current_log_line)

        self.last_log_line = current_log_line

    def _exit_threads(self):
        self.peers_manager.is_active = False
        os._exit(0)


class CustomStorage:
    def __init__(self):
        pass

    def write(self, file_piece_list, data):
        raise Exception("CustomStorage.write not implemented")

    def read(self, files, block_offset, block_length):
        raise Exception("CustomStorage.read not implemented")
