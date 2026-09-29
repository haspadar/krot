"""krot-index lives in the role that installs it; the tests import it from there."""

import os
import sys

# ⚠️ The role copies roles/indexing/files/krot_index to the machine whole, and a
# __pycache__ written there by these tests would ride along from any checkout
# they ran in — this Mac's bytecode, changed on every run.
sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "roles", "indexing", "files"))
