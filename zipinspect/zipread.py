import os.path
import zlib
import bz2
import lzma
import compression.zstd

import httpx

from enum import Enum
from typing import NamedTuple
from struct import Struct


class ZipCompression(Enum):
    NONE = 0
    DEFLATE = 8
    BZIP2 = 12
    LZMA = 14
    ZSTANDARD = 93

class ZipEntryInfo(NamedTuple):
    path: str
    raw_offset: int
    file_size: int
    checksum: int
    compression: ZipCompression
    compressed_size: int
    modified_date: tuple
    internal_attrs: int
    external_attrs: int

    @property
    def is_dir(self):
        return self.path.endswith('/')

class _CDFHStub(NamedTuple):
    signature: bytes
    maker_version: int # 2
    version_needed: int # 2
    bitflag: int # 2
    compression_mode: int # 2
    file_mtime: int # 2
    file_mdate: int # 2
    checksum: int # 4
    compressed_size: int # 4
    uncompressed_size: int # 4
    path_size: int # 2
    extra_size: int # 2
    comment_size: int # 2
    begin_disk: int # 2
    internal_attrs: int # 2
    external_attrs: int # 4
    offset: int # 4

class _EOCDStub(NamedTuple):
    signature: bytes
    disk: int
    begin_disk: int
    ents_on_disk: int
    ents_total: int
    cd_size: int
    cd_offset: int
    comment_size: int

class _LFHStub(NamedTuple):
    signature: bytes
    version: int
    bitflag: int
    compression_mode: int
    file_mtime: int
    file_mdate: int
    checksum: int
    compressed_size: int
    uncomprssed_size: int
    path_size: int
    extra_size: int

class ZipError(Exception):
    pass

class HTTPError(Exception):
    pass

class HTTPZipReader:
    LFH_PARSER  = Struct('<4sHHHHHIIIHH')
    CDFH_PARSER = Struct('<4sHHHHHHIIIHHHHHII')
    EOCD_PARSER = Struct('<4sHHHHIIH')

    def __init__(self, url: str, *, httpx_args=None):
        httpx_args = httpx_args or {}

        self.url = url
        self.entries = None
        self.size = 0
        self.client = httpx.AsyncClient(http2=True, **httpx_args)

    async def _do_range_request(self, start, end=None, *, stream=False, httpx_args=None):
        if httpx_args is None:
            httpx_args = {}
        if start < 0:
            raise ValueError(f"Range can't beginning with {start}; clamping.")
        if end is None:
            end = self.size
        if start >= end:
            raise ValueError(f"Invalid range {start}-{end}")

        httpx_args = httpx_args or {}

        headers = httpx_args.setdefault('headers', {})
        if rv := headers.get('Range'):
            raise RuntimeWarning(f"Range header present (value={rv}); overwriting it.")

        # Assuming end is not zero.
        headers['Range'] = f'bytes={int(start)}-{int(end)-1}'

        request = self.client.build_request('GET', self.url, **httpx_args)

        r = await self.client.send(request, stream=stream)
        r.raise_for_status()

        return r

    async def _parse_eocd(self):
        r = await self._do_range_request(self.size-22)
        stub = _EOCDStub._make(self.EOCD_PARSER.unpack(r.content))

        if (stub.disk != stub.begin_disk or
            stub.ents_on_disk != stub.ents_total):
            raise ZipError("Multipart zip files are not supported")

        return stub

    @staticmethod
    def _detect_zip64_from_eocd(stub: _EOCDStub):
        if (stub.disk == 0xFFFF and
            stub.ents_total == 0xFFF and
            stub.cd_size == 0xFFFFFFF and
            stub.cd_offset == 0xFFFFFFFF):
            return True
        else:
            return False

    async def _parse_cd_ents(self, offset, size):
        r = await self._do_range_request(offset, offset+size)
        assert len(r.content) == size

        offset = 0
        while offset < size:
            stub = _CDFHStub._make(self.CDFH_PARSER.unpack(r.content[offset:offset+46]))
            offset += 46

            # NOTE Unicode assumption maybe (somewhat) erroneous; do Proper handling.
            path = r.content[offset:offset+stub.path_size].decode('utf-8', errors='replace')
            offset += stub.path_size

            # TODO Our initial implementation skips implementing Zip64 for brevity,
            # and no extensions are implemented as of now.
            offset += stub.extra_size + stub.comment_size
            yield path, stub


    async def _calc_data_offset(self, offset: int) -> int:
        r = await self._do_range_request(offset, offset + 30)
        lfh = _LFHStub._make(self.LFH_PARSER.unpack(r.content))

        # TODO Account for encryption header (GPF bit 0).
        return (offset
                    + 30             # LFH Header
                    + lfh.path_size  # ... Variable Field
                    + lfh.extra_size)

    @staticmethod
    def _parse_msdos_date(date, time):
        # See: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-dosdatetimetofiletime
        # Microsoft was retarded from its early days.
        year   = date >> 8 + 1980
        month  = date >> 5 & 0xF
        day    = date      & 0x1F
        hour   = time >> 11
        minute = time >> 5 & 0x3F
        second = time      & 0x1F

        return year, month, day, hour, minute, second*2

    async def load_entries(self):
        if self.entries is not None:
            return

        r = await self.client.head(self.url)
        r.raise_for_status()

        if r.headers.get('Accept-Ranges') != 'bytes':
            raise HTTPError(f"Range requests not supported on {self.url}")

        if size := r.headers.get('Content-Length'):
            self.size = int(size)
        else:
            raise HTTPError(f"Unable to determine length of zip file for {self.url}")

        # TODO Implement Zip64 for better compatibility.
        eocd = await self._parse_eocd()
        if self._detect_zip64_from_eocd(eocd):
            raise NotImplementedError("Zip64 is not implemented, sorry")

        self.entries = [ZipEntryInfo(path=path,
                                     raw_offset=info.offset,
                                     file_size=info.uncompressed_size,
                                     checksum=info.checksum,
                                     compression=ZipCompression(info.compression_mode),
                                     compressed_size=info.compressed_size,
                                     modified_date=self._parse_msdos_date(info.file_mdate, info.file_mtime),
                                     internal_attrs=info.internal_attrs,
                                     external_attrs=info.external_attrs)
                        async for path, info in self._parse_cd_ents(eocd.cd_offset, eocd.cd_size)]

    async def extract(self, info, output):
        offset = await self._calc_data_offset(info.raw_offset)

        # TODO Preferably raise an exception here for empty files.
        if info.compressed_size == 0:
            return

        r = await self._do_range_request(offset,
                                         offset + info.compressed_size, stream=True)

        match info.compression:
            case ZipCompression.NONE:
                decompressor = None
            case ZipCompression.DEFLATE:
                decompressor = zlib.decompressobj(wbits=-15)
            case ZipCompression.BZIP2:
                decompressor = bz2.BZ2Decompressor()
            case ZipCompression.LZMA:
                decompressor = lzma.LZMADecompressor()
            case ZipCompression.ZSTANDARD:
                decompressor = compression.zstd.ZstdDecompressor()
            case _:
                raise NotImplementedError
        
        if decompressor:
            async for chunk in r.aiter_bytes():
                decompressed = decompressor.decompress(chunk)
                output.write(decompressed)

            decompressed = decompressor.flush()
            output.write(decompressed)
        else:
            async for chunk in r.aiter_bytes():
                output.write(chunk)

    async def __aenter__(self):
        await self.load_entries()

        return self

    async def __aexit__(self, ex, ex_val, tb):
        pass
