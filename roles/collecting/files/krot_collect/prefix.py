"""An address range a crawler's operator publishes, and whether an address is in it."""

import ipaddress
import re

MASK = re.compile(r"^\d{1,3}$", re.ASCII)

# The widest mask a published crawler range can plausibly carry. ⚠️ A range too
# WIDE is the dangerous mirror of a stripped mask: `0.0.0.0/0` reads as valid and
# then confirms every address on the internet for its family — the check does not
# fail, it silently stops checking. The widest any operator publishes is a /8.
NARROWEST = {4: 8, 6: 16}


def _split(text):
    text = text.strip()
    if "/" not in text:
        return None
    address, mask = text.split("/", 1)
    if not MASK.match(mask):
        return None
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return None
    return text, parsed, int(mask)


def shaped_like_a_range(text):
    """Shaped like a range, whatever its width.

    Apart from read(): a source publishing something too wide must not count as a
    source publishing malformed lines — three odd lines would refuse a list of
    hundreds, leaving the family judged by yesterday's ranges while nothing said so.
    """
    split = _split(text)
    return split is not None and split[2] <= split[1].max_prefixlen


class Prefix:
    def __init__(self, text, network):
        # As the source wrote it: rebuilding would rewrite `34.22.85.7/24` as
        # `34.22.85.0/24`, and a stored list differing from its source cannot be
        # compared with it by eye.
        self.text = text
        self.network = network

    def holds(self, address):
        """Whether the address is inside; an address of the other family is outside."""
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        return parsed.version == self.network.version and parsed in self.network


def read(text):
    """The range, or None when the text is not one.

    ⚠️ None for an address WITHOUT a mask, deliberately. An aggregator once served
    Googlebot's list as 2146 bare addresses — every /24 flattened to its first
    address — with HTTP 200. Read as /32 they cover 4 of 80 live Googlebot
    addresses, and the real crawler becomes an impostor. Refusing lets the answer
    be judged malformed as a whole.
    """
    split = _split(text)
    if split is None:
        return None
    written, address, bits = split
    if bits > address.max_prefixlen or bits < NARROWEST[address.version]:
        return None
    # strict=False: `1.2.3.4/24` and `1.2.3.0/24` are one range, and both
    # spellings are common and harmless.
    return Prefix(written, ipaddress.ip_network("%s/%d" % (address, bits), strict=False))
