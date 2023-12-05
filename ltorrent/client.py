__author__ = 'alexisgallepe, L-ING'

import time
from threading import Thread
from ltorrent.peers_manager import PeersPool, PeersScraper, PeersManager
from ltorrent.pieces_manager import PiecesManager
from ltorrent.torrent import Torrent
from ltorrent.message import Request
from ltorrent.log import Logger
from ltorrent.block import State, BLOCK_SIZE


class Client(Thread):
    last_percentage_completed = -1
    last_log_line = ""

    def __init__(self, port, timeout=2, custom_storage=None, stdout=None, sequential=False):
        Thread.__init__(self)
        self.port = port
        self.timeout = timeout
        self.custom_storage = custom_storage
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
        self.sequential = sequential
        self.is_active = True

        self.torrent = {}
        self.selection = []
        self.peers_pool = None
        self.peers_scraper = None
        self.pieces_manager = None
        self.peers_manager = None

        self.last_update = 0
        self.retries = 0

    def load(self, torrent_path='', magnet_link=''):
        if torrent_path:
            self.torrent = Torrent(
                custom_storage=self.custom_storage,
                stdout=self.stdout
            ).load_from_path(path=torrent_path)
        elif magnet_link:
            self.torrent = Torrent(
                custom_storage=self.custom_storage,
                stdout=self.stdout
            ).load_from_magnet(magnet_link=magnet_link)
        else:
            raise Exception("Neither torrent path nor magnet link is provided.")

    def list_file(self):
        if not self.torrent:
            raise Exception("You haven't load torrent file or magnet link.")
        output = '0. All\n'
        for i, file_info in enumerate(self.torrent.file_names):
            output += '%d. \"%s\" %.2fMB\n' % (i + 1, file_info['path'], file_info['length'] / 1024 / 1024)
        self.stdout.FILES(output.strip())

    def select_file(self, selection):
        if not self.torrent:
            raise Exception("You haven't load torrent file or magnet link.")
        if not selection:
            raise Exception("No selection")
        selection = selection.split()
        result = []
        for i in selection:
            # range
            rg = [int(item) for item in i.split('-')]
            if len(rg) > 1:
                rg = range(rg[0], rg[1] + 1)
            result.extend(rg)

        if max(result) > len(self.torrent.file_names) + 1:
            raise Exception('Wrong file number')
        elif 0 in result:
            self.selection = range(0, len(self.torrent.file_names))
        else:
            self.selection = [item - 1 for item in result]

    def run(self):
        try:
            if not self.selection:
                raise Exception("You haven't select file(s).")

            self.peers_pool = PeersPool()

            self.pieces_manager = PiecesManager(
                torrent=self.torrent,
                selection=self.selection,
                custom_storage=self.custom_storage,
                stdout=self.stdout,
                sequential=self.sequential
            )
            self.peers_manager = PeersManager(
                torrent=self.torrent,
                pieces_manager=self.pieces_manager,
                peers_pool=self.peers_pool,
                stdout=self.stdout
            )
            self.peers_scraper = PeersScraper(
                torrent=self.torrent,
                peers_pool=self.peers_pool,
                peers_manager=self.peers_manager,
                pieces_manager=self.pieces_manager,
                port=self.port,
                timeout=self.timeout,
                stdout=self.stdout
            )

            self.peers_scraper.start()
            self.peers_manager.start()

            if len(self.peers_pool.connected_peers) < 1:
                self._exit_threads()
                self.stdout.INFO('Peers not enough')

            self.last_update = time.time()

            if not self.sequential:
                while not self.pieces_manager.all_pieces_completed() and self.is_active:
                    for piece, block_index, block in self.pieces_manager.get_unfull_blocks():
                        if not self.is_active:
                            break
                        
                        if not self.peers_manager.has_unchoked_peers():
                            self.stdout.INFO("No unchocked peers")
                            time.sleep(1)
                            continue
                        
                        piece.update_block_status()

                        if block.state == State.FREE:
                            block.state = State.PENDING
                            block.last_seen = time.time()

                        while True:
                            if not self.is_active:
                                break
                            peer = self.peers_manager.get_random_peer_having_piece(index=piece.piece_index)
                            if peer:
                                break
                            else:
                                time.sleep(0.2)

                        piece_data = Request(
                            piece_index=piece.piece_index,
                            block_offset=block_index * BLOCK_SIZE,
                            block_length=block.block_size
                        ).to_bytes()
                        peer.send_to_peer(msg=piece_data)
                        self.display_progression()
            else:
                for group_index in range(self.pieces_manager.number_of_group):
                    if not self.is_active:
                        break
                    while len(unfull_blocks := self.pieces_manager.get_group_unfull_blocks(group_index)) > 0:
                        if not self.is_active:
                            break
                        for piece, block_index, block in unfull_blocks:
                            if not self.is_active:
                                break

                            if not self.peers_manager.has_unchoked_peers():
                                self.stdout.INFO("No unchocked peers")
                                time.sleep(1)
                                continue

                            piece.update_block_status()

                            if block.state == State.FREE:
                                block.state = State.PENDING
                                block.last_seen = time.time()

                            while True:
                                if not self.is_active:
                                    break
                                peer = self.peers_manager.get_random_peer_having_piece(index=piece.piece_index)
                                if peer:
                                    break
                                else:
                                    time.sleep(0.2)

                            piece_data = Request(
                                piece_index=piece.piece_index,
                                block_offset=block_index * BLOCK_SIZE,
                                block_length=block.block_size
                            ).to_bytes()
                            peer.send_to_peer(msg=piece_data)
                            self.display_progression()
            if self.is_active:
                self.display_progression()
                self._exit_threads()
                self.stdout.INFO("File(s) downloaded successfully.")
            else:
                self._exit_threads()

        except Exception as e:
            try:
                self._exit_threads()
            finally:
                self.stdout.ERROR(e)

    def display_progression(self):
        now = time.time()
        if (now - self.last_update) > 300:
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

        percentage_completed = (self.pieces_manager.completed_size / self.pieces_manager.total_active_size) * 100

        current_log_line = "Connected peers: %d - %.2f%% completed | %d/%d pieces" % (
            number_of_peers,
            percentage_completed,
            self.pieces_manager.completed_pieces,
            self.pieces_manager.number_of_active_pieces
        )

        if current_log_line != self.last_log_line:
            self.stdout.PROGRESS(current_log_line)
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
