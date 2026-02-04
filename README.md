# zipinspect

![PyPI - Version](https://img.shields.io/pypi/v/zipinspect?style=for-the-badge)


PKWare's [Zip](https://en.wikipedia.org/wiki/ZIP_(file_format)) is the ubiquitous format for file archival; so much so that it's considered both a noun and verb. Invented in 1989, it has been extensively used to compress or seamlessly transfer multiple files. Zip has one major advantage over [Tarballs](https://en.wikipedia.org/wiki/Tar_(computing)) — random access. Some (especially UNIX purists) may criticise Zip for worse compression ratios if there's data redundancy present amongst files in the archive, because it compresses file individually. However, that its strongest points too; it enables us to extract a single file without decompressing the whole archive, unlike compressed tarballs. And, not only that, it enables fast append/update/deletes, which is not possible Tarballs, without decompressing and creating one anew.

This tool covers a rather niche usecase — Zip files on the network, accessed using HTTP. HTTP has a neat feature called [range requests](https://http.dev/range-request), which is extensively used here; in your browser it's typically used for resumable downloads. In a nutshell, it's a variant of the normal GET request wherein the client signals the range of data it's interested in, and server responds accordingly with 206 status code. Here, this is what allows for random access of files.

## Demo

```sh
$ zipinspect 'https://example.com/ArthurRimbaud-OnlyFans.zip'
> list
  #  entry                    size    modified date
---  -----------------------  ------  -------------------
  0  ArthurRimbaudOF_001.jpg  2.2M    2024-11-07T18:41:46
  1  ArthurRimbaudOF_002.jpg  2.4M    2024-11-07T18:41:48
  2  ArthurRimbaudOF_003.jpg  2.4M    2024-11-07T18:41:50
  3  ArthurRimbaudOF_004.jpg  2.5M    2024-11-07T18:41:50
  4  ArthurRimbaudOF_005.jpg  2.3M    2024-11-07T18:41:52
  5  ArthurRimbaudOF_006.jpg  2.4M    2024-11-07T18:41:52
  6  ArthurRimbaudOF_007.jpg  2.2M    2024-11-07T18:41:54
  7  ArthurRimbaudOF_008.jpg  2.4M    2024-11-07T18:41:56
  8  ArthurRimbaudOF_009.jpg  2.4M    2024-11-07T18:41:56
  9  ArthurRimbaudOF_010.jpg  2.3M    2024-11-07T18:41:58
 10  ArthurRimbaudOF_011.jpg  2.5M    2024-11-07T18:41:58
 11  ArthurRimbaudOF_012.jpg  1.5M    2024-11-07T18:42:00
 12  ArthurRimbaudOF_013.jpg  2.4M    2024-11-07T18:42:00
 13  ArthurRimbaudOF_014.jpg  2.6M    2024-11-07T18:42:02
 14  ArthurRimbaudOF_015.jpg  2.8M    2024-11-07T18:42:02
 15  ArthurRimbaudOF_016.jpg  2.8M    2024-11-07T18:42:04
 16  ArthurRimbaudOF_017.jpg  2.3M    2024-11-07T18:42:04
 17  ArthurRimbaudOF_018.jpg  2.9M    2024-11-07T18:42:06
 18  ArthurRimbaudOF_019.jpg  3.1M    2024-11-07T18:42:08
 19  ArthurRimbaudOF_020.jpg  2.9M    2024-11-07T18:42:08
 20  ArthurRimbaudOF_021.jpg  3.1M    2024-11-07T18:42:10
 21  ArthurRimbaudOF_022.jpg  3.1M    2024-11-07T18:42:10
 22  ArthurRimbaudOF_023.jpg  3.1M    2024-11-07T18:42:12
 23  ArthurRimbaudOF_024.jpg  3.0M    2024-11-07T18:42:14
 24  ArthurRimbaudOF_025.jpg  2.9M    2024-11-07T18:42:14
(Page 1/14)
> extract 8

 |#######################################################################| 100%

> extract 8,9,16

 |#######################################################################| 100%

> extract 20,...,24
 
 |#######################################################################| 100%

> 
```

First the entries in the archive — files and directories — are loaded, and the user is presented with a REPL (command prompt), where the files could be easily browsed and extracted. Multiple entries could be downloaded concurrently thanks to its underlying asynchronous implementation.

## Installation

```
$ pip install zipinspect
```

### uv

```
$ uv tool install zipinspect
```

## Features & Limitations

- Multiple parallel extractions.
- HTTP/2 for better download performance.
- Zip files over 4GiB (Zip64) supported.
- DEFLATE, BZip2, LZMA and [Zstd](https://en.wikipedia.org/wiki/Zstd) compression supported.
- ZipCrypto or WinZip AES aren't supported.
- Multi-part (spanned) files aren't supported.

## Help

In the REPL, `help` command lists all the available commands and their corresponding arguments.                   
    > help
    This is the REPL, and the following commands are available.
    
    list                            List entries in the current page
    prev                            Go backward one page and show entries
    next                            Go forward one page and show entries
    extract <index> [dir]           Extract entry with index <index>
    extract <start>,...,<end> [dir] Extract entries from <start> to <end>
    extract <i0>,<i1>,...<in> [dir] Extract entries with specified indices
    
    NOTE: The extract command accepts an optional path to the directory to extract into.
    If not provided, it extracts into the current working directory

If any of the arguments contains a space wrap it in a double-quote; or if it contains a double quote, wrap in a double quote and backslash-escape it.

## Remarks

Initially, [zipfile](https://docs.python.org/3/library/zipfile.html#zipfile-objects) was considered along with a seekable file-like interface into the remote file using HTTP transport. Although the prototype worked, but it was nowhere near as performant as it is now. The major issue was that, through the abstract interface sequential accesses couldn't be differentiated with random accesses. 

Technically only sequential access is possible with HTTP, because HTTP is a stateless protocol; but to support our needs, random accesses are implemented using HTTP range requests. This isn't without performance penalty, as for each request the server has to setup a handler to serve that request; so we have to minimise these if the amount of data to be read is known in advance. We do [know the compressed size], but unfortunately the `zipfile` API isn't aware all these complexities, so it does a lot of unnecessary seeks that prevents any possible optimisations. 

### The solution? 

Implement the Zip specification from scratch, preferably with asynchronous API to allow concurrent extractions. That's what was done. Much the information on implementation was derived from the Wikipedia page and PKWare [APPNOTE.txt](https://pkwaredownloads.blob.core.windows.net/pkware-general/Documentation/APPNOTE-6.3.9.TXT). It's not entirely specification-compliant, but hopes to function in majority of the cases.

