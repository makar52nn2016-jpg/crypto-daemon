#!/usr/bin/env python3
import os, json, urllib.request, urllib.error
TOKEN = os.environ.get('FRANTIC_TOKEN', '')
KID = os.environ.get('AGENT_KID', 'agent-b94b60')
ACTION = os.environ.get('ACTION', 'status')
BID = os.environ.get('BOUNTY_ID', '0')
URL = os.environ.get('ARTIFACT_URL', '')

def api(u, method='GET', body=None):
    req = urllib.request.Request(u, method=method)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'frantic-bot')
    if body: req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'body': e.read().decode()[:500]}
    except Exception as e:
        return {'error': str(e)[:300]}

print('Agent:', KID, '| Action:', ACTION, '| Bounty:', BID)

if ACTION == 'status':
    d = api('https://gofrantic.com/v1/agents/' + KID + '/status')
    agent = d.get('agent', {}) if isinstance(d, dict) else {}
    work = d.get('work', {}) if isinstance(d, dict) else {}
    print('Eligible:', agent.get('eligible'))
    print('Earned USD:', agent.get('earnedUsd'))
    print('Work summary:', work.get('summary', {}))
    opens = work.get('open', []) or []
    print('Open claims:', len(opens))
    for c in opens:
        # Print all fields
        print('  Claim:', json.dumps(c, indent=2)[:500])
elif ACTION == 'list':
    d = api('https://gofrantic.com/v1/board')
    bounties = d.get('board', {}).get('open_bounties', []) or []
    print('Total open bounties:', len(bounties))
    for b in bounties[:15]:
        cp = b.get('claim_progress', {}) or {}
        print('  #{} ${} | {}/{} slots | {}'.format(b.get('number'), b.get('price_usd'), cp.get('available'), cp.get('capacity'), b.get('title', '')[:60]))
elif ACTION == 'claim':
    d = api('https://gofrantic.com/v1/claims', method='POST', body={'bounty': int(BID), 'agent_kid': KID})
    print(json.dumps(d, indent=2)[:2000])
elif ACTION == 'deliver':
    # Get the most recent claim_id for this bounty
    d = api('https://gofrantic.com/v1/agents/' + KID + '/status')
    print('Status response work keys:', list(d.get('work', {}).keys()) if isinstance(d, dict) else d)
    opens = d.get('work', {}).get('open', []) or []
    print('Open claims full:', json.dumps(opens, indent=2)[:1000])
    claim_id = None
    for c in opens:
        b = c.get('bounty', {})
        bnum = b.get('number') if isinstance(b, dict) else b
        if str(bnum) == BID:
            claim_id = c.get('id') or c.get('claim_id') or c.get('claimId')
            break
    print('Claim ID:', claim_id)
    if not claim_id:
        print('No active claim for bounty', BID, '- try /v1/claims endpoint')
        exit(1)
    d = api('https://gofrantic.com/v1/deliveries', method='POST', body={'claim_id': claim_id, 'agent_kid': KID, 'artifact_refs': ['public_url=' + URL]})
    print(json.dumps(d, indent=2)[:2000])
elif ACTION == 'claims':
    # List all claims
    d = api('https://gofrantic.com/v1/claims')
    print(json.dumps(d, indent=2)[:2000])
