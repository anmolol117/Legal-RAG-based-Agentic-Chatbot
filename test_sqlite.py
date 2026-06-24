import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

conn = sqlite3.connect(":memory:", check_same_thread=False)
memory = SqliteSaver(conn)
try:
    memory.setup()
    print("Setup succeeded")
except Exception as e:
    print("Setup failed:", e)
