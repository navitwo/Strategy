import sys
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import list_projects, request

# reconcile: was the project created despite null response?
found = [p for p in list_projects() if p["name"] == "NQ CISD IFVG 2026"]
print("existing matches:", found)
if not found:
    d = request("projects/create", {"name": "NQ CISD IFVG 2026",
                                    "organizationId": "08ae00e33d9cd7bd35c1349683d7d3d4",
                                    "language": "Py"})
    print("create keys:", sorted(d.keys()))
    print("success:", d.get("success"))
    pj = d.get("projects") or d.get("project") or d.get("projectId")
    print("project field type:", type(pj).__name__)
    if isinstance(pj, list) and pj:
        print("list item keys:", sorted(pj[0].keys()) if isinstance(pj[0], dict) else pj[0])
    if isinstance(pj, dict):
        print("dict keys:", sorted(pj.keys()))
    elif pj is not None:
        print("value:", pj)
