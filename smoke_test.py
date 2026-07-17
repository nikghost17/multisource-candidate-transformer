import requests

h = requests.get("http://localhost:8001/health").json()
print("Health:", h)

with open("input/test_recruiter1.csv", "rb") as f:
    r = requests.post(
        "http://localhost:8001/candidates/from-csv",
        files={"file": ("test_recruiter1.csv", f, "text/csv")},
        data={"enable_llm": "false"},
    )

d = r.json()
print(f"Status: {r.status_code}")
print(f"Ingested: {len(d.get('candidate_ids', []))} candidates")
for c in d.get("candidates", []):
    skills = [s["name"] for s in c.get("skills", [])[:3]]
    print(f"  {c['full_name']} | conf={c['overall_confidence']} | skills={skills}")
