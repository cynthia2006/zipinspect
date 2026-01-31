import io
import httpx

class HTTPRandom(io.RawIOBase):
    """Random access HTTP resource using range-requests under the hood."""

    def __init__(self, url, **httpx_args):
        """
        :param url: URL to operate on
        """
        self.url = url
        self.client = httpx.Client(http2=True, **httpx_args)
        self.offset = 0

        r = self.client.head(url)
        if r.headers.get('Accept-Ranges') != 'bytes':
            raise ValueError(f"Range requests not supported on {url}")

        if size := r.headers.get('Content-Length'):
            self.size = int(size)
        else:
            raise ValueError(f"Content length couldn't be determined for {url}")

    def read(self, amt=-1):
        if amt < 0:
            actual = self.size - self.offset
        else:
            actual = min(self.size - self.offset, amt)

        r = self.client.get(self.url, headers={
            'Range': f'bytes={self.offset}-{self.offset + actual - 1}'
        })
        r.raise_for_status()

        # print(f'DEBUG: Read {amt} bytes from {self.url}')

        self.offset += actual
        return r.content

    def readinto(self, b):
        data = self.read(len(b))

        b[:len(data)] = data[:]

    def readall(self):
        return self.read()

    def tell(self):
        return self.offset

    def close(self):
       self.client.close()

    def flush(self):
        pass

    def readable(self):
        return True

    def writable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=0, /):
        # print(f'DEBUG: Sought to {offset} respect to whence {whence}')

        match whence:
            case 0 if 0 <= offset <= self.size:
                self.offset = offset
            case 1 if 0 <= (current := self.offset + offset) <= self.size:
                self.offset = current
            case 2 if 0 <= (current := self.size + offset) <= self.size:
                self.offset = current
            case _:
                raise ValueError("Seek offset out of bounds or invalid whence")

        return offset
