__author__ = 'alexisgallepe, L-ING'

import hashlib
import math
import time
from ltorrent_async.block import Block, BLOCK_SIZE, State


class Piece(object):
    def __init__(self, piece_index: int, piece_size: int, piece_hash: str, pieces_manager, storage, stdout):
        self.piece_index: int = piece_index
        self.piece_size: int = piece_size
        self.piece_hash: str = piece_hash
        self.pieces_manager = pieces_manager
        self.is_full: bool = False
        self.files = []
        self.number_of_blocks: int = math.ceil(piece_size / BLOCK_SIZE)
        self.blocks: list[Block] = []
        self.storage = storage
        self.is_active = 0
        self.stdout = stdout

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
        return await self.storage.read(self.files, block_offset, block_length)

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
        await self.storage.write(self.files, data)
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
