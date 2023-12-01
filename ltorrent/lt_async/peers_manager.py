__author__ = 'alexisgallepe, L-ING'

import select
import asyncio
import socket
import random
import aiohttp
from bcoding import bdecode
import struct
from urllib.parse import urlparse, quote_from_bytes
import ipaddress
import queue
import urllib3
from ltorrent.lt_async.message import (
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
from ltorrent.lt_async.peer import Peer
from ltorrent.lt_async.log import Logger
import ltorrent.lt_async._rewrite

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_WORKERS = 10
SEMA = asyncio.Semaphore(MAX_WORKERS)

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

# def with_query(self, *args, **kwargs):

    

class HTTPScraper:
    def __init__(self, torrent, tracker, peers_pool, port=6881, timeout=1, stdout=None):
        self.torrent = torrent
        self.tracker = tracker
        self.peers_pool = peers_pool
        self.port = port
        self.timeout = timeout
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
    
    async def run(self):
        try:
            torrent = self.torrent
            tracker = self.tracker
            params = {
                'info_hash': quote_from_bytes(torrent.info_hash),
                'peer_id': torrent.peer_id,
                'uploaded': 0,
                'downloaded': 0,
                'port': self.port,
                'left': torrent.total_length,
                'event': 'started'
            }
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.get(tracker, params=params, ssl=False) as answer_tracker:
                        try:
                            list_peers = bdecode(await answer_tracker.content.read())
                        except TypeError:
                            await self.stdout.WARNING("Failed to decode response content from tracker:", tracker)
                            return
                except ConnectionRefusedError:
                    await self.stdout.WARNING("Failed to visit tracker in http scraper:", tracker)
                    return
                except asyncio.exceptions.TimeoutError:
                    await self.stdout.WARNING("Timeout in http scraper:", tracker)
                    return
                except aiohttp.client_exceptions.ServerDisconnectedError:
                    await self.stdout.WARNING("Server disconnected in http scraper:", tracker)
                    return
                except aiohttp.client_exceptions.ClientConnectorError:
                    await self.stdout.WARNING("Network unreachable in http scraper:", tracker)
                    return
                except ValueError as e:
                    await self.stdout.WARNING(e, tracker)
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
            await self.stdout.DEBUG("HTTP scraper got peers: %s" % tracker)
        except Exception as e:
            await self.stdout.ERROR("Error in http scraper:", tracker, e)
            return


class UDPScraper:
    def __init__(self, torrent, tracker, peers_pool, port=6881, timeout=1, stdout=None):
        self.torrent = torrent
        self.tracker = tracker
        self.peers_pool = peers_pool
        self.port = port
        self.timeout = timeout
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()

    async def run(self):
        try:
            torrent = self.torrent
            tracker = self.tracker
            parsed = urlparse(tracker)
            try:
                ip, port = socket.gethostbyname(parsed.hostname), parsed.port
            except socket.gaierror:
                await self.stdout.WARNING("No address associated with hostname:", parsed.hostname)
                return
            except:
                await self.stdout.WARNING("Urlparse not working. Using manual parser")
                hostname = ':'.join(parsed.netloc.split(':')[:-1]).lstrip('[').rstrip(']')
                port = int(parsed.netloc.split(':')[-1])
                try:
                    ip = socket.gethostbyname(hostname)
                except socket.gaierror:
                    await self.stdout.WARNING("No address associated with hostname:", parsed.hostname)
                    return

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(self.timeout)

            if ipaddress.ip_address(ip).is_private:
                await self.stdout.WARNING("ip address is private:", tracker)
                return

            tracker_connection_input = UdpTrackerConnection()
            response = await self.send_message(
                conn=(ip, port),
                sock=sock,
                tracker_message=tracker_connection_input
            )

            if not response:
                await self.stdout.WARNING("No response for UdpTrackerConnection:", tracker)
                return

            tracker_connection_output = UdpTrackerConnection()
            tracker_connection_output.from_bytes(payload=response)

            tracker_announce_input = UdpTrackerAnnounce(
                info_hash=torrent.info_hash,
                conn_id=tracker_connection_output.conn_id,
                peer_id=torrent.peer_id,
                port=self.port
            )
            response = await self.send_message(
                conn=(ip, port),
                sock=sock,
                tracker_message=tracker_announce_input
            )

            if not response:
                await self.stdout.WARNING("No response for UdpTrackerAnnounce:", tracker)
                return

            tracker_announce_output = UdpTrackerAnnounceOutput()
            tracker_announce_output.from_bytes(payload=response)

            for ip, port in tracker_announce_output.list_sock_addr:
                sock_addr = SockAddr(ip=ip, port=port)

                if sock_addr.__hash__() not in self.peers_pool.dict_sock_addr:
                    self.peers_pool.dict_sock_addr[sock_addr.__hash__()] = sock_addr
            await self.stdout.DEBUG("UDP scraper got peers: %s" % tracker)
        except Exception as e:
            await self.stdout.ERROR("Error in udp scraper:", tracker, e)
            return
    
    async def send_message(self, conn, sock, tracker_message):
        message = tracker_message.to_bytes()
        trans_id = tracker_message.trans_id
        action = tracker_message.action
        size = len(message)

        sock.sendto(message, conn)

        try:
            response = await self._read_from_socket(sock)
        except socket.timeout:
            await self.stdout.WARNING("Send message timeout in UDPScraper")
            return
        except Exception as e:
            await self.stdout.ERROR("Error read from socket in UDPScraper:", e)
            return

        if len(response) < size:
            await self.stdout.WARNING("Response size not valid in UDPScraper")
            return

        if action != response[0:4] or trans_id != response[4:8]:
            await self.stdout.WARNING("Data not valid in UDPScraper")
            return

        return response
    
    async def _read_from_socket(self, sock):
        data = b''

        while True:
            try:
                buff = sock.recv(4096)
                if len(buff) <= 0:
                    break

                data += buff
            except socket.timeout:
                await self.stdout.WARNING("Read from socket timeout in UDPScraper")
                break
            except BlockingIOError:
                await self.stdout.WARNING("Resource temporarily unavailable when read from socket in UDPScraper")
                break
            except OSError:
                await self.stdout.WARNING("Socket closed in UDPScraper")
                break
            except Exception as e:
                await self.stdout.ERROR("Error when read from socket in UDPScraper:", e)
                break

        return data


class PeersConnector:
    def __init__(self, torrent, sock_addr, peers_pool, peers_manager, piece_manager, del_queue, timeout=1, stdout=None):
        self.torrent = torrent
        self.sock_addr = sock_addr
        self.peers_pool = peers_pool
        self.peers_manager = peers_manager
        self.piece_manager = piece_manager
        self.del_queue = del_queue
        self.timeout = timeout
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
    
    async def run(self):
        try:
            new_peer = Peer(
                number_of_pieces=int(self.torrent.number_of_pieces),
                peers_manager=self.peers_manager,
                piece_manager=self.piece_manager,
                ip=self.sock_addr.ip,
                port=self.sock_addr.port,
                stdout=self.stdout
            )
            if not await new_peer.connect(timeout=self.timeout) or not await self.do_handshake(new_peer):
                self.del_queue.put(new_peer.__hash__())
            else:
                self.peers_pool.connected_peers[new_peer.__hash__()] = new_peer
                await self.stdout.DEBUG("new peer added: ip: %s - port: %s" % (new_peer.ip, new_peer.port))
        except Exception as e:
            await self.stdout.ERROR("Error in peers connector:", e)
            return
    
    async def do_handshake(self, peer):
        try:
            handshake = Handshake(info_hash=self.torrent.info_hash)
            await peer.send_to_peer(handshake.to_bytes())
            return True

        except Exception as e:
            await self.stdout.ERROR("Error when sending Handshake message:", e)

        return False


class PeersScraper:
    def __init__(self, torrent, peers_pool, peers_manager, piece_manager, port=6881, timeout=1, stdout=None):
        self.torrent = torrent
        self.tracker_list = self.torrent.announce_list
        self.peers_pool = peers_pool
        self.peers_manager = peers_manager
        self.piece_manager = piece_manager
        self.port = port
        self.timeout = timeout
        self.queue = queue.Queue()
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()
    
    async def run(self):
        await self.stdout.INFO("Updating peers")
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
                ).run()
                task_list.append(scraper)
            elif str.startswith(tracker, "udp"):
                scraper = UDPScraper(
                    torrent=self.torrent,
                    tracker=tracker,
                    peers_pool=self.peers_pool,
                    port=self.port,
                    timeout=self.timeout,
                    stdout=self.stdout
                ).run()
                task_list.append(scraper)
            else:
                await self.stdout.WARNING("unknown scheme for: %s " % tracker)
        
        await asyncio.gather(*task_list)
            
        await self.stdout.INFO("Total %d peers" % len(self.peers_pool.dict_sock_addr))

        task_list = []
        for sock_addr in self.peers_pool.dict_sock_addr.values():
            connector = PeersConnector(
                torrent=self.torrent,
                sock_addr=sock_addr,
                peers_pool=self.peers_pool,
                peers_manager=self.peers_manager,
                piece_manager=self.piece_manager,
                del_queue=self.queue,
                timeout=self.timeout,
                stdout=self.stdout
            ).run()
            task_list.append(connector)
        
        await asyncio.gather(*task_list)
        
        for del_peer in self.queue.queue:
            try:
                del self.peers_pool.dict_sock_addr[del_peer]
                del self.peers_pool.connected_peers[del_peer]
            except:
                continue
        
        await self.stdout.INFO('Connected to %d peers' % len(self.peers_pool.connected_peers))


class PeersManager:
    def __init__(self, torrent, pieces_manager, peers_pool, stdout=None):
        self.torrent = torrent
        self.pieces_manager = pieces_manager
        self.peers_pool = peers_pool
        self.pieces_by_peer = [[0, []] for _ in range(pieces_manager.number_of_pieces)]
        self.is_active = True
        if stdout:
            self.stdout = stdout
        else:
            self.stdout = Logger()

    async def peer_requests_piece(self, request, peer):
        if not request or not peer:
            await self.stdout.WARNING("empty request/peer message")

        piece_index, block_offset, block_length = request.piece_index, request.block_offset, request.block_length

        block = await self.pieces_manager.get_block(
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
            await peer.send_to_peer(mgs=piece)
            await self.stdout.DEBUG("Sent piece index {} to peer : {}".format(request.piece_index, peer.ip))

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

    async def _read_from_socket(self, sock):
        data = b''

        while True:
            try:
                buff = sock.recv(4096)
                if len(buff) <= 0:
                    break

                data += buff
            except socket.timeout:
                await self.stdout.WARNING("Read from socket timeout in PeersManager")
                break
            except BlockingIOError:
                # Resource temporarily unavailable
                break
            except ConnectionResetError:
                await self.stdout.WARNING("Connection reset by peer in PeersManager")
                break
            except OSError:
                await self.stdout.WARNING("Socket closed in PeersManager")
                break
            except Exception as e:
                await self.stdout.ERROR("Error when read from socket in peers_manager.PeersManager:", e)
                break

        return data

    async def start(self):
        while self.is_active:
            try:
                read = [peer.socket for peer in self.peers_pool.connected_peers.values()]
                read_list, _, _ = select.select(read, [], [], 1)

                for socket in read_list:
                    peer = self.get_peer_by_socket(socket)
                    if not peer.healthy:
                        await self.remove_peer(peer=peer)
                        continue

                    try:
                        payload = await self._read_from_socket(socket)
                    except Exception as e:
                        await self.stdout.ERROR("Recv failed %s" % e)
                        await self.remove_peer(peer=peer)
                        continue

                    peer.read_buffer += payload

                    async for message in peer.get_messages():
                        await self._process_new_message(new_message=message, peer=peer)
            except ValueError as e:
                await self.stdout.ERROR("PeersManager is still running when updating peers.", e)
                break
            except Exception as e:
                await self.stdout.ERROR("Error when looping peers manager:", e)
                break
            await asyncio.sleep(0.1)
    
    async def run(self):
        self.is_active = True
        asyncio.create_task(self.start())

    async def remove_peer(self, peer):
        if peer in self.peers_pool.connected_peers.values():
            try:
                peer.socket.close()
            except Exception as e:
                await self.stdout.ERROR("Wrong when remove peer: %s" % e)

            del self.peers_pool.connected_peers[peer.__hash__()]

    def get_peer_by_socket(self, socket):
        for peer in self.peers_pool.connected_peers.values():
            if socket == peer.socket:
                return peer
        raise Exception("Peer not present in peer_list")

    async def _process_new_message(self, new_message: Message, peer: Peer):
        if isinstance(new_message, Handshake) or isinstance(new_message, KeepAlive):
            await self.stdout.WARNING("Handshake or KeepALive should have already been handled")

        elif isinstance(new_message, Choke):
            await peer.handle_choke()

        elif isinstance(new_message, UnChoke):
            await peer.handle_unchoke()

        elif isinstance(new_message, Interested):
            await peer.handle_interested()

        elif isinstance(new_message, NotInterested):
            await peer.handle_not_interested()

        elif isinstance(new_message, Have):
            await peer.handle_have(have=new_message)

        elif isinstance(new_message, BitField):
            await peer.handle_bitfield(bitfield=new_message)

        elif isinstance(new_message, Request):
            await peer.handle_request(request=new_message)

        elif isinstance(new_message, Piece):
            await peer.handle_piece(message=new_message)

        elif isinstance(new_message, Cancel):
            await peer.handle_cancel()

        elif isinstance(new_message, Port):
            await peer.handle_port_request()

        else:
            await self.stdout.WARNING("Unknown message")
