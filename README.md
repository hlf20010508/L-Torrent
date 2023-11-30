
# LTorrent
A pure python torrent client based on PyTorrent

- Pure Python client.
- Based on [gallexis/PyTorrent](https://github.com/gallexis/PyTorrent).
- Support torrent file and magnet link.
- Scrape `udp` or `http` trackers with multiple thread.
- Connect to peers with multiple thread.
- Support custom storage.
- Support file selection.

## Todo
- Download more than one torrent at a time.
- Pause and resume download.
- Scrape peers while downloading.
- Accept new peers while downloading.

## File Selection
Input number of files, seperated by `Space`, eg: `2 5 7`.

Range supported, linked by `-`, eg: `4 6-10 12 14-20`.

## Installation
```sh
# using pip
pip install git+https://github.com/hlf20010508/LTorrent.git
# using pipenv
pipenv install git+https://github.com/hlf20010508/LTorrent.git#egg=LTorrent
```

## Start
### Run Demo
```sh
pipenv install
pipenv run python demo.py
```

### Torrent File
```py
from ltorrent.client import Client

torrent_path = "your-torrent-path"
port = 8080
timeout = 1

client = Client(
    port,
    torrent_path=torrent_path,
    timeout=timeout,
)
client.start()
```

### Magnet Link
```py
from ltorrent.client import Client

magnet_link = "your-magnet-link"
port = 8080
timeout = 1

client = Client(
    port,
    magnet_link=magnet_link,
    timeout=timeout,
)
client.start()
```

### Custom Storage
See full example in `examples/custom_storage.py`.
```py
from ltorrent.client import Client, CustomStorage


class MyStorage(CustomStorage):
    def __init__(self):
        CustomStorage.__init__(self)

    def write(self, file_piece_list, data):
        for file_piece in file_piece_list:
            path_file = os.path.join('downloads', file_piece["path"].split('/')[-1])
            file_offset = file_piece["fileOffset"]
            piece_offset = file_piece["pieceOffset"]
            length = file_piece["length"]

            ...

    def read(self, files, block_offset, block_length):
        file_data_list = []
        for file in files:
            path_file = file["path"]
            file_offset = file["fileOffset"]
            piece_offset = file["pieceOffset"]
            length = file["length"]

            ...
        
        return piece[block_offset : block_offset + block_length]


magnet_link = "your-magnet-link"
port = 8080
timeout = 1
custom_storage = MyStorage()

client = Client(
    port,
    magnet_link=magnet_link,
    timeout=timeout,
    custom_storage=custom_storage
)
client.start()
```
