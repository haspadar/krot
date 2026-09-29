"""krot-index lives in the role that installs it; the tests import it from there."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "roles", "indexing", "files"))
