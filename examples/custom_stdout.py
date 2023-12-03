import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from ltorrent.client import Client
from ltorrent.log import LoggerBase


class MyLogger(LoggerBase):
    def __init__(self):
        LoggerBase.__init__(self)
    
    def MUST(self, *args):
        print(*args)
    
    def INFO(self, *args):
        print(*args)

    def DEBUG(self, *args):
        print(*args)
    
    def PROGRESS(self, *args):
        print(*args)


if __name__ == '__main__':
    magnet_link = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"
    port = 8080
    logger = MyLogger()
    
    client = Client(
        port=port,
        stdout=logger
    )

    client.load(magnet_link=magnet_link)
    client.select_file()
    client.run()
