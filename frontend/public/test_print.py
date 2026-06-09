import urllib.request
import json

convo_name = "projects/gilbertos-project-340619/locations/global/conversations/d13cc0d2-d3b7-4525-818f-e676e9a4d70e"
msg_url = f"http://localhost:8000/api/messages/{urllib.parse.quote(convo_name)}"
msg_resp = urllib.request.urlopen(msg_url)
messages = json.loads(msg_resp.read().decode('utf-8'))

merged_sys = {
    "text": {"parts": []},
    "schema": {},
    "data": {},
    "chart": {}
}

for m in messages[6:]:
    if "systemMessage" in m:
        sys = m["systemMessage"]
        if "text" in sys and "parts" in sys["text"]:
            merged_sys["text"]["parts"].extend(sys["text"]["parts"])
        if "schema" in sys:
            merged_sys["schema"].update(sys["schema"])
        if "data" in sys:
            merged_sys["data"].update(sys["data"])
        if "chart" in sys:
            merged_sys["chart"].update(sys["chart"])

print("chart result keys:", list(merged_sys["chart"].get("result", {}).keys()))
print("chart result content:", merged_sys["chart"].get("result"))
