import os
import sys

# Add the project directory to path so we can import integrators
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from integrators.uyumsoft_api import _customer_display_name

print("TESTING ChatGPT's FALLBACK LOGIC...\n")

# Scenario 1: Missing Name, valid VKN
data1 = {
    "customer_name": None,
    "customer_title": "",
    "customer": None
}
vkn1 = "1122334455"
print(f"Scenario 1 - Name: None, VKN: {vkn1}")
print(f"Result: {_customer_display_name(data1, vkn1)}\n")

# Scenario 2: Missing Name, missing/invalid VKN (0000000000)
data2 = {
    "customer_name": "",
    "customer_title": None,
    "customer": ""
}
vkn2 = "0000000000"
print(f"Scenario 2 - Name: None, VKN: {vkn2}")
print(f"Result: {_customer_display_name(data2, vkn2)}\n")

# Scenario 3: Missing Name, completely missing VKN
data3 = {}
vkn3 = ""
print(f"Scenario 3 - Name: None, VKN: empty")
print(f"Result: {_customer_display_name(data3, vkn3)}\n")

