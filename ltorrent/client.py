__author__ = 'alexisgallepe, L-ING'

import time
from threading import Thread
from ltorrent.peers_manager import PeersPool, PeersScraper, PeersManager
from ltorrent.pieces_manager import PiecesManager, ExitSelectionException
from ltorrent.torrent import Torrent
from ltorrent.message import Request
from ltorrent.log import Logger


class Client(Thread):
    last_percentage_completed = -1
    last_log_line = ""

    def __init__(self, port, torrent_path='', magnet_link='', timeout=1, custom_storage=None, stdout=None, stdin=input):
        Thread.__init__(self)
        self.port = port
        self.torrent_path = torrent_path
        self.magnet_link = magnet_link
        self.timeout = timeout
        self.custom_storage = custom_storage
        self.stdout = stdout
        self.stdin = stdin
        self.is_active = True

        self.torrent = {}
        self.peers_pool = None
        self.peers_scraper = None
        self.pieces_manager = None
        self.peers_manager = None

        self.last_update = 0
        self.retries = 0



    def run(self):
        try:
            if not self.stdout:
                self.stdout = Logger()

            if self.torrent_path:
                self.torrent = Torrent(custom_storage=self.custom_storage).load_from_path(path=self.torrent_path)
            if self.magnet_link:
                self.torrent = Torrent(custom_storage=self.custom_storage).load_from_magnet(magnet_link=self.magnet_link)
            
            self.peers_pool = PeersPool()

            self.peers_scraper = PeersScraper(
                torrent=self.torrent,
                peers_pool=self.peers_pool,
                port=self.port,
                timeout=self.timeout,
                stdout=self.stdout
            )
            self.pieces_manager = PiecesManager(
                torrent=self.torrent,
                custom_storage=self.custom_storage,
                stdout=self.stdout,
                stdin=self.stdin
            )
            self.peers_manager = PeersManager(
                torrent=self.torrent,
                pieces_manager=self.pieces_manager,
                peers_pool=self.peers_pool,
                stdout=self.stdout
            )

            self.peers_scraper.start()
            self.peers_manager.start()

            if len(self.peers_pool.connected_peers) < 1:
                self._exit_threads()
                self.stdout.INFO('Peers not enough')

            self.last_update = time.time()

            while not self.pieces_manager.all_pieces_completed() and self.is_active:
                if not self.peers_manager.has_unchoked_peers():
                    self.stdout.WARNING("No unchocked peers")
                    time.sleep(1)
                    continue

                for piece in self.pieces_manager.pieces:
                    index = piece.piece_index

                    if not self.pieces_manager.pieces[index].is_active:
                        continue

                    if self.pieces_manager.pieces[index].is_full:
                        continue

                    peer = self.peers_manager.get_random_peer_having_piece(index=index)
                    if not peer:
                        continue

                    self.pieces_manager.pieces[index].update_block_status()

                    data = self.pieces_manager.pieces[index].get_empty_block()
                    if not data:
                        continue

                    piece_index, block_offset, block_length = data
                    piece_data = Request(
                        piece_index=piece_index,
                        block_offset=block_offset,
                        block_length=block_length
                    ).to_bytes()
                    peer.send_to_peer(msg=piece_data)

                self.display_progression()

                time.sleep(0.1)
            
            if self.is_active:
                self.display_progression()
                self._exit_threads()
                self.stdout.INFO("File(s) downloaded successfully.")
            else:
                self._exit_threads()

        except ExitSelectionException:
            self.stdout.INFO("File selection cancelled.")
        except Exception as e:
            try:
                self._exit_threads()
            finally:
                self.stdout.ERROR(e)

    def display_progression(self):
        now = time.time()
        if (now - self.last_update) > 60:
            if self.retries > 3:
                self._exit_threads()
                self.stdout.INFO('Too many retries')
                return

            self.stdout.INFO("Timeout")

            self.peers_manager.is_active = False

            for peer in self.peers_manager.peers_pool.connected_peers.values():
                peer.socket.close()
            self.peers_pool = PeersPool()

            self.peers_scraper.start()

            self.peers_manager = PeersManager(
                torrent=self.torrent,
                pieces_manager=self.pieces_manager,
                peers_pool=self.peers_pool,
                stdout=self.stdout
            )
            
            self.peers_manager.start()

            if len(self.peers_pool.connected_peers) < 1:
                self._exit_threads()
                self.stdout.INFO('Peers not enough')
                return
            
            self.retries += 1
            
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
            self.stdout.INFO(current_log_line)
            self.last_log_line = current_log_line
        
        if percentage_completed != self.last_percentage_completed:
            self.last_update = now
            self.last_percentage_completed = percentage_completed

    def _exit_threads(self):
        self.peers_manager.is_active = False
        self.is_active = False


class CustomStorage:
    def __init__(self):
        pass

    def write(self, file_piece_list, data):
        raise Exception("CustomStorage.write not implemented")

    def read(self, files, block_offset, block_length):
        raise Exception("CustomStorage.read not implemented")
