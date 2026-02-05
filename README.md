# zipinspect

![PyPI - Version](https://img.shields.io/pypi/v/zipinspect?style=for-the-badge)

Zip files on the network — a niche use case, but still an interesting one to cover. This tool aims to extract individual files from Zip files over HTTP without downloading the whole file. It depends on the fact that HTTP [range requests](https://en.wikipedia.org/wiki/Byte_serving) are available (i.e. downloading the file can be resumed), otherwise it refuses to operate as it would defeat the purpose of this tool.

## Installation

```
$ pip install zipinspect
```

### uv

```
$ uv tool install zipinspect
```

## Demo

```sh
# If uvx (astral.sh/uv) is avaiable, an installation is not required; just use
#
# 	uvx zipinspect 'https://example.com/ArthurRimbaud-OnlyFans.zip'
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

First the entries in the archive are loaded, then the user is presented with a REPL, where the files could be browsed and extracted. Multiple entries could be downloaded currently using the range syntax, and the downloads are fast because of its asynchronous design.

## Features & Limitations

- Multiple parallel extractions.
- HTTP/2 for better download performance.
- Zip files over 4GiB (Zip64) supported.
- DEFLATE, BZip2, LZMA and [Zstd](https://en.wikipedia.org/wiki/Zstd) compression supported.
- ZipCrypto or WinZip AES aren't supported.
- Multi-part (spanned) files aren't supported.

## Help

In the REPL, `help` command lists all the available commands and their corresponding arguments.                   
```
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
```

1. If any of the arguments contain a space wrap it in a double-quote; if it contains a double quote, wrap in a double quote and backslash-escape it.
2. If an index to a directory is provided to extract, it downloads the files and folders within it recursively.
3. If a file or folder already exists in the filesystem, it **doesn't ask for permission to overwrite it.**

## How it works

The Zip format compresses each files individually, unlike some other formats (e.g. [Tarballs](https://en.wikipedia.org/wiki/Tar_(computing))), and stores offsets to file entries along with all necessary metadata in its **central directory**, which is located at the end of the file. The existence of a central directory allows us to extract, not the whole archive, but just the file we're interested in. Though this might not translate to much for Zip files available locally, it however provides a great advantage when Zip files exist remotely (see [this](https://www.djmannion.net/partial_zip/)). 

### An Example

For instance, assume you have a large Zip archive full of pictures — weighing 42 GiB — stored on a remote server far away, and you require to fetch a few images worth 21 MiB. Now, would you rather download the entire archive and then extract the files you need, or would you rather download just the files you need? It depends on the speed of your connection, storage capacity, and patience. Not everyone has the luxury to afford these.

### The procedure

Since, most people are unable to afford such lavish lifestyles, this tool comes in handy. When you run it with a URL,

1. The list of entries in the Zip archive are loaded in first, reading the central directory record.
2. The user can interactively browse the list of present entries using `prev`, `next` and `list` commands.
3. File(s) could be extracted using the `extract` command with [fearless concurrency](https://gist.github.com/cynthia2006/584f518161cfcba9a745afd94c903304) and [![blazingly fast](https://www.blazingly.fast/api/badge.svg?repo=cynthia2006%2Fzipinspect)](https://www.blazingly.fast)speeds.

The result? You don't waste bandwidth more than the size of the files you asked for.

## Remarks

The initial implementation consisted of [zipfile](https://docs.python.org/3/library/zipfile.html#zipfile-objects), along with a seekable file object wrapper for the remote file. Though the prototype worked, its performance was abysmal. The major bottleneck of this naive approach was that, through the abstract interface sequential accesses couldn't be differentiated with random accesses. 

Technically speaking, only sequential access is possible via HTTP, because it's a stateless protocol, but to support our needs, random accesses in the file are implemented using HTTP range requests. This incurs a performance penalty, and quite noticeable too even with a single transfer; for each GET request the server has to setup a handler (CGI, FastCGI, et al.), open the file, seek to a position, and various other tasks to be able to respond. Thus considering this overhead, we have to minimise the number of requests if the amount of data to be read is known in advance. Fortunately, we do, but `zipfile` API is oblivious to all these complexities about its interface, so it performs lots of unnecessary seeks that prevents optimisations to be made.

### The solution? 

Implement the Zip specification from scratch, preferably with an asynchronous API to allow concurrent extractions. That's what was done in this case — an HTTP-aware Zip extractor implementation. Much of the information concerning the format was derived from the Wikipedia page and PKWare's original [APPNOTE.txt](https://pkwaredownloads.blob.core.windows.net/pkware-general/Documentation/APPNOTE-6.3.9.TXT) (Zip specification). Though it's not entirely on par the specification or more mature implementations, but it hopes to work in the majority of the cases. If you need a feature, open a Github Issue.

