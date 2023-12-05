__author__ = 'alexisgallepe, L-ING'

import math
import bitstring
from ltorrent.piece import Piece
from ltorrent.block import State

# 8 * 1024 * 1024
GROUP_MAX_SIZE = 8388608

class ExitSelectionException(Exception):
    pass

class PiecesManager(object):
    def __init__(self, torrent, selection, storage, stdout, sequential=False):
        self.torrent = torrent
        self.number_of_pieces = int(torrent.number_of_pieces)
        self.bitfield = bitstring.BitArray(self.number_of_pieces)
        self.storage = storage
        self.stdout = stdout
        self.sequential = sequential
        self.pieces = self._generate_pieces()
        self.group_pieces_num = GROUP_MAX_SIZE // self.pieces[0].piece_size
        self.number_of_group = math.ceil(self.number_of_pieces / self.group_pieces_num)
        self.selection = selection
        self.total_active_size = 0
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
        self.pieces[piece_index].clear()

    def receive_block_piece(self, piece_index, piece_offset, piece_data):
        if self.pieces[piece_index].is_full:
            return

        self.pieces[piece_index].set_block(offset=piece_offset, data=piece_data)

        if self.pieces[piece_index].are_all_blocks_full():
            if self.pieces[piece_index].set_to_full():
                self.completed_pieces +=1

    def receive_block_piece_seq(self, piece_index, piece_offset, piece_data):
        group_index = piece_index // self.group_pieces_num
        if self.pieces[piece_index].is_full:
            return
        self.pieces[piece_index].set_block(offset=piece_offset, data=piece_data)

        if self.is_group_full(group_index):
            self.write_group(group_index)

    def get_unfull_blocks(self):
        block_list = []
        for piece in self.pieces:
            if not piece.is_active:
                continue
            if piece.is_full:
                continue
            for block_index, block in enumerate(piece.blocks):
                if block.state == State.FULL:
                    continue
                block_list.append((piece, block_index, block))
        return block_list

    def get_group_unfull_blocks(self, group_index):
        block_list = []
        for piece in self.get_group_pieces(group_index):
            if not piece.is_active:
                continue
            if piece.is_full:
                continue
            for block_index, block in enumerate(piece.blocks):
                if block.state == State.FULL:
                    continue
                block_list.append((piece, block_index, block))
        return block_list

    def get_group_pieces(self, group_index):
        return self.pieces[group_index * self.group_pieces_num : (group_index + 1) * self.group_pieces_num]

    def valid_group_pieces(self, group_index):
        for piece in self.get_group_pieces(group_index):
            if piece.is_active and not piece.is_full and piece.are_all_blocks_full():
                data = piece._merge_blocks()
                if not piece._valid_blocks(piece_raw_data=data):
                    piece._init_blocks()
                    return False
                piece.is_full = True
                self.completed_pieces += 1
        return True

    def is_group_full(self, group_index):
        if self.valid_group_pieces(group_index):
            for piece in self.get_group_pieces(group_index):
                if piece.is_active and not piece.is_full:
                    return False
            return True
        else:
            return False

    def write_group(self, group_index):
        group_data = b''
        group_file_list = []
        data_index = 0
        for piece in self.get_group_pieces(group_index):
            if piece.is_active:
                piece_data = piece._merge_blocks()
                for piece_file in piece.files:
                    if not self.is_piece_file_in_group_file_list(piece_file, group_file_list):
                        group_file_list.append({
                            'path': piece_file['path'],
                            'fileOffset': piece_file["fileOffset"],
                            'pieceOffset': data_index + piece_file['pieceOffset'],
                            'length': 0
                        })
                    for group_file in group_file_list:
                        if group_file['path'] == piece_file['path']:
                            group_file['length'] += piece_file['length']
                            break
                self.update_bitfield(piece.piece_index)
                group_data += piece_data
            else:
                group_data += b'0' * piece.piece_size

            data_index += piece.piece_size

        self.storage.write(group_file_list, group_data)
        
        for piece in self.get_group_pieces(group_index):
            piece.clear()
                    
    def is_piece_file_in_group_file_list(self, piece_file, group_file_list):
        for group_file in group_file_list:
            if piece_file['path'] == group_file['path']:
                return True
        return False

    def get_block(self, piece_index, block_offset, block_length):
        for piece in self.pieces:
            if piece_index == piece.piece_index:
                if piece.is_full:
                    return piece.get_block(block_offset=block_offset, block_length=block_length)
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
                    storage=self.storage,
                    stdout=self.stdout
                ))
            else:
                piece_length = self.torrent.total_length - (self.number_of_pieces - 1) * self.torrent.piece_length
                pieces.append(Piece(
                    piece_index=i,
                    piece_size=piece_length,
                    piece_hash=self.torrent.pieces[start:end],
                    pieces_manager=self,
                    storage=self.storage,
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
                id_piece = piece_offset // self.torrent.piece_length
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

        for piece in self.pieces:
            if piece.is_active:
                self.total_active_size += piece.piece_size

        return files
