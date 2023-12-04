__author__ = 'alexisgallepe, L-ING'

import hashlib
import math
import time
from ltorrent.block import Block, BLOCK_SIZE, State
from ltorrent.lt_async.log import Logger


class Piece(object):
    def __init__(self, piece_index: int, piece_size: int, piece_hash: str, pieces_manager, custom_storage=None, stdout=None):
        self.piece_index: int = piece_index
        self.piece_size: int = piece_size
        self.piece_hash: str = piece_hash
        self.pieces_manager = pieces_manager
        self.is_full: bool = False
        self.files = []
        self.number_of_blocks: int = math.ceil(piece_size / BLOCK_SIZE)
        self.blocks: list[Block] = []
        self.custom_storage = custom_storage
        self.is_active = 0
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()

        self._init_blocks()

    def update_block_status(self):  # if block is pending for too long : set it free
        for i, block in enumerate(self.blocks):
            if block.state == State.PENDING and (time.time() - block.last_seen) > 5:
                self.blocks[i] = Block()

    def set_block(self, offset, data):
        index = offset // BLOCK_SIZE

        if not self.is_full and not self.blocks[index].state == State.FULL:
            self.blocks[index].data = data
            self.blocks[index].state = State.FULL
            self.pieces_manager.completed_size += self.blocks[index].block_size

    async def get_block(self, block_offset, block_length):
        if self.custom_storage:
            return await self.custom_storage.read(self.files, block_offset, block_length)

        file_data_list = []
        for file in self.files:
            path_file = file["path"]
            file_offset = file["fileOffset"]
            piece_offset = file["pieceOffset"]
            length = file["length"]

            try:
                f = open(path_file, 'rb')
            except Exception as e:
                await self.stdout.ERROR("Can't read file %s:" % path_file, e)
                return

            f.seek(file_offset)
            data = f.read(length)
            file_data_list.append((piece_offset, data))
            f.close()

        file_data_list.sort(key=lambda x: x[0])
        piece = b''.join([data for _, data in file_data_list])
        return piece[block_offset : block_offset + block_length]

    def get_empty_block(self):
        if self.is_full:
            return None

        for block_index, block in enumerate(self.blocks):
            if block.state == State.FREE:
                self.blocks[block_index].state = State.PENDING
                self.blocks[block_index].last_seen = time.time()
                return self.piece_index, block_index * BLOCK_SIZE, block.block_size

        return None

    def are_all_blocks_full(self):
        for block in self.blocks:
            if block.state == State.FREE or block.state == State.PENDING:
                return False

        return True

    async def set_to_full(self):
        data = self._merge_blocks()

        if not await self._valid_blocks(piece_raw_data=data):
            self._init_blocks()
            return False

        self.is_full = True
        if self.custom_storage:
            await self.custom_storage.write(self.files, data)
        else:
            await self._write_piece_on_disk(data)
        self.clear()
        self.pieces_manager.update_bitfield(self.piece_index)

        return True

    def _init_blocks(self):
        self.blocks = []

        if self.number_of_blocks > 1:
            for _ in range(self.number_of_blocks):
                self.blocks.append(Block())

            # Last block of last piece, the special block
            if (self.piece_size % BLOCK_SIZE) > 0:
                self.blocks[self.number_of_blocks - 1].block_size = self.piece_size % BLOCK_SIZE

        else:
            self.blocks.append(Block(block_size=int(self.piece_size)))

    def clear(self):
        for block in self.blocks:
            block.data = b''

    async def _write_piece_on_disk(self, data):
        for file in self.files:
            path_file = file["path"]
            file_offset = file["fileOffset"]
            piece_offset = file["pieceOffset"]
            length = file["length"]

            try:
                f = open(path_file, 'r+b')  # Already existing file
            except IOError:
                f = open(path_file, 'wb')  # New file
            except Exception as e:
                await self.stdout.ERROR("Can't write to file:", e)
                return

            f.seek(file_offset)
            f.write(data[piece_offset:piece_offset + length])
            f.close()

    def _merge_blocks(self):
        buf = b''

        for block in self.blocks:
            buf += block.data

        return buf

    async def _valid_blocks(self, piece_raw_data):
        hashed_piece_raw_data = hashlib.sha1(piece_raw_data).digest()

        if hashed_piece_raw_data == self.piece_hash:
            return True

        await self.stdout.WARNING("Error Piece Hash", "{} : {}".format(hashed_piece_raw_data, self.piece_hash))
        return False
