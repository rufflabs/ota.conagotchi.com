# boot.py — runs once before main.py on every power-on / reset.
# Keep this minimal; heavy initialisation belongs in main.py.

import gc
gc.collect()
