import sys
from block import State

__author__ = 'alexisgallepe'

import time
import peers_manager
import pieces_manager
import torrent
import os
import message


class Client(object):
    percentage_completed = -1
    last_log_line = ""

    def __init__(self, magnet_link, port, timeout=0.5):
        self.torrent = torrent.Torrent().load_from_magnet(magnet_link)
        # self.tracker = tracker.Tracker(self.torrent, port, timeout=timeout)
        self.peers_pool = peers_manager.PeersPool()
        self.peers_scraper = peers_manager.PeersScraper(self.torrent, self.peers_pool, port, timeout=timeout)
        self.pieces_manager = pieces_manager.PiecesManager(self.torrent)
        self.peers_manager = peers_manager.PeersManager(self.torrent, self.pieces_manager, self.peers_pool)

        self.peers_scraper.run()
        self.peers_manager.start()
        # print("PeersManager Started")
        # print("PiecesManager Started")
        # self.tracker.find_peers()

    def start(self):
        # peers_dict = self.tracker.get_peers_from_trackers()
        # self.peers_manager.add_peers(peers_dict.values())

        while not self.pieces_manager.all_pieces_completed():
            if not self.peers_manager.has_unchoked_peers():
                # time.sleep(1)
                print("No unchocked peers")
                self._exit_threads()
                # continue

            for piece in self.pieces_manager.pieces:
                index = piece.piece_index

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

        print("File(s) downloaded successfully.")
        self.display_progression()

        self._exit_threads()

    def display_progression(self):
        new_progression = 0

        for i in range(self.pieces_manager.number_of_pieces):
            for j in range(self.pieces_manager.pieces[i].number_of_blocks):
                if self.pieces_manager.pieces[i].blocks[j].state == State.FULL:
                    new_progression += len(self.pieces_manager.pieces[i].blocks[j].data)

        if new_progression == self.percentage_completed:
            return

        number_of_peers = self.peers_manager.unchoked_peers_count()
        percentage_completed = float((float(new_progression) / self.torrent.total_length) * 100)

        current_log_line = "Connected peers: {} - {}% completed | {}/{} pieces".format(
            number_of_peers,
            round(percentage_completed, 2),
            self.pieces_manager.complete_pieces,
            self.pieces_manager.number_of_pieces
        )
        if current_log_line != self.last_log_line:
            print(current_log_line)

        self.last_log_line = current_log_line
        self.percentage_completed = new_progression

    def _exit_threads(self):
        self.peers_manager.is_active = False
        os._exit(0)


if __name__ == '__main__':
    magnet_link = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"
    port = 8080
    timeout = 2
    run = Client(magnet_link, port, timeout)
    run.start()
