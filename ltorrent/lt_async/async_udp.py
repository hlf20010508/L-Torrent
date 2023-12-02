import asyncio

class CustomDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, outer_instance):
        self.outer_instance = outer_instance

    def datagram_received(self, data, addr):
        if self.outer_instance.recv_future is not None and not self.outer_instance.recv_future.done():
            self.outer_instance.recv_future.set_result((data, addr))

class AsyncUDPClient:
    def __init__(self):
        self.host = ''
        self.port = 0
        self.timeout = 1
        self.transport = None
        self.protocol = None
        self.recv_future = None
        self.loop = asyncio.get_running_loop()

    async def create_connection(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

        self.transport, self.protocol = await self.loop.create_datagram_endpoint(
            lambda: CustomDatagramProtocol(self),
            remote_addr=(self.host, self.port)
        )

        self.transport.sendto(b'ping')

        self.recv_future = self.loop.create_future()

        await asyncio.wait_for(self.recv_future, self.timeout)

    async def send(self, msg):
        if not isinstance(msg, bytes):
            msg = msg.encode()
        if self.transport is not None:
            self.transport.sendto(msg)
        else:
            raise Exception("Connection not created")

    async def recv(self, buffer_size=-1):
        if self.transport is None:
            raise Exception("Connection not created")

        self.recv_future = self.loop.create_future()
        try:
            # data, addr
            data, _ = await asyncio.wait_for(self.recv_future, self.timeout)
            if buffer_size == -1:
                return data
            else:
                return data[:buffer_size]
        except asyncio.TimeoutError:
            return b''

    def close(self):
        if self.transport is not None:
            self.transport.close()
