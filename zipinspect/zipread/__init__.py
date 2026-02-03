import zlib
import bz2
import lzma
import compression.zstd

import httpx

from enum import Enum
from struct import Struct
from dataclasses import dataclass

from .stubs import (
    _LFHStub,
    _CDFHStub,
    _EOCDStub,
    _EOCD64Stub
)

class ZipCompression(Enum):
    NONE = 0
    DEFLATE = 8
    BZIP2 = 12
    LZMA = 14
    ZSTANDARD = 93

@dataclass
class ZipEntryInfo:
    path: str
    raw_offset: int
    file_size: int
    encrypted: int
    checksum: int
    compression: ZipCompression
    compressed_size: int
    modified_date: tuple
    internal_attrs: int
    external_attrs: int

    @property
    def is_dir(self):
        return self.path.endswith('/')


class ZipError(Exception):
    pass


class HTTPError(Exception):
    pass


_LFHStruct = Struct('<4sHHHHHIIIHH')
_CDFHStruct = Struct('<4sHHHHHHIIIHHHHHII')
_EOCDStruct = Struct('<4sHHHHII')
_ExtraStruct = Struct('<2sH')
_EOCD64Struct = Struct('<4sQHHIIQQQQ')
_EOCD64LocatorStruct = Struct('<4sIQI')


class HTTPZipReader:
    def __init__(self, url: str, *, httpx_args=None):
        httpx_args = httpx_args or {}

        self.url = url
        self.entries = None
        self.size = 0
        self.client = httpx.AsyncClient(http2=True, **httpx_args)

    async def _request(self, start, end=None, *, stream=False, httpx_args=None):
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
        headers['Range'] = f'bytes={int(start)}-{int(end) - 1}'

        request = self.client.build_request('GET', self.url, **httpx_args)
        r = await self.client.send(request, stream=stream)
        if r.status_code != 206:
            raise HTTPError(f"Got status code {r.status_code} for {self.url}")

        return r

    async def _parse_eocd(self):
        r = await self._request(max(0, self.size - 65557))
        start_offset = r.content.rfind(b'\x50\x4B\x05\x06')

        if start_offset == -1:
            raise ZipError(f"EOCD Signature not found")

        stub = _EOCDStub._make(_EOCDStruct.unpack(r.content[start_offset:start_offset + 20]))
        if (stub.disk != stub.begin_disk or
                stub.ents_on_disk != stub.ents_total):
            raise ZipError("Multipart Zip files aren't supported")

        return stub, (self.size - len(r.content) + start_offset)

    async def _parse_eocd64(self, offset):
        r = await self._request(offset, offset + 56)
        stub = _EOCD64Stub._make(_EOCDStruct.unpack(r.content))

        if stub.signature != b'\x50\x4B\x06\x06':
            raise ZipError(f"Invalid EOCD signature: {stub.signature.hex()}")

        if (stub.disk != stub.begin_disk or
                stub.ents_on_disk != stub.ents_total):
            raise ZipError("Multipart Zip files are not supported")

    async def _parse_eocd64_locator(self, eocd_start):
        r = await self._request(eocd_start - 20, eocd_start)

        signature, disk, offset, n_disks = _EOCD64LocatorStruct.unpack(r.content)

        if signature != b'\x50\x4B\x06\x07':
            raise ZipError(f"Invalid EOCD64 signature: {signature.hex()}")
        if disk != 0 or n_disks == 1:
            raise ZipError("Multipart Zip files aren't supported.")

        return offset

    @staticmethod
    def _detect_zip64_from_eocd(stub: _EOCDStub):
        if (stub.disk == 0xFFFF and
                stub.ents_total == 0xFFF and
                stub.cd_size == 0xFFFFFFF and
                stub.cd_offset == 0xFFFFFFFF):
            return True
        else:
            return False

    @staticmethod
    def _parse_extras(extras):
        offset = 0
        size = len(extras)

        while offset < size:
            eid = extras[offset:offset + 2]
            size = int.from_bytes(extras[offset + 2:offset + 4], byteorder='little')
            data = extras[offset + 4:offset + size]

            yield eid, data

    @staticmethod
    def _parse_zip64_extra(data):
        size = len(data)
        uncompressed, compressed, offset = None, None, None

        if size >= 8:
            uncompressed = int.from_bytes(data[:8], byteorder='little')
        if size >= 16:
            compressed = int.from_bytes(data[8:16], byteorder='little')
        if size >= 32:
            offset = int.from_bytes(data[16:24], byteorder='little')

        return uncompressed, compressed, offset

    async def _parse_cd_ents(self, offset, size):
        r = await self._request(offset, offset + size)
        cd = r.content

        offset = 0
        while offset < size:
            stub = _CDFHStub._make(_CDFHStruct.unpack(cd[offset:offset + 46]))
            offset += 46

            raw_path = cd[offset:offset + stub.path_size]
            offset += stub.path_size

            extras = dict(self._parse_extras(cd[offset:offset + stub.extra_size]))
            offset += stub.extra_size
            offset += stub.comment_size

            # TODO Consider "UPath" extra field for completeness sake
            if stub.bitflag & 0b10000000000:
                path = raw_path.decode('utf-8', errors='replace')
            else:
                path = raw_path.decode('cp437')

            if zip64_extra := extras.get(b'\x01\x00'):
                uncompressed, compressed, offset = self._parse_zip64_extra(zip64_extra)

                if stub.compressed_size == 0xFF:
                    stub.compressed_size = compressed
                if stub.uncompressed_size == 0xFF:
                    stub.uncompressed_size = uncompressed
                if stub.offset == 0xFF:
                    stub.offset = offset

            yield path, stub

    async def _calc_data_offset(self, offset: int) -> int:
        r = await self._request(offset, offset + 30)
        lfh = _LFHStub._make(_LFHStruct.unpack(r.content))

        # NOTE An encrypted file has encryption header following LFH.
        return (offset
                + 30  # LFH
                + lfh.path_size
                + lfh.extra_size)

    @staticmethod
    def _parse_msdos_date(date, time):
        # See: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-dosdatetimetofiletime
        # Microsoft was retarded from its early days.
        year = (date >> 9) + 1980
        month = date >> 5 & 0xF
        day = date & 0x1F
        hour = time >> 11
        minute = time >> 5 & 0x3F
        second = time & 0x1F

        return year, month, day, hour, minute, second * 2

    async def load_entries(self):
        if self.entries is not None:
            return

        r = await self.client.head(self.url)
        if r.status_code != 200:
            raise HTTPError(f"Got status code {r.status_code} for {self.url}")
        if r.headers.get('Accept-Ranges') != 'bytes':
            raise HTTPError(f"Range requests not supported on {self.url}")

        if size := r.headers.get('Content-Length'):
            self.size = int(size)
        else:
            raise HTTPError(f"Unable to determine length of zip file for {self.url}")

        eocd, eocd_start = await self._parse_eocd()

        # Load EOCD64 if Zip64 detected, and replace original EOCD.
        if self._detect_zip64_from_eocd(eocd):
            eocd64_start = await self._parse_eocd64_locator(eocd_start)
            eocd = await self._parse_eocd64(eocd64_start)

        self.entries = [ZipEntryInfo(path=path,
                                     raw_offset=info.offset,
                                     file_size=info.uncompressed_size,
                                     checksum=info.checksum,
                                     encrypted=bool(info.bitflag & 1),
                                     compression=ZipCompression(info.compression_mode),
                                     compressed_size=info.compressed_size,
                                     modified_date=self._parse_msdos_date(info.file_mdate, info.file_mtime),
                                     internal_attrs=info.internal_attrs,
                                     external_attrs=info.external_attrs)
                        async for path, info in self._parse_cd_ents(eocd.cd_offset, eocd.cd_size)]

    async def extract(self, info, output):
        offset = await self._calc_data_offset(info.raw_offset)

        # Nothing to do, so exit.
        if not info.compressed_size:
            return
        if info.encrypted:
            raise ZipError("Encrypted files are not supported")

        r = await self._request(offset,
                                offset + info.compressed_size, stream=True)

        match info.compression:
            case ZipCompression.NONE:
                decompressor = None
            case ZipCompression.DEFLATE:
                # Negative value for raw DEFLATE
                decompressor = zlib.decompressobj(-15)
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
                yield len(decompressed)

            decompressed = decompressor.flush()
            output.write(decompressed)
            yield len(decompressed)
        else:
            async for chunk in r.aiter_bytes():
                output.write(chunk)
                yield len(chunk)

    async def __aenter__(self):
        await self.load_entries()

        return self

    async def __aexit__(self, *args):
        pass
