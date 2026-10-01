#!/usr/bin/env python3
"""Hourly autonomous runner."""
import os, sys, json, re, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ENGINE_HOME = Path(__file__).resolve().parent
DAEMON_HOME = ENGINE_HOME.parent
PAT = os.environ.get("GH_TOKEN", "")
FT = os.environ.get("FRANTIC_AGENT_TOKEN", "")
TG = os.environ.get("TG_TOKEN", "")
TC = os.environ.get("TG_CHAT", "")
SF = ENGINE_HOME / "state" / "hourly_state.json"

PRS = [("ritik4ever/stellar-bounty-board",p) for p in [1586,1587]] + \
     [("Ikalus1988/MisakaNet",2662)] + \
     [("auscaster/stompstart-startup-list",p) for p in [9,21,22]] + \
     [("Heliobond/frontend",676)] + \
     [("SecureBananaLabs/bug-bounty",p) for p in [12770,12771]] + \
     [("opensource-maintainer-toolkit/open-source-maintainer-toolkit",p) for p in [56,57,58]]

def load(): return json.loads(SF.read_text()) if SF.exists() else {"prev_w":{},"prev_c":{},"runs":0}
def save(s): SF.parent.mkdir(parents=True,exist_ok=True); SF.write_text(json.dumps(s,indent=2))
def gget(path):
    try:
        r=urllib.request.Request(f"https://api.github.com{path}",headers={"Authorization":f"token {PAT}","Accept":"application/vnd.github.v3+json","User-Agent":"hourly"})
        with urllib.request.urlopen(r,timeout=15) as resp: return json.loads(resp.read())
    except: return {}
def tg(msg):
    if not TG or not TC: print(f"[TG]: {msg[:200]}"); return
    try:
        d=json.dumps({"chat_id":TC,"text":msg,"parse_mode":"Markdown"}).encode()
        r=urllib.request.Request(f"https://api.telegram.org/bot{TG}/sendMessage",data=d,headers={"Content-Type":"application/json"})
        urllib.request.urlopen(r,timeout=10); print("[TG] sent")
    except Exception as e: print(f"[TG] fail: {e}")

def main():
    now=datetime.now(timezone.utc); print(f"\n=== HOURLY {now.isoformat()} ===")
    s=load(); s["runs"]+=1; s["last_run"]=now.isoformat(); n=s["runs"]
    merges=[]; comments=[]; walert=[]
    print("--- PRs ---")
    for repo,pr in PRS:
        d=gget(f"/repos/{repo}/pulls/{pr}")
        if d.get("merged") and not s.get("prev_c",{}).get(f"{repo}#{pr}_m"):
            merges.append(f"{repo}#{pr}"); s.setdefault("prev_c",{})[f"{repo}#{pr}_m"]=True; print(f"  MERGED {repo}#{pr}")
        cd=gget(f"/repos/{repo}/issues/{pr}/comments?per_page=3&sort=created&direction=desc")
        if isinstance(cd,list) and cd:
            u=cd[0].get("user",{}).get("login","?")
            if u not in ("makar52nn2016-jpg","vercel[bot]") and "github-actions" not in u:
                b=cd[0].get("body","")[:80].replace("\n"," "); c=cd[0].get("created_at","")
                k=f"{repo}#{pr}"
                if c!=s.get("prev_c",{}).get(k):
                    comments.append(f"@{u}: {b}"); s.setdefault("prev_c",{})[k]=c; print(f"  COMMENT {u} on {repo}#{pr}")
    print("--- Wallets ---")
    w={}
    try:
        r=urllib.request.urlopen("https://horizon.stellar.org/accounts/GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ",timeout=10)
        w["XLM"]=float([b["balance"] for b in json.loads(r.read())["balances"] if b["asset_type"]=="native"][0])
    except: w["XLM"]=s.get("prev_w",{}).get("XLM",0)
    try:
        r=urllib.request.urlopen("https://tonapi.io/v2/accounts/UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH",timeout=10)
        w["TON"]=json.loads(r.read()).get("balance",0)/1e9
    except: w["TON"]=s.get("prev_w",{}).get("TON",0)
    for k,v in w.items():
        p=s.get("prev_w",{}).get(k,0)
        if v>p: walert.append(f"+{v-p:.6f} {k}")
        print(f"  {k}: {v}")
    s["prev_w"]=w
    print("--- Frantic ---")
    al=False; earned=0; inv=0
    if FT:
        try:
            r=urllib.request.Request("https://gofrantic.com/v1/agents/agent-b94b60/status",headers={"Authorization":f"Bearer {FT}"})
            d=json.loads(urllib.request.urlopen(r,timeout=15).read())
            a=d.get("agent",{}); al=a.get("situation",{}).get("open",False); earned=a.get("earnedUsd",0); inv=len(a.get("invites",[]))
            print(f"  Arena:{al} Earned:${earned} Invites:{inv}")
        except: print("  Frantic fail")
    print("--- Bounties ---")
    bd=gget("/search/issues?q=%22Bounty+%24%22+state:open+label:%22good+first+issue%22+comments:0..2&per_page=5")
    nb=[]
    if isinstance(bd,dict) and "items" in bd:
        for i in bd["items"][:3]:
            if i.get("pull_request"): continue
            am=max([int(x) for x in re.findall(r'\$(\d+)',i.get("title","")+" "+(i.get("body") or "")[:500])],default=0)
            if am>=10: nb.append(f"${am} {i.get('number')}"); print(f"  Found ${am}")
    print("--- Self-learning ---")
    lessons=[]
    if merges: lessons.append(f"Merges: {merges}")
    if walert: lessons.append(f"Money: {walert}")
    if comments: lessons.append(f"Comments: {len(comments)}")
    if inv>0: lessons.append(f"Invites: {inv}")
    kb=DAEMON_HOME/"KNOWLEDGE_BASE.md"
    if kb.exists() and lessons:
        c=kb.read_text()
        for l in lessons:
            if l not in c: c+=f"\n## {now.strftime('%Y-%m-%d')}: {l}\n"
        kb.write_text(c)
        for l in lessons: print(f"  {l}")
    save(s)
    rpt=f"Hourly #{n}: {len(merges)} merges, {len(comments)} comments, XLM={w.get('XLM',0)}, TON={w.get('TON',0)}, Frantic=${earned}, Arena={al}"
    print(f"\n{rpt}")
    if walert: tg(f"💰 MONEY! {', '.join(walert)}")
    elif merges: tg(f"✅ MERGED! {', '.join(merges)}")
    elif not al: tg("⚠️ Frantic Arena down!")
    else: tg(rpt)
    print("✅ Done")

if __name__=="__main__": main()
