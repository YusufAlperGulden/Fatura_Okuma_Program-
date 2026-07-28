import re

regex = re.compile(r"TAHS[İI]L", re.IGNORECASE)
print("TAHSİL matches:", bool(regex.search("TAHSİL")))
print("tahsil matches:", bool(regex.search("tahsil")))
print("tahsıl matches:", bool(regex.search("tahsıl")))
print("TAHSıL matches:", bool(regex.search("TAHSıL")))
