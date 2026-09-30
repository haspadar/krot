"""The log files of one site, newest first, gzip included.

nginx keeps a fortnight (`rotate 14`, `compress`, `delaycompress`: yesterday's
file is plain, the ones before gzipped). Reading only today's would open every
screen on a graph that starts at nothing, for history that is already on disk.
"""

import glob
import gzip
import os
import re
import struct
import zlib

ROTATION = re.compile(r"\.log\.(\d+)(\.gz)?$")


class Unreadable(Exception):
    """A log file that exists and cannot be read, or cannot be read whole.

    Its own type because it must never pass for an empty one. Both give no lines,
    and only one means "no crawler came" — the other means the collector is blind
    and has been writing that answer down every night. The case is real: nginx
    writes these `0640 www-data adm`, and an account outside `adm` gets
    Permission denied on every one.
    """


def age(path):
    """Rotations back: 0 for the live file, 1 for yesterday's, and so on."""
    found = ROTATION.search(path)
    return int(found.group(1)) if found else 0


class LogFiles:
    def __init__(self, directory="/var/log/nginx", pattern="{domain}-access.log*"):
        self.directory = directory
        self.pattern = pattern

    def of(self, domain):
        """Paths for one site, newest first.

        By the rotation NUMBER, not by name: `.10.gz` sorts before `.2.gz` as text,
        which would hand back a fortnight shuffled and make "stop at a day already
        collected" stop at the wrong place.
        """
        found = glob.glob(os.path.join(self.directory, self.pattern.replace("{domain}", glob.escape(domain))))
        return sorted(found, key=age)

    def lines(self, path):
        """The lines of one file, one at a time, gzipped or not.

        A generator: the busiest site writes tens of thousands of lines a day and a
        first run takes in fourteen files at once, on a machine that has no memory
        to hold them.
        """
        compressed = path.endswith(".gz")
        try:
            handle = gzip.open(path, "rb") if compressed else open(path, "rb")
        except OSError as failure:
            raise Unreadable("cannot read %s (%s) — the account needs to be in the log group"
                             % (path, failure.strerror or failure)) from failure
        read = 0
        try:
            try:
                for raw in handle:
                    read += len(raw)
                    yield raw.rstrip(b"\r\n").decode("utf-8", "surrogateescape")
            except (OSError, EOFError, zlib.error) as failure:
                raise Unreadable("cannot read %s whole (%s)" % (path, failure)) from failure
        finally:
            handle.close()
        # ⚠️ A truncated archive can stop like a whole one. The earlier
        # implementation measured a `.gz` cut mid-stream yielding two of its three
        # lines in silence — stored, that undercount is marked collected and never
        # read again. gzip's own trailer carries the uncompressed length; a file
        # that delivered fewer bytes than it promised was cut.
        if compressed and read != declared_length(path):
            raise Unreadable("%s is truncated: it read %d bytes, its trailer promises %s"
                             % (path, read, declared_length(path)))


def declared_length(path):
    """The uncompressed length a gzip file claims in its last four bytes, or None.

    32 bits, so it wraps above 4 GB — a false truncation, which errs toward
    refusing to collect rather than toward storing an undercount as fact.
    """
    try:
        with open(path, "rb") as handle:
            handle.seek(-4, os.SEEK_END)
            trailer = handle.read(4)
    except OSError:
        return None
    if len(trailer) != 4:
        return None
    return struct.unpack("<I", trailer)[0]
