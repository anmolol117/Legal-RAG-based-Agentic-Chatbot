import sys
from rag.chain import LegalRAGChain

chain = LegalRAGChain()
res = chain.agent.invoke({"messages": [("user", "What is Section 498A?")]}, config={"configurable": {"thread_id": "debug1"}})
print("====== RAW RESPONSE ======")
print(res)
print("====== MESSAGES ======")
for i, m in enumerate(res["messages"]):
    print(f"Message {i}: type={type(m)}, content={repr(m.content)}")
    if hasattr(m, 'tool_calls'):
        print(f"  Tool calls: {m.tool_calls}")
