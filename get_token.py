import requests

AUTH_CODE = "ec934b41a2822376de68a30d2ee471193cc45f39"

response = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": "179724",
        "client_secret": "3f77e89798fed5b04de5c58d355e50cd28ea443d",
        "code": AUTH_CODE,
        "grant_type": "authorization_code"
    }
)

print("\n--- Strava Response ---")
print(response.json())
print("\nCopy the value of 'refresh_token' from above — you'll paste that into your main script.")
