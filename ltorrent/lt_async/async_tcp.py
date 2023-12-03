import asyncio

class AsyncTCPClient:
    def __init__(self):
        self.host = ''
        self.port = 0
        self.timeout = 2
        self.reader = None
        self.writer = None
        self.loop = asyncio.get_running_loop()

    async def create_connection(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)

    async def send(self, msg):
        if not isinstance(msg, bytes):
            msg = msg.encode()
        if self.writer is not None:
            self.writer.write(msg)
            await asyncio.wait_for(self.writer.drain(), self.timeout)
        else:
            raise Exception("AsyncTCPClient not connected yet.")

    async def recv(self, buffer_size=-1):
        if self.reader is not None:
            # try:
            first_byte = await asyncio.wait_for(self.reader.read(1), 0.5)
            if not first_byte:
                return b''
            data = first_byte + await asyncio.wait_for(self.reader.read(buffer_size - 1), 2)
            return data
            # except asyncio.TimeoutError:
                # print("Read from socket timeout in PeersManager")
                # return b''
        else:
            raise Exception("AsyncTCPClient not connected yet.")

    async def close(self):
        if self.writer is not None:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), self.timeout)
            except ConnectionResetError:
                # print("Connection reset by peer when close async tcp")
                return
            except BrokenPipeError:
                # print("Remove peer broken pipe error when close async tcp")
                return
        else:
            raise Exception("AsyncTCPClient not connected yet.")
