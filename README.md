
# LTorrent
A pure python torrent client based on PyTorrent

- Pure Python client.
- Based on [gallexis/PyTorrent](https://github.com/gallexis/PyTorrent).
- Support [torrent file](#torrent-file) and [magnet link](#magnet-link).
- Scrape `udp` or `http` trackers with multiple thread.
- Connect to peers with multiple thread.
- Support [custom storage](#custom-storage).
- Support file selection.
- Support custom [stdout](https://github.com/hlf20010508/LTorrent/tree/master/examples/custom_stdout.py) and [stdin](https://github.com/hlf20010508/LTorrent/tree/master/examples/custom_stdin.py).
- Support [running as a thread](#run-as-a-thread).

See examples [here](https://github.com/hlf20010508/LTorrent/tree/master/examples).

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
pip install git+https://github.com/hlf20010508/LTorrent.git@1.2.0
# using pipenv
pipenv install git+https://github.com/hlf20010508/LTorrent.git@1.2.0#egg=LTorrent
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
    port=port,
    timeout=timeout,
)

client.load(torrent_path=torrent_path)
client.select_file()
client.run()
```

### Magnet Link
```py
from ltorrent.client import Client

magnet_link = "your-magnet-link"
port = 8080
timeout = 1

client = Client(
    port=port,
    timeout=timeout,
)

client.load(magnet_link=magnet_link)
client.select_file()
client.run()
```

### Custom Storage
See full example in [examples/custom_storage.py](https://github.com/hlf20010508/LTorrent/tree/master/examples/custom_storage.py).
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
    port=port,
    timeout=timeout,
    custom_storage=custom_storage
)

client.load(magnet_link=magnet_link)
client.select_file()
client.run()
```

### Run as a Thread
```py
from ltorrent.client import Client

magnet_link = "your-magnet-link"
port = 8080
timeout = 1

client = Client(
    port=port,
    timeout=timeout,
)

client.load(magnet_link=magnet_link)
client.select_file()
client.start()
```
