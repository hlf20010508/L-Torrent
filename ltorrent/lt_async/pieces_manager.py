__author__ = 'alexisgallepe, L-ING'

import bitstring
from ltorrent.lt_async.piece import Piece
from ltorrent.lt_async.log import Logger

class ExitSelectionException(Exception):
    pass

class PiecesManager(object):
    def __init__(self, torrent, selection, custom_storage=None, stdout=None):
        self.torrent = torrent
        self.number_of_pieces = int(torrent.number_of_pieces)
        self.bitfield = bitstring.BitArray(self.number_of_pieces)
        self.custom_storage = custom_storage
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
        self.pieces = self._generate_pieces()
        self.selection = selection
        self.files = self._load_files()
        self.number_of_active_pieces = self.get_active_pieces_num()
        self.completed_pieces = 0
        self.completed_size = 0

        for file in self.files:
            if file['fileId'] in self.selection:
                id_piece = file['idPiece']
                self.pieces[id_piece].files.append(file)

    def get_active_pieces_num(self):
        count = 0
        for piece in self.pieces:
            if piece.is_active:
                count += 1
        return count

    def update_bitfield(self, piece_index):
        self.bitfield[piece_index] = 1

    async def receive_block_piece(self, piece_index, piece_offset, piece_data):
        if self.pieces[piece_index].is_full:
            return

        self.pieces[piece_index].set_block(offset=piece_offset, data=piece_data)

        if self.pieces[piece_index].are_all_blocks_full():
            if await self.pieces[piece_index].set_to_full():
                self.completed_pieces +=1


    async def get_block(self, piece_index, block_offset, block_length):
        for piece in self.pieces:
            if piece_index == piece.piece_index:
                if piece.is_full:
                    return await piece.get_block(block_offset=block_offset, block_length=block_length)
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
                pieces.append(Piece(
                    piece_index=i,
                    piece_size=self.torrent.piece_length,
                    piece_hash=self.torrent.pieces[start:end],
                    pieces_manager=self,
                    custom_storage=self.custom_storage,
                    stdout=self.stdout
                ))
            else:
                piece_length = self.torrent.total_length - (self.number_of_pieces - 1) * self.torrent.piece_length
                pieces.append(Piece(
                    piece_index=i,
                    piece_size=piece_length,
                    piece_hash=self.torrent.pieces[start:end],
                    pieces_manager=self,
                    custom_storage=self.custom_storage,
                    stdout=self.stdout
                ))

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
