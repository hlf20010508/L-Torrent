__author__ = 'alexisgallepe, L-ING'

import time
import asyncio
import struct
import bitstring
from ltorrent_async.message import (
    WrongMessageException,
    UnChoke,
    Interested,
    Handshake,
    KeepAlive,
    MessageDispatcher
)
from ltorrent_async.async_tcp import AsyncTCPClient


class Peer(object):
    def __init__(self, number_of_pieces, peers_manager, pieces_manager, stdout, ip, port=6881):
        self.last_call = 0.0
        self.has_handshaked = False
        self.healthy = False
        self.read_buffer = b''
        self.socket = None
        self.ip = ip
        self.peers_manager = peers_manager
        self.pieces_manager = pieces_manager
        self.port = port
        self.number_of_pieces = number_of_pieces
        self.stdout = stdout
        self.bit_field = bitstring.BitArray(number_of_pieces)
        self.state = {
            'am_choking': True,
            'am_interested': False,
            'peer_choking': True,
            'peer_interested': False,
        }
        self.timeout_num = 0


    def __hash__(self):
        return "%s:%d" % (self.ip, self.port)

    async def connect(self, timeout=2):
        try:
            self.socket = AsyncTCPClient()
            await self.socket.create_connection(self.ip, self.port, timeout=timeout)
            self.healthy = True
        except asyncio.TimeoutError:
            await self.stdout.WARNING("Connection timeout in Peer.")
            return False
        except OSError as e:
            # Network is unreachable
            await self.stdout.WARNING(e)
            return False
        except Exception as e:
            await self.stdout.ERROR("Failed to connect to peer:", e)
            return False

        return True

    async def send_to_peer(self, msg):
        try:
            await self.socket.send(msg)
            self.last_call = time.time()
        except ConnectionResetError:
            self.healthy = False
            await self.stdout.WARNING("Connection reset by peer in send_to_peer")
        except BrokenPipeError:
            self.healthy = False
            await self.stdout.WARNING("Broken pipe. Sending message to a closed peer.")
        except OSError:
            self.healthy = False
            await self.stdout.WARNING("Socket closed in Peer")
        except Exception as e:
            self.healthy = False
            await self.stdout.ERROR("Failed to send to peer:", e)

    def is_eligible(self):
        now = time.time()
        return (now - self.last_call) > 0.2

    def has_piece(self, index):
        return self.bit_field[index]

    def am_choking(self):
        return self.state['am_choking']

    def am_unchoking(self):
        return not self.am_choking()

    def is_choking(self):
        return self.state['peer_choking']

    def is_unchoked(self):
        return not self.is_choking()

    def is_interested(self):
        return self.state['peer_interested']

    def am_interested(self):
        return self.state['am_interested']

    async def handle_choke(self):
        await self.stdout.DEBUG('handle_choke - %s' % self.ip)
        self.state['peer_choking'] = True

    async def handle_unchoke(self):
        await self.stdout.DEBUG('handle_unchoke - %s' % self.ip)
        self.state['peer_choking'] = False

    async def handle_interested(self):
        await self.stdout.DEBUG('handle_interested - %s' % self.ip)
        self.state['peer_interested'] = True

        if self.am_choking():
            unchoke = UnChoke().to_bytes()
            await self.send_to_peer(msg=unchoke)

    async def handle_not_interested(self):
        await self.stdout.DEBUG('handle_not_interested - %s' % self.ip)
        self.state['peer_interested'] = False

    async def handle_have(self, have):
        """
        :type have: message.Have
        """
        await self.stdout.DEBUG('handle_have - ip: %s - piece: %s' % (self.ip, have.piece_index))
        self.bit_field[have.piece_index] = True

        if self.is_choking() and not self.state['am_interested']:
            interested = Interested().to_bytes()
            await self.send_to_peer(mgs=interested)
            self.state['am_interested'] = True

    async def handle_bitfield(self, bitfield):
        """
        :type bitfield: message.BitField
        """
        await self.stdout.DEBUG('handle_bitfield - %s - %s' % (self.ip, bitfield.bitfield))
        self.bit_field = bitfield.bitfield

        if self.is_choking() and not self.state['am_interested']:
            interested = Interested().to_bytes()
            await self.send_to_peer(msg=interested)
            self.state['am_interested'] = True

    async def handle_request(self, request):
        """
        :type request: message.Request
        """
        await self.stdout.DEBUG('handle_request - %s' % self.ip)
        if self.is_interested() and self.is_unchoked():
            await self.peers_manager.peer_requests_piece(request, self)

    async def handle_piece(self, message):
        """
        :type message: message.Piece
        """
        # await self.stdout.DEBUG('handle_piece - %s' % self.ip)
        if self.pieces_manager.sequential:
            await self.pieces_manager.receive_block_piece_seq(
                piece_index=message.piece_index,
                piece_offset=message.block_offset,
                piece_data=message.block
            )
        else:
            await self.pieces_manager.receive_block_piece(
                piece_index=message.piece_index,
                piece_offset=message.block_offset,
                piece_data=message.block
            )

    async def handle_cancel(self):
        await self.stdout.DEBUG('handle_cancel - %s' % self.ip)

    async def handle_port_request(self):
        await self.stdout.DEBUG('handle_port_request - %s' % self.ip)

    async def _handle_handshake(self):
        try:
            handshake_message = Handshake.from_bytes(payload=self.read_buffer)
            self.has_handshaked = True
            self.read_buffer = self.read_buffer[handshake_message.total_length:]
            await self.stdout.DEBUG('handle_handshake - %s' % self.ip)
            return True

        except Exception as e:
            await self.stdout.ERROR("First message should always be a handshake message:", e)
            self.healthy = False

        return False

    async def _handle_keep_alive(self):
        try:
            keep_alive = KeepAlive.from_bytes(payload=self.read_buffer)
            await self.stdout.DEBUG('handle_keep_alive - %s' % self.ip)
        except WrongMessageException:
            # try to handle keep alive message in every loop
            return False
        except Exception as e:
            await self.stdout.ERROR("Error KeepALive, need at least 4 bytes, but got %d bytes:" % len(self.read_buffer), e)
            return False

        self.read_buffer = self.read_buffer[keep_alive.total_length:]
        return True

    async def get_messages(self):
        while len(self.read_buffer) > 4 and self.healthy:
            if (not self.has_handshaked and await self._handle_handshake()) or await self._handle_keep_alive():
                continue

            payload_length, = struct.unpack(">I", self.read_buffer[:4])
            total_length = payload_length + 4

            if len(self.read_buffer) < total_length:
                break
            else:
                payload = self.read_buffer[:total_length]
                self.read_buffer = self.read_buffer[total_length:]

            try:
                received_message = await MessageDispatcher(payload=payload, stdout=self.stdout).dispatch()
                if received_message:
                    yield received_message
            except WrongMessageException as e:
                await self.stdout.ERROR("Wrong message received in peer.Peer.get_messages:", e)
