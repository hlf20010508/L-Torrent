import ipaddress
import struct
import peer
from message import UdpTrackerConnection, UdpTrackerAnnounce, UdpTrackerAnnounceOutput
from peers_manager import PeersManager

__author__ = 'alexisgallepe'

import requests
import logging
from bcoding import bdecode
import socket
from urllib.parse import urlparse


class SockAddr:
    def __init__(self, ip, port, allowed=True):
        self.ip = ip
        self.port = port
        self.allowed = allowed

    def __hash__(self):
        return "%s:%d" % (self.ip, self.port)


class Tracker(object):
    def __init__(self, torrent, port, timeout):
        self.port = port
        self.timeout = timeout
        self.torrent = torrent
        self.threads_list = []
        self.connected_peers = {}
        self.dict_sock_addr = {}

    def get_peers_from_trackers(self):
        for i, tracker_url in enumerate(self.torrent.announce_list):
            if str.startswith(tracker_url, "http"):
                try:
                    self.http_scraper(self.torrent, tracker_url)
                except Exception as e:
                    logging.error("HTTP scraping failed: %s " % e.__str__())

            if str.startswith(tracker_url, "udp"):
                try:
                    self.udp_scrapper(tracker_url)
                except Exception as e:
                    logging.error("UDP scraping failed: %s " % e.__str__())

            else:
                logging.error("unknown scheme for: %s " % tracker_url)

        self.try_peer_connect()

        return self.connected_peers

    def try_peer_connect(self):
        logging.info("Trying to connect to %d peer(s)" % len(self.dict_sock_addr))

        for _, sock_addr in self.dict_sock_addr.items():
            new_peer = peer.Peer(int(self.torrent.number_of_pieces), sock_addr.ip, sock_addr.port)
            if not new_peer.connect(timeout=self.timeout):
                continue

            print('Connected to %d peers' % len(self.connected_peers))

            self.connected_peers[new_peer.__hash__()] = new_peer

    def http_scraper(self, torrent, tracker):
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
            answer_tracker = requests.get(tracker, params=params, verify=False, timeout=self.timeout)
            list_peers = bdecode(answer_tracker.content)
            offset=0
            if not type(list_peers['peers']) == list:
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
                    port = struct.unpack_from("!H",list_peers['peers'], offset)[0]
                    offset += 2
                    s = SockAddr(ip,port)
                    self.dict_sock_addr[s.__hash__()] = s
            else:
                for p in list_peers['peers']:
                    s = SockAddr(p['ip'], p['port'])
                    self.dict_sock_addr[s.__hash__()] = s

        except Exception as e:
            logging.exception("HTTP scraping failed: %s" % e.__str__())

    def udp_scrapper(self, announce):
        torrent = self.torrent
        parsed = urlparse(announce)
        try:
            ip, port = socket.gethostbyname(parsed.hostname), parsed.port
        except:
            hostname = ':'.join(parsed.netloc.split(':')[:-1]).lstrip('[').rstrip(']')
            port = int(parsed.netloc.split(':')[-1])
            ip = socket.gethostbyname(hostname)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(self.timeout)

        if ipaddress.ip_address(ip).is_private:
            return

        tracker_connection_input = UdpTrackerConnection()
        response = self.send_message((ip, port), sock, tracker_connection_input)

        if not response:
            raise Exception("No response for UdpTrackerConnection")

        tracker_connection_output = UdpTrackerConnection()
        tracker_connection_output.from_bytes(response)

        tracker_announce_input = UdpTrackerAnnounce(torrent.info_hash, tracker_connection_output.conn_id,
                                                    torrent.peer_id, self.port)
        response = self.send_message((ip, port), sock, tracker_announce_input)

        if not response:
            raise Exception("No response for UdpTrackerAnnounce")

        tracker_announce_output = UdpTrackerAnnounceOutput()
        tracker_announce_output.from_bytes(response)

        for ip, port in tracker_announce_output.list_sock_addr:
            sock_addr = SockAddr(ip, port)

            if sock_addr.__hash__() not in self.dict_sock_addr:
                self.dict_sock_addr[sock_addr.__hash__()] = sock_addr

        print("Got %d peers" % len(self.dict_sock_addr))

    def send_message(self, conn, sock, tracker_message):
        message = tracker_message.to_bytes()
        trans_id = tracker_message.trans_id
        action = tracker_message.action
        size = len(message)

        sock.sendto(message, conn)

        try:
            response = PeersManager._read_from_socket(sock)
        except socket.timeout as e:
            logging.debug("Timeout : %s" % e)
            return
        except Exception as e:
            logging.exception("Unexpected error when sending message : %s" % e.__str__())
            return

        if len(response) < size:
            logging.debug("Did not get full message.")

        if action != response[0:4] or trans_id != response[4:8]:
            logging.debug("Transaction or Action ID did not match")

        return response

TRACKERS_LIST = [
    'http://1337.abcvg.info:80/announce',
    'http://207.241.226.111:6969/announce',
    'http://207.241.231.226:6969/announce',
    'http://46.17.46.112:8080/announce',
    'http://49.12.76.8:8080/announce',
    'http://[2001:1b10:1000:8101:0:242:ac11:2]:6969/announce',
    'http://[2a00:b700:1::3:1dc]:8080/announce',
    'http://[2a01:4f8:c012:8025::1]:8080/announce',
    'http://[2a04:ac00:1:3dd8::1:2710]:2710/announce',
    'http://bt.okmp3.ru:2710/announce',
    'http://bvarf.tracker.sh:2086/announce',
    'http://ch3oh.ru:6969/announce',
    'http://incine.ru:6969/announce',
    'http://movies.zsw.ca:6969/announce',
    'http://nyaa.tracker.wf:7777/announce',
    'http://open.acgnxtracker.com:80/announce',
    'http://open.acgtracker.com:1096/announce',
    'http://retracker.hotplug.ru:2710/announce',
    'http://share.camoe.cn:8080/announce',
    'http://smurfsoft.com:6969/announce',
    'http://t.acg.rip:6699/announce',
    'http://t.nyaatracker.com:80/announce',
    'http://torrentsmd.com:8080/announce',
    'http://tracker.birkenwald.de:6969/announce',
    'http://tracker.bt4g.com:2095/announce',
    'http://tracker.dler.com:6969/announce',
    'http://tracker.edkj.club:6969/announce',
    'http://tracker.electro-torrent.pl:80/announce',
    'http://tracker.files.fm:6969/announce',
    'http://tracker.gbitt.info:80/announce',
    'http://tracker.ipv6tracker.org:80/announce',
    'http://tracker.ipv6tracker.ru:80/announce',
    'http://tracker.k.vu:6969/announce',
    'http://tracker.mywaifu.best:6969/announce',
    'http://tracker.openbittorrent.com:80/announce',
    'http://tracker.opentrackr.org:1337/announce',
    'http://tracker.qu.ax:6969/announce',
    'http://tracker.renfei.net:8080/announce',
    'http://tracker.rev.pm:6969/announce',
    'http://tracker2.itzmx.com:6961/announce',
    'http://tracker3.itzmx.com:6961/announce',
    'http://tracker4.itzmx.com:2710/announce',
    'http://v6-tracker.0g.cx:6969/announce',
    'http://wepzone.net:6969/announce',
    'http://wg.mortis.me:6969/announce',
    'http://www.all4nothin.net:80/announce.php',
    'http://www.peckservers.com:9000/announce',
    'http://www.wareztorrent.com:80/announce',
    'https://1337.abcvg.info:443/announce',
    'https://t1.hloli.org:443/announce',
    'https://tr.burnabyhighstar.com:443/announce',
    'https://tracker.cloudit.top:443/announce',
    'https://tracker.gbitt.info:443/announce',
    'https://tracker.imgoingto.icu:443/announce',
    'https://tracker.jdx3.org:443/announce',
    'https://tracker.kuroy.me:443/announce',
    'https://tracker.lilithraws.cf:443/announce',
    'https://tracker.lilithraws.org:443/announce',
    'https://tracker.loligirl.cn:443/announce',
    'https://tracker.netmap.top:8443/announce',
    'https://tracker.renfei.net:443/announce',
    'https://tracker.tamersunion.org:443/announce',
    'https://tracker.yemekyedim.com:443/announce',
    'https://tracker1.520.jp:443/announce',
    'https://trackers.mlsub.net:443/announce',
    'https://www.peckservers.com:9443/announce',
    'udp://119.28.71.45:8080/announce',
    'udp://184.105.151.166:6969/announce',
    'udp://1c.premierzal.ru:6969/announce',
    'udp://207.241.226.111:6969/announce',
    'udp://207.241.231.226:6969/announce',
    'udp://46.17.46.112:8080/announce',
    'udp://49.12.76.8:8080/announce',
    'udp://52.58.128.163:6969/announce',
    'udp://6.pocketnet.app:6969/announce',
    'udp://91.216.110.52:451/announce',
    'udp://aarsen.me:6969/announce',
    'udp://acxx.de:6969/announce',
    'udp://aegir.sexy:6969/announce',
    'udp://black-bird.ynh.fr:6969/announce',
    'udp://bt.ktrackers.com:6666/announce',
    'udp://bt1.archive.org:6969/announce',
    'udp://bt2.archive.org:6969/announce',
    'udp://concen.org:6969/announce',
    'udp://d40969.acod.regrucolo.ru:6969/announce',
    'udp://ec2-18-191-163-220.us-east-2.compute.amazonaws.com:6969/announce',
    'udp://epider.me:6969/announce',
    'udp://evan.im:6969/announce',
    'udp://exodus.desync.com:6969/announce',
    'udp://fe.dealclub.de:6969/announce',
    'udp://fh2.cmp-gaming.com:6969/announce',
    'udp://free.publictracker.xyz:6969/announce',
    'udp://hz.is:1337/announce',
    'udp://ipv6.fuuuuuck.com:6969/announce',
    'udp://isk.richardsw.club:6969/announce',
    'udp://mail.artixlinux.org:6969/announce',
    'udp://moonburrow.club:6969/announce',
    'udp://movies.zsw.ca:6969/announce',
    'udp://new-line.net:6969/announce',
    'udp://ns1.monolithindustries.com:6969/announce',
    'udp://odd-hd.fr:6969/announce',
    'udp://oh.fuuuuuck.com:6969/announce',
    'udp://open.demonii.com:1337/announce',
    'udp://open.dstud.io:6969/announce',
    'udp://open.free-tracker.ga:6969/announce',
    'udp://open.stealth.si:80/announce',
    'udp://open.tracker.ink:6969/announce',
    'udp://open.u-p.pw:6969/announce',
    'udp://opentor.org:2710/announce',
    'udp://opentracker.io:6969/announce',
    'udp://p4p.arenabg.com:1337/announce',
    'udp://private.anonseed.com:6969/announce',
    'udp://public-tracker.cf:6969/announce',
    'udp://retracker.hotplug.ru:2710/announce',
    'udp://retracker01-msk-virt.corbina.net:80/announce',
    'udp://run-2.publictracker.xyz:6969/announce',
    'udp://run.publictracker.xyz:6969/announce',
    'udp://ryjer.com:6969/announce',
    'udp://sabross.xyz:6969/announce',
    'udp://sanincode.com:6969/announce',
    'udp://static.54.161.216.95.clients.your-server.de:6969/announce',
    'udp://su-data.com:6969/announce',
    'udp://tamas3.ynh.fr:6969/announce',
    'udp://thouvenin.cloud:6969/announce',
    'udp://tk1.trackerservers.com:8080/announce',
    'udp://torrents.artixlinux.org:6969/announce',
    'udp://tracker-udp.gbitt.info:80/announce',
    'udp://tracker.0x7c0.com:6969/announce',
    'udp://tracker.4.babico.name.tr:3131/announce',
    'udp://tracker.6.babico.name.tr:6969/announce',
    'udp://tracker.anima.nz:6969/announce',
    'udp://tracker.artixlinux.org:6969/announce',
    'udp://tracker.birkenwald.de:6969/announce',
    'udp://tracker.ccp.ovh:6969/announce',
    'udp://tracker.cubonegro.lol:6969/announce',
    'udp://tracker.cyberia.is:6969/announce',
    'udp://tracker.dler.com:6969/announce',
    'udp://tracker.dler.org:6969/announce',
    'udp://tracker.edkj.club:6969/announce',
    'udp://tracker.farted.net:6969/announce',
    'udp://tracker.filemail.com:6969/announce',
    'udp://tracker.fnix.net:6969/announce',
    'udp://tracker.iperson.xyz:6969/announce',
    'udp://tracker.moeking.me:6969/announce',
    'udp://tracker.openbittorrent.com:6969/announce',
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://tracker.qu.ax:6969/announce',
    'udp://tracker.skynetcloud.site:6969/announce',
    'udp://tracker.skyts.net:6969/announce',
    'udp://tracker.srv00.com:6969/announce',
    'udp://tracker.swateam.org.uk:2710/announce',
    'udp://tracker.t-rb.org:6969/announce',
    'udp://tracker.theoks.net:6969/announce',
    'udp://tracker.therarbg.com:6969/announce',
    'udp://tracker.tiny-vps.com:6969/announce',
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://tracker.tryhackx.org:6969/announce',
    'udp://tracker1.bt.moack.co.kr:80/announce',
    'udp://tracker1.myporn.club:9337/announce',
    'udp://tracker2.dler.com:80/announce',
    'udp://tracker2.dler.org:80/announce',
    'udp://tracker2.itzmx.com:6961/announce',
    'udp://tracker3.itzmx.com:6961/announce',
    'udp://tracker4.itzmx.com:2710/announce',
    'udp://ttk2.nbaonlineservice.com:6969/announce',
    'udp://u4.trakx.crim.ist:1337/announce',
    'udp://u6.trakx.crim.ist:1337/announce',
    'udp://uploads.gamecoast.net:6969/announce',
    'udp://v2.iperson.xyz:6969/announce',
    'udp://wepzone.net:6969/announce',
    'udp://x.paranoid.agency:6969/announce',
    'udp://x.t-1.org:6969/announce',
    'udp://y.paranoid.agency:6969/announce',
]
