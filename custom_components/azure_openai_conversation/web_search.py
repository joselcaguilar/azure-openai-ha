import requests

def google_search(query, api_key, cx, timeout=5):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "hl": "it",
        "num": 5,
    }

    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item["title"],
            "snippet": item["snippet"],
            "link": item["link"]
        })

    return results
