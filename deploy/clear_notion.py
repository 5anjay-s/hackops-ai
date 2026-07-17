"""Clear all pages from the Hackathon Tracker database."""
import requests

TOKEN = "ntn_t3475349150aDGTsQuAXEhvS6I8NhDvwMhyFB3eJNZa5Rt"
DATABASE_ID = "3a00cf259e9e8064a44efecb2cf3ab32"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

print("Querying all pages...")
all_pages = []
has_more = True
next_cursor = None

while has_more:
    body = {"page_size": 100}
    if next_cursor:
        body["start_cursor"] = next_cursor
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
        headers=HEADERS,
        json=body,
    )
    data = resp.json()
    all_pages.extend(data.get("results", []))
    has_more = data.get("has_more", False)
    next_cursor = data.get("next_cursor")

print(f"Found {len(all_pages)} pages. Archiving all...")

for i, page in enumerate(all_pages, 1):
    requests.patch(
        f"https://api.notion.com/v1/pages/{page['id']}",
        headers=HEADERS,
        json={"archived": True},
    )
    if i % 10 == 0:
        print(f"  Archived {i}/{len(all_pages)}...")

print(f"Done! Archived {len(all_pages)} pages. Database is now empty.")
