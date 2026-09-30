"""krot-collect lives in the role that installs it; the tests import it from there."""

import os
import sys

# ⚠️ The role copies roles/collecting/files/krot_collect to the machine whole, and
# a __pycache__ written there by these tests would ride along from any checkout.
sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "roles", "collecting", "files"))
