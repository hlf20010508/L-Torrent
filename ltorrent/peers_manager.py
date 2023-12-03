__author__ = 'alexisgallepe, L-ING'

import select
from threading import Thread, BoundedSemaphore
from pubsub import pub
import socket
import random
import requests
from bcoding import bdecode
import struct
from urllib.parse import urlparse
import ipaddress
import queue
import urllib3
from ltorrent.message import (
    UdpTrackerConnection,
    UdpTrackerAnnounce,
    UdpTrackerAnnounceOutput,
    Handshake,
    Piece,
    Message,
    Choke,
    UnChoke,
    Interested,
    NotInterested,
    Have,
    BitField,
    Request,
    Cancel,
    Port,
    KeepAlive
)
from ltorrent.peer import Peer
from ltorrent.log import Logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

THREAD_MAX_NUM = 10
THREAD_SEMA = BoundedSemaphore(THREAD_MAX_NUM)


class SockAddr:
    def __init__(self, ip, port, allowed=True):
        self.ip = ip
        self.port = port
        self.allowed = allowed

    def __hash__(self):
        return "%s:%d" % (self.ip, self.port)


class PeersPool:
    dict_sock_addr = {}
    connected_peers = {}


class HTTPScraper(Thread):
    def __init__(self, torrent, tracker, peers_pool, port=6881, timeout=1, stdout=None):
        Thread.__init__(self)
        self.torrent = torrent
        self.tracker = tracker
        self.peers_pool = peers_pool
        self.port = port
        self.timeout = timeout
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
    
    def run(self):
        THREAD_SEMA.acquire()
        try:
            torrent = self.torrent
            tracker = self.tracker
            params = {
                'info_hash': torrent.info_hash,
                'peer_id': torrent.peer_id,
                'uploaded': 0,
                'downloaded': 0,
                'port': self.port,
                'left': torrent.total_length,
                'event': 'started'
            }
            try:
                answer_tracker = requests.get(url=tracker, params=params, verify=False, timeout=self.timeout)
            except OSError:
                self.stdout.WARNING("Failed to visit tracker in http scraper:", tracker)
                return

            try:
                list_peers = bdecode(answer_tracker.content)
            except TypeError:
                self.stdout.WARNING("Failed to decode response content from tracker:", tracker)
                return

            offset=0
            if 'peers' in list_peers:
                peers = list_peers['peers']
            else:
                return
            if not type(peers) == list:
                '''
                - Handles bytes form of list of peers
                - IP address in bytes form:
                    - Size of each IP: 6 bytes
                    - The first 4 bytes are for IP address
                    - Next 2 bytes are for port number
                - To unpack initial 4 bytes !i (big-endian, 4 bytes) is used.
                - To unpack next 2 byets !H(big-endian, 2 bytes) is used.
                '''
                for _ in range(len(list_peers['peers'])//6):
                    ip = struct.unpack_from("!i", list_peers['peers'], offset)[0]
                    ip = socket.inet_ntoa(struct.pack("!i", ip))
                    offset += 4
                    port = int(struct.unpack_from("!H",list_peers['peers'], offset)[0])
                    offset += 2
                    s = SockAddr(ip=ip, port=port)
                    self.peers_pool.dict_sock_addr[s.__hash__()] = s
            else:
                for p in list_peers['peers']:
                    if isinstance(p, dict):
                        s = SockAddr(ip=p['ip'], port=int(p['port']))
                        self.peers_pool.dict_sock_addr[s.__hash__()] = s
            self.stdout.DEBUG("HTTP scraper got peers: %s" % tracker)
        except Exception as e:
            self.stdout.ERROR("Error in http scraper:", tracker, e)
            return
        finally:
            THREAD_SEMA.release()


class UDPScraper(Thread):
    def __init__(self, torrent, tracker, peers_pool, port=6881, timeout=1, stdout=None):
        Thread.__init__(self)
        self.torrent = torrent
        self.tracker = tracker
        self.peers_pool = peers_pool
        self.port = port
        self.timeout = timeout
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()

    def run(self):
        THREAD_SEMA.acquire()
        try:
            torrent = self.torrent
            tracker = self.tracker
            parsed = urlparse(tracker)
            try:
                ip, port = socket.gethostbyname(parsed.hostname), parsed.port
            except socket.gaierror:
                self.stdout.WARNING("No address associated with hostname:", parsed.hostname)
                return
            except:
                self.stdout.WARNING("Urlparse not working. Using manual parser")
                hostname = ':'.join(parsed.netloc.split(':')[:-1]).lstrip('[').rstrip(']')
                port = int(parsed.netloc.split(':')[-1])
                try:
                    ip = socket.gethostbyname(hostname)
                except socket.gaierror:
                    self.stdout.WARNING("No address associated with hostname:", parsed.hostname)
                    return

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(self.timeout)

            if ipaddress.ip_address(ip).is_private:
                self.stdout.WARNING("ip address is private:", tracker)
                return

            tracker_connection_input = UdpTrackerConnection()
            response = self.send_message(
                conn=(ip, port),
                sock=sock,
                tracker_message=tracker_connection_input
            )

            if not response:
                self.stdout.WARNING("No response for UdpTrackerConnection:", tracker)
                return

            tracker_connection_output = UdpTrackerConnection()
            tracker_connection_output.from_bytes(payload=response)

            tracker_announce_input = UdpTrackerAnnounce(
                info_hash=torrent.info_hash,
                conn_id=tracker_connection_output.conn_id,
                peer_id=torrent.peer_id,
                port=self.port
            )
            response = self.send_message(
                conn=(ip, port),
                sock=sock,
                tracker_message=tracker_announce_input
            )

            if not response:
                self.stdout.WARNING("No response for UdpTrackerAnnounce:", tracker)
                return

            tracker_announce_output = UdpTrackerAnnounceOutput()
            tracker_announce_output.from_bytes(payload=response)

            for ip, port in tracker_announce_output.list_sock_addr:
                sock_addr = SockAddr(ip=ip, port=port)

                if sock_addr.__hash__() not in self.peers_pool.dict_sock_addr:
                    self.peers_pool.dict_sock_addr[sock_addr.__hash__()] = sock_addr
            self.stdout.DEBUG("UDP scraper got peers: %s" % tracker)
        except Exception as e:
            self.stdout.ERROR("Error in udp scraper:", tracker, e)
            return
        finally:
            THREAD_SEMA.release()
    
    def send_message(self, conn, sock, tracker_message):
        message = tracker_message.to_bytes()
        trans_id = tracker_message.trans_id
        action = tracker_message.action
        size = len(message)

        sock.sendto(message, conn)

        try:
            response = self._read_from_socket(sock)
        except socket.timeout:
            self.stdout.WARNING("Send message timeout in UDPScraper")
            return
        except Exception as e:
            self.stdout.ERROR("Error read from socket in UDPScraper:", e)
            return

        if len(response) < size:
            self.stdout.WARNING("Response size not valid in UDPScraper")
            return

        if action != response[0:4] or trans_id != response[4:8]:
            self.stdout.WARNING("Data not valid in UDPScraper")
            return

        return response
    
    def _read_from_socket(self, sock):
        data = b''

        while True:
            try:
                buff = sock.recv(4096)
                if len(buff) <= 0:
                    break

                data += buff
            except socket.timeout:
                self.stdout.WARNING("Read from socket timeout in UDPScraper")
                break
            except BlockingIOError:
                self.stdout.WARNING("Resource temporarily unavailable when read from socket in UDPScraper")
                break
            except OSError:
                self.stdout.WARNING("Socket closed in UDPScraper")
                break
            except Exception as e:
                self.stdout.ERROR("Error when read from socket in UDPScraper:", e)
                break

        return data


class PeersConnector(Thread):
    def __init__(self, torrent, sock_addr, peers_pool, del_queue, timeout=1, stdout=None):
        Thread.__init__(self)
        self.torrent = torrent
        self.sock_addr = sock_addr
        self.peers_pool = peers_pool
        self.del_queue = del_queue
        self.timeout = timeout
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
    
    def run(self):
        THREAD_SEMA.acquire()
        try:
            new_peer = Peer(
                number_of_pieces=int(self.torrent.number_of_pieces),
                ip=self.sock_addr.ip,
                port=self.sock_addr.port,
                stdout=self.stdout
            )
            if not new_peer.connect(timeout=self.timeout) or not self.do_handshake(new_peer):
                self.del_queue.put(new_peer.__hash__())
            else:
                self.peers_pool.connected_peers[new_peer.__hash__()] = new_peer
                self.stdout.DEBUG("new peer added: ip: %s - port: %s" % (new_peer.ip, new_peer.port))
        except Exception as e:
            self.stdout.ERROR("Error in peers connector:", e)
            return
        finally:
            THREAD_SEMA.release()
    
    def do_handshake(self, peer):
        try:
            handshake = Handshake(info_hash=self.torrent.info_hash)
            peer.send_to_peer(handshake.to_bytes())
            return True

        except Exception as e:
            self.stdout.ERROR("Error when sending Handshake message:", e)

        return False


class PeersScraper():
    def __init__(self, torrent, peers_pool, port=6881, timeout=1, stdout=None):
        self.torrent = torrent
        self.tracker_list = self.torrent.announce_list
        self.peers_pool = peers_pool
        self.port = port
        self.timeout = timeout
        self.queue = queue.Queue()
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
    
    def start(self):
        self.stdout.INFO("Updating peers")
        task_list = []
        for tracker in self.tracker_list:
            if str.startswith(tracker, "http"):
                scraper = HTTPScraper(
                    torrent=self.torrent,
                    tracker=tracker,
                    peers_pool=self.peers_pool,
                    port=self.port,
                    timeout=self.timeout,
                    stdout=self.stdout
                )
                task_list.append(scraper)
                scraper.start()
            elif str.startswith(tracker, "udp"):
                scraper = UDPScraper(
                    torrent=self.torrent,
                    tracker=tracker,
                    peers_pool=self.peers_pool,
                    port=self.port,
                    timeout=self.timeout,
                    stdout=self.stdout
                )
                task_list.append(scraper)
                scraper.start()
            else:
                self.stdout.WARNING("unknown scheme for: %s " % tracker)
        for scraper in task_list:
            scraper.join()

        self.stdout.INFO("Total %d peers" % len(self.peers_pool.dict_sock_addr))

        task_list = []
        for sock_addr in self.peers_pool.dict_sock_addr.values():
            connector = PeersConnector(
                torrent=self.torrent,
                sock_addr=sock_addr,
                peers_pool=self.peers_pool,
                del_queue=self.queue,
                timeout=self.timeout,
                stdout=self.stdout
            )
            task_list.append(connector)
            connector.start()
        for connector in task_list:
            connector.join()
        
        for del_peer in self.queue.queue:
            try:
                del self.peers_pool.dict_sock_addr[del_peer]
                del self.peers_pool.connected_peers[del_peer]
            except:
                continue
        
        self.stdout.INFO('Connected to %d peers' % len(self.peers_pool.connected_peers))


class PeersManager(Thread):
    def __init__(self, torrent, pieces_manager, peers_pool, stdout=None):
        Thread.__init__(self)
        self.torrent = torrent
        self.pieces_manager = pieces_manager
        self.peers_pool = peers_pool
        self.pieces_by_peer = [[0, []] for _ in range(pieces_manager.number_of_pieces)]
        self.is_active = True
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()

        # Events
        pub.subscribe(self.peer_requests_piece, 'PeersManager.PeerRequestsPiece')

    def peer_requests_piece(self, request=None, peer=None):
        if not request or not peer:
            self.stdout.WARNING("empty request/peer message")

        piece_index, block_offset, block_length = request.piece_index, request.block_offset, request.block_length

        block = self.pieces_manager.get_block(
            piece_index=piece_index,
            block_offset=block_offset,
            block_length=block_length
        )
        if block:
            piece = Piece(
                block_length=block_length,
                piece_index=piece_index,
                block_offset=block_offset,
                block=block
            ).to_bytes()
            peer.send_to_peer(mgs=piece)
            self.stdout.DEBUG("Sent piece index {} to peer : {}".format(request.piece_index, peer.ip))

    def get_random_peer_having_piece(self, index):
        ready_peers = []
        for peer in self.peers_pool.connected_peers.values():
            if peer.is_eligible() and peer.is_unchoked() and peer.am_interested() and peer.has_piece(index):
                ready_peers.append(peer)
        return random.choice(ready_peers) if ready_peers else None

    def has_unchoked_peers(self):
        for peer in self.peers_pool.connected_peers.values():
            if peer.is_unchoked():
                return True
        return False

    def unchoked_peers_count(self):
        cpt = 0
        for peer in self.peers_pool.connected_peers.values():
            if peer.is_unchoked():
                cpt += 1
        return cpt

    def _read_from_socket(self, sock):
        data = b''

        while True:
            try:
                buff = sock.recv(4096)
                if len(buff) <= 0:
                    break

                data += buff
            except socket.timeout:
                self.stdout.WARNING("Read from socket timeout in PeersManager")
                break
            except BlockingIOError:
                # Resource temporarily unavailable
                # self.stdout.WARNING('Blocking IO in PeersManager:', e)
                break

        return data

    def run(self):
        while self.is_active:
            try:
                read = [peer.socket for peer in self.peers_pool.connected_peers.values()]
                read_list, _, _ = select.select(read, [], [], 1)

                for socket in read_list:
                    peer = self.get_peer_by_socket(socket)
                    if not peer.healthy:
                        self.remove_peer(peer=peer)
                        continue

                    try:
                        payload = self._read_from_socket(socket)
                    except ConnectionResetError:
                        self.stdout.WARNING("Connection reset by peer in PeersManager")
                        self.remove_peer(peer=peer)
                        continue
                    except OSError:
                        self.stdout.WARNING("Socket closed in PeersManager")
                        self.remove_peer(peer=peer)
                        continue
                    except Exception as e:
                        self.stdout.ERROR("Error when read from socket in peers_manager.PeersManager:", e)
                        self.remove_peer(peer=peer)
                        continue

                    peer.read_buffer += payload

                    for message in peer.get_messages():
                        self._process_new_message(new_message=message, peer=peer)
            except ValueError as e:
                self.stdout.ERROR("PeersManager is still running when updating peers.", e)
                break
            except Exception as e:
                self.stdout.ERROR("Error when looping peers manager:", e)
                break

    def remove_peer(self, peer):
        if peer in self.peers_pool.connected_peers.values():
            try:
                peer.socket.close()
            except BrokenPipeError as e:
                self.stdout.WARNING("Remove peer broken pipe error:", e)
            except Exception as e:
                self.stdout.ERROR("Wrong when remove peer: %s" % e)

            del self.peers_pool.connected_peers[peer.__hash__()]

    def get_peer_by_socket(self, socket):
        for peer in self.peers_pool.connected_peers.values():
            if socket == peer.socket:
                return peer
        raise Exception("Peer not present in peer_list")

    def _process_new_message(self, new_message: Message, peer: Peer):
        if isinstance(new_message, Handshake) or isinstance(new_message, KeepAlive):
            self.stdout.WARNING("Handshake or KeepALive should have already been handled")

        elif isinstance(new_message, Choke):
            peer.handle_choke()

        elif isinstance(new_message, UnChoke):
            peer.handle_unchoke()

        elif isinstance(new_message, Interested):
            peer.handle_interested()

        elif isinstance(new_message, NotInterested):
            peer.handle_not_interested()

        elif isinstance(new_message, Have):
            peer.handle_have(have=new_message)

        elif isinstance(new_message, BitField):
            peer.handle_bitfield(bitfield=new_message)

        elif isinstance(new_message, Request):
            peer.handle_request(request=new_message)

        elif isinstance(new_message, Piece):
            peer.handle_piece(message=new_message)

        elif isinstance(new_message, Cancel):
            peer.handle_cancel()

        elif isinstance(new_message, Port):
            peer.handle_port_request()

        else:
            self.stdout.WARNING("Unknown message")
