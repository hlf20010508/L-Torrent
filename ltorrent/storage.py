import os
from ltorrent.log import Logger

class StorageBase:
    def __init__(self):
        pass
    
    def create_root_dir(self, root):
        pass
    
    def create_sub_dir(self, path_file):
        pass

    def write(self, file_piece_list, data):
        raise Exception("CustomStorage.write not implemented")

    def read(self, files, block_offset, block_length):
        raise Exception("CustomStorage.read not implemented")

class Storage(StorageBase):
    def __init__(self):
        StorageBase.__init__(self)
        self.stdout = Logger()

    def create_root_dir(self, root):
        if not os.path.exists(root):
            os.mkdir(path=root, mode=0o0766 )
    
    def create_sub_dir(self, path_file):
        if not os.path.exists(path=os.path.dirname(path_file)):
            os.makedirs(name=os.path.dirname(path_file))

    def write(self, file_piece_list, data):
        for file in file_piece_list:
            path_file = file["path"]
            file_offset = file["fileOffset"]
            piece_offset = file["pieceOffset"]
            length = file["length"]

            try:
                f = open(path_file, 'r+b')  # Already existing file
            except IOError:
                f = open(path_file, 'wb')  # New file
            except Exception as e:
                self.stdout.ERROR("Can't write to file:", e)
                return

            f.seek(file_offset)
            f.write(data[piece_offset:piece_offset + length])
            f.close()

    async def read(self, files, block_offset, block_length):
        file_data_list = []
        for file in files:
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
