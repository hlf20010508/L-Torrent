__author__ = 'alexisgallepe, L-ING'

import bitstring
from pubsub import pub
import piece


class PiecesManager(object):
    def __init__(self, torrent, custom_storage=None):
        self.torrent = torrent
        self.number_of_pieces = int(torrent.number_of_pieces)
        self.bitfield = bitstring.BitArray(self.number_of_pieces)
        self.custom_storage = custom_storage
        self.pieces = self._generate_pieces()
        self.selection = self.select_file()
        self.files = self._load_files()
        self.number_of_active_pieces = self.get_active_pieces_num()
        self.complete_pieces = 0

        for file in self.files:
            if file['fileId'] in self.selection:
                id_piece = file['idPiece']
                self.pieces[id_piece].files.append(file)

        # events
        pub.subscribe(self.receive_block_piece, 'PiecesManager.Piece')
        pub.subscribe(self.update_bitfield, 'PiecesManager.PieceCompleted')

    def select_file(self):
        print('0. Exit')
        print('1. All')
        for i, file_info in enumerate(self.torrent.file_names):
            print('%d. \"%s\" %.2fMB' % (i + 2, file_info['path'], file_info['length'] / 1024 / 1024))
        selection = input('Select files: ').split()
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
            exit(0)
        elif 1 in result:
            return range(0, len(self.torrent.file_names))
        else:
            return [item - 2 for item in result]

    def get_active_pieces_num(self):
        count = 0
        for piece in self.pieces:
            if piece.is_active:
                count += 1
        return count

    def update_bitfield(self, piece_index):
        self.bitfield[piece_index] = 1
        self.pieces[piece_index].clear()

    def receive_block_piece(self, piece):
        piece_index, piece_offset, piece_data = piece

        if self.pieces[piece_index].is_full:
            return

        self.pieces[piece_index].set_block(piece_offset, piece_data)

        if self.pieces[piece_index].are_all_blocks_full():
            if self.pieces[piece_index].set_to_full():
                self.complete_pieces +=1


    def get_block(self, piece_index, block_offset, block_length):
        for piece in self.pieces:
            if piece_index == piece.piece_index:
                if piece.is_full:
                    return piece.get_block(block_offset, block_length)
                else:
                    break

        return None

    def all_pieces_completed(self):
        for piece in self.pieces:
            if piece.is_active and not piece.is_full:
                return False

        return True

    def _generate_pieces(self):
        pieces = []
        last_piece = self.number_of_pieces - 1

        for i in range(self.number_of_pieces):
            start = i * 20
            end = start + 20

            if i != last_piece:
                pieces.append(piece.Piece(i, self.torrent.piece_length, self.torrent.pieces[start:end], self.custom_storage))
            else:
                piece_length = self.torrent.total_length - (self.number_of_pieces - 1) * self.torrent.piece_length
                pieces.append(piece.Piece(i, piece_length, self.torrent.pieces[start:end], self.custom_storage))

        return pieces

    def _load_files(self):
        files = []
        piece_offset = 0
        piece_size_used = 0
        for i, f in enumerate(self.torrent.file_names):
            current_size_file = f["length"]
            file_offset = 0
            is_active = 1
            if i not in self.selection:
                is_active = 0
            while current_size_file > 0:
                id_piece = int(piece_offset / self.torrent.piece_length)
                self.pieces[id_piece].is_active += is_active
                piece_size = self.pieces[id_piece].piece_size - piece_size_used

                if current_size_file - piece_size >= 0:
                    current_size_file -= piece_size
                    file = {
                        "length": piece_size,
                        "idPiece": id_piece,
                        "fileOffset": file_offset,
                        "pieceOffset": piece_size_used,
                        "path": f["path"],
                        'fileId': i
                    }
                    piece_offset += piece_size
                    file_offset += piece_size
                    piece_size_used = 0
                else:
                    file = {
                        "length": current_size_file,
                        "idPiece": id_piece,
                        "fileOffset": file_offset,
                        "pieceOffset": piece_size_used,
                        "path": f["path"],
                        'fileId': i
                    }
                    piece_offset += current_size_file
                    file_offset += current_size_file
                    piece_size_used += current_size_file
                    current_size_file = 0

                files.append(file)
        return files
