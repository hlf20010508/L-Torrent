__author__ = 'alexisgallepe, L-ING'

import time
import os
import peers_manager
import pieces_manager
import torrent
import message


class Client(object):
    last_log_line = ""

    def __init__(self, port, torrent_path='', magnet_link='', timeout=0.5, custom_storage=None):
        if torrent_path:
            self.torrent = torrent.Torrent(custom_storage).load_from_path(torrent_path)
        if magnet_link:
            self.torrent = torrent.Torrent(custom_storage).load_from_magnet(magnet_link)

        self.peers_pool = peers_manager.PeersPool()
        self.peers_scraper = peers_manager.PeersScraper(self.torrent, self.peers_pool, port, timeout=timeout)
        self.pieces_manager = pieces_manager.PiecesManager(self.torrent, custom_storage)
        self.peers_manager = peers_manager.PeersManager(self.torrent, self.pieces_manager, self.peers_pool)

        self.last_update = 0
        self.retries = 0

    def start(self):
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
                piece_data = message.Request(piece_index, block_offset, block_length).to_bytes()
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
            self.peers_pool = peers_manager.PeersPool()
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
    def write(self, file_piece_list, data):
        for file_piece in file_piece_list:
            path_file = os.path.join('downloads', file_piece["path"].split('/')[-1])
            file_offset = file_piece["fileOffset"]
            piece_offset = file_piece["pieceOffset"]
            length = file_piece["length"]

            try:
                f = open(path_file, 'r+b')
            except IOError:
                f = open(path_file, 'wb')
            except:
                print("Can't write to file")
                return

            f.seek(file_offset)
            f.write(data[piece_offset:piece_offset + length])
            f.close()

    def read(self, files, block_offset, block_length):
        file_data_list = []
        for file in files:
            path_file = file["path"]
            file_offset = file["fileOffset"]
            piece_offset = file["pieceOffset"]
            length = file["length"]

            try:
                f = open(path_file, 'rb')
            except:
                print("Can't read file %s" % path_file)
                return
            f.seek(file_offset)
            data = f.read(length)
            file_data_list.append((piece_offset, data))
            f.close()
        file_data_list.sort(key=lambda x: x[0])
        piece = b''.join([data for _, data in file_data_list])
        return piece[block_offset : block_offset + block_length]


if __name__ == '__main__':
    magnet_link = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"
    port = 8080
    timeout = 1
    custom_storage = CustomStorage()
    
    if not os.path.exists('downloads'):
        os.mkdir('downloads')

    client = Client(
        port,
        magnet_link=magnet_link,
        timeout=timeout,
        custom_storage=custom_storage
    )
    client.start()
