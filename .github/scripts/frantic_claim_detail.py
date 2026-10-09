#!/usr/bin/env python3
import os, json, urllib.request, urllib.error
TOKEN = os.environ.get('FRANTIC_TOKEN', '')
CLAIM_ID = os.environ.get('CLAIM_ID', '467ca1b3-d99d-44ec-8fe5-134e3f118282')
KID = os.environ.get('AGENT_KID', 'agent-b94b60')

def api(u):
    req = urllib.request.Request(u)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/json')
    req.add_header('User-Agent', 'frantic-bot')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'body': e.read().decode()[:500]}
    except Exception as e:
        return {'error': str(e)[:300]}

print('=== Claim', CLAIM_ID, 'details ===')
d = api('https://gofrantic.com/v1/claims/' + CLAIM_ID)
print(json.dumps(d, indent=2)[:3000])
