from typing import NamedTuple

class _CDFHStub(NamedTuple):
    signature: bytes
    maker_version: int
    version_needed: int
    bitflag: int
    compression_mode: int
    file_mtime: int
    file_mdate: int
    checksum: int
    compressed_size: int
    uncompressed_size: int
    path_size: int
    extra_size: int
    comment_size: int
    begin_disk: int
    internal_attrs: int
    external_attrs: int
    offset: int

class _EOCDStub(NamedTuple):
    signature: bytes
    disk: int
    begin_disk: int
    ents_on_disk: int
    ents_total: int
    cd_size: int
    cd_offset: int

class _EOCD64Stub(NamedTuple):
    signature: bytes
    size: int
    make_version: int
    version_needed: int
    disk: int
    begin_disk: int
    ents_on_disk: int
    ents_total: int
    cd_size: int
    cd_offset: int

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