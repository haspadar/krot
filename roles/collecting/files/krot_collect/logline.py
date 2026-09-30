"""One line of an nginx access log, in a format known by name.

⚠️ One regular expression over the whole line, never a split on spaces.
`$time_local` is `22/Aug/2026:00:39:03 +0300` — a space inside the field — so
every field after it shifts by one and an address read by position is a timezone
offset. The earlier implementation found that the expensive way: `awk` printed
plausible numbers with exit code 0.

The format belongs to whoever writes the vhosts, not to this program. A new one
is a new entry in FORMATS and a test, never a guess from a sample.
"""

import re
from datetime import date

FORMATS = {
    # [$time_local] $remote_addr - $host "$request" $status $body_bytes_sent
    # "$http_referer" "$http_user_agent" cf=$http_cf_ipcountry rt=$request_time
    #
    # Everything past the agent is optional, and deliberately so: `cf=` and
    # `rt=` joined the format after the first sites went live, and a fortnight of
    # archives still holds lines that end at the agent. Requiring them would turn
    # each of those into an unreadable line — a louder and different failure than
    # a missing response time.
    "time_first": re.compile(
        r'^\[(?P<day>\d{2}/[A-Za-z]{3}/\d{4}):\d{2}:\d{2}:\d{2}\s'
        r'(?P<zone>[-+]\d{4})\]\s'
        r'(?P<address>\S+)\s-\s'
        r'(?P<host>\S+)\s'
        r'"(?P<request>[^"]*)"\s'
        r'(?P<status>\d{3})\s'
        r'(?P<bytes>\d+)\s'
        r'"[^"]*"\s'
        r'"(?P<agent>[^"]*)"'
        r'(?:.*?\srt=(?P<rt>\d+\.\d+))?',
        re.ASCII,
    ),
}

MONTHS = {name: number for number, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


class LogLine:
    __slots__ = ("day", "address", "path", "status", "bytes", "agent", "response_time")

    def __init__(self, day, address, path, status, size, agent, response_time=None):
        self.day = day
        self.address = address
        # The path asked for, without the method or the protocol: what separates a
        # crawler from something wearing its name — a crawler reads pages the site
        # offers, a scan asks for `/.env`.
        self.path = path
        self.status = status
        self.bytes = size
        self.agent = agent
        # ⚠️ None rather than zero, and the distinction is the reason it exists.
        # Zero is real and common — a 304 on a static file writes `rt=0.000` — so a
        # line without the field, counted as zero, would drag a slow site's average
        # down and make a machine under load read as a fast one.
        self.response_time = response_time


def read(line, pattern):
    """The line, or None when it is not one.

    None rather than an exception: a request arriving before a vhost is fully
    written lands in the file half-formed and stays there until it rotates out,
    and one such line must not stop a night's collection.
    """
    found = pattern.match(line)
    if found is None:
        return None
    day_text = found.group("day")
    month = MONTHS.get(day_text[3:6].lower())
    try:
        # The date as the machine wrote it, with its own offset — never converted
        # to UTC. A hit logged at 00:39 +0300 belongs to that calendar day for the
        # operator reading the log; shifting it would move the first hours of
        # every day into the day before, and the figures would disagree with the
        # file anyone checks them against.
        day = date(int(day_text[7:11]), month, int(day_text[0:2])) if month else None
    except ValueError:
        return None
    if day is None:
        return None
    rt = found.group("rt")
    return LogLine(
        day=day,
        address=found.group("address"),
        path=path_of(found.group("request")),
        status=int(found.group("status")),
        size=int(found.group("bytes")),
        agent=found.group("agent"),
        response_time=float(rt) if rt else None,
    )


def path_of(request):
    """What sits between the first and second space, or the whole field without one.

    A malformed request line still says what was asked for, and dropping it would
    hide exactly the requests worth seeing — a scanner sends plenty no browser would.
    """
    parts = request.split(" ")
    return parts[1] if len(parts) > 1 else request
