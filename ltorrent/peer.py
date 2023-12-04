__author__ = 'alexisgallepe, L-ING'

import time
import socket
import struct
import bitstring
from ltorrent.message import (
    WrongMessageException,
    UnChoke,
    Interested,
    Handshake,
    KeepAlive,
    MessageDispatcher
)
from ltorrent.log import Logger


class Peer(object):
    def __init__(self, number_of_pieces, ip, peers_manager, pieces_manager, port=6881, stdout=None):
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
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
        self.bit_field = bitstring.BitArray(number_of_pieces)
        self.state = {
            'am_choking': True,
            'am_interested': False,
            'peer_choking': True,
            'peer_interested': False,
        }

    def __hash__(self):
        return "%s:%d" % (self.ip, self.port)

    def connect(self, timeout=2):
        try:
            self.socket = socket.create_connection((self.ip, self.port), timeout=timeout)
            self.socket.setblocking(False)
            self.healthy = True
        except socket.timeout:
            self.stdout.WARNING("Connection timeout in Peer.")
            return False
        except ConnectionRefusedError:
            self.stdout.WARNING("Connection refused in Peer.")
            return False
        except OSError as e:
            # No route to host
            self.stdout.WARNING(e)
            return False
        except Exception as e:
            self.stdout.ERROR("Failed to connect to peer:", e)
            return False

        return True

    def send_to_peer(self, msg):
        try:
            self.socket.send(msg)
            self.last_call = time.time()
        except BrokenPipeError:
            self.healthy = False
            self.stdout.WARNING("Broken pipe. Sending message to a closed peer.")
        except OSError:
            self.healthy = False
            self.stdout.WARNING("Socket closed in Peer")
        except Exception as e:
            self.healthy = False
            self.stdout.ERROR("Failed to send to peer:", e)

    def is_eligible(self):
        now = time.time()
        return (now - self.last_call) > 0.1

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

    def handle_choke(self):
        self.stdout.DEBUG('handle_choke - %s' % self.ip)
        self.state['peer_choking'] = True

    def handle_unchoke(self):
        self.stdout.DEBUG('handle_unchoke - %s' % self.ip)
        self.state['peer_choking'] = False

    def handle_interested(self):
        self.stdout.DEBUG('handle_interested - %s' % self.ip)
        self.state['peer_interested'] = True

        if self.am_choking():
            unchoke = UnChoke().to_bytes()
            self.send_to_peer(msg=unchoke)

    def handle_not_interested(self):
        self.stdout.DEBUG('handle_not_interested - %s' % self.ip)
        self.state['peer_interested'] = False

    def handle_have(self, have):
        """
        :type have: message.Have
        """
        self.stdout.DEBUG('handle_have - ip: %s - piece: %s' % (self.ip, have.piece_index))
        self.bit_field[have.piece_index] = True

        if self.is_choking() and not self.state['am_interested']:
            interested = Interested().to_bytes()
            self.send_to_peer(mgs=interested)
            self.state['am_interested'] = True

    def handle_bitfield(self, bitfield):
        """
        :type bitfield: message.BitField
        """
        self.stdout.DEBUG('handle_bitfield - %s - %s' % (self.ip, bitfield.bitfield))
        self.bit_field = bitfield.bitfield

        if self.is_choking() and not self.state['am_interested']:
            interested = Interested().to_bytes()
            self.send_to_peer(msg=interested)
            self.state['am_interested'] = True

    def handle_request(self, request):
        """
        :type request: message.Request
        """
        self.stdout.DEBUG('handle_request - %s' % self.ip)
        if self.is_interested() and self.is_unchoked():
            self.peers_manager.peer_requests_piece(request=request, peer=self)

    def handle_piece(self, message):
        """
        :type message: message.Piece
        """
        if self.pieces_manager.sequential:
            self.pieces_manager.receive_block_piece_seq(
                piece_index=message.piece_index,
                piece_offset=message.block_offset,
                piece_data=message.block
            )
        else:
            self.pieces_manager.receive_block_piece(
                piece_index=message.piece_index,
                piece_offset=message.block_offset,
                piece_data=message.block
            )

    def handle_cancel(self):
        self.stdout.DEBUG('handle_cancel - %s' % self.ip)

    def handle_port_request(self):
        self.stdout.DEBUG('handle_port_request - %s' % self.ip)

    def _handle_handshake(self):
        try:
            handshake_message = Handshake.from_bytes(payload=self.read_buffer)
            self.has_handshaked = True
            self.read_buffer = self.read_buffer[handshake_message.total_length:]
            self.stdout.DEBUG('handle_handshake - %s' % self.ip)
            return True

        except Exception as e:
            self.stdout.ERROR("First message should always be a handshake message:", e)
            self.healthy = False

        return False

    def _handle_keep_alive(self):
        try:
            keep_alive = KeepAlive.from_bytes(payload=self.read_buffer)
            self.stdout.DEBUG('handle_keep_alive - %s' % self.ip)
        except WrongMessageException:
            # try to handle keep alive message in every loop
            return False
        except Exception as e:
            self.stdout.ERROR("Error KeepALive, need at least 4 bytes, but got %d bytes:" % len(self.read_buffer), e)
            return False

        self.read_buffer = self.read_buffer[keep_alive.total_length:]
        return True

    def get_messages(self):
        while len(self.read_buffer) > 4 and self.healthy:
            if (not self.has_handshaked and self._handle_handshake()) or self._handle_keep_alive():
                continue

            payload_length, = struct.unpack(">I", self.read_buffer[:4])
            total_length = payload_length + 4

            if len(self.read_buffer) < total_length:
                break
            else:
                payload = self.read_buffer[:total_length]
                self.read_buffer = self.read_buffer[total_length:]

            try:
                received_message = MessageDispatcher(payload=payload, stdout=self.stdout).dispatch()
                if received_message:
                    yield received_message
            except WrongMessageException as e:
                self.stdout.ERROR("Wrong message received in peer.Peer.get_messages:", e)
