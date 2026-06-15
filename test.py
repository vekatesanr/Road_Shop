import base64

with open("credentials.json",
"rb") as f:
[Convert]::ToBase64String(
[IO.File]::ReadAllBytes("credentials.json")
)
    print(base64.b64encode(f.read()).decode())