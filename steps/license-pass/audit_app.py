"""The license audit page: one project per screen, answers saved to a TSV after each click.

  python3 -I audit_app.py [--port 2731]

It listens on 127.0.0.1 only (reach it through an SSH local forward). Items: work/audit/items.json
(80_audit_items.py). Answers: work/audit/answers.tsv (project, verdict, note, time; the last answer of a
project counts). /results shows the error rate with its 95% interval.
"""
import argparse
import csv
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = f"{HERE}/work/audit"
ITEMS = f"{AUDIT}/items.json"
ANSWERS = f"{AUDIT}/answers.tsv"
HOST = "127.0.0.1"
VERDICTS = ("right", "wrong", "unsure")
LOCK = threading.Lock()


def load_items():
    with open(ITEMS) as f:
        return json.load(f)


def load_answers():
    out = {}
    if os.path.exists(ANSWERS):
        with open(ANSWERS, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                out[r["project"]] = r
    return out


def save_answer(project, verdict, note):
    with LOCK:
        ans = load_answers()
        ans[project] = {"project": project, "verdict": verdict, "note": note,
                        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        tmp = ANSWERS + ".tmp"
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["project", "verdict", "note", "time"], delimiter="\t",
                               lineterminator="\n")
            w.writeheader()
            for p in sorted(ans):
                w.writerow(ans[p])
        os.replace(tmp, ANSWERS)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def results(items, ans):
    """Error rates: unweighted (Wilson interval) and weighted by stratum size (normal interval)."""
    rows = [(i, ans[i["project"]]["verdict"]) for i in items if i["project"] in ans]
    judged = [(i, v) for i, v in rows if v in ("right", "wrong")]
    k = sum(1 for _, v in judged if v == "wrong")
    n = len(judged)
    out = {"answered": len(rows), "items": len(items), "unsure": sum(1 for _, v in rows if v == "unsure"),
           "judged": n, "wrong": k, "rate": k / n if n else None, "wilson": wilson(k, n)}
    strata = {}
    for i, v in judged:
        s = strata.setdefault(i["stratum"], {"size": i["stratum_size"], "n": 0, "wrong": 0})
        s["n"] += 1
        s["wrong"] += v == "wrong"
    total = sum(s["size"] for s in strata.values())
    if total:
        est = sum(s["size"] / total * s["wrong"] / s["n"] for s in strata.values())
        var = sum((s["size"] / total) ** 2 * (s["wrong"] / s["n"]) * (1 - s["wrong"] / s["n"]) / max(s["n"] - 1, 1)
                  for s in strata.values())
        out["weighted"] = est
        out["weighted_ci"] = (max(0.0, est - 1.96 * math.sqrt(var)), min(1.0, est + 1.96 * math.sqrt(var)))
        out["weighted_population"] = total
    by = {}
    for i, v in judged:
        b = by.setdefault(i["confidence"], [0, 0])
        b[0] += v == "wrong"
        b[1] += 1
    out["by_confidence"] = {c: {"wrong": w, "judged": m, "rate": w / m, "wilson": wilson(w, m)}
                            for c, (w, m) in sorted(by.items())}
    out["wrong_list"] = [{"project": i["project"], "value": i["value"], "note": ans[i["project"]]["note"]}
                         for i, v in rows if v == "wrong"]
    return out


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>License audit</title>
<style>
body{font:15px/1.45 system-ui,sans-serif;margin:0;background:#f6f6f4;color:#1d1d1b}
header{display:flex;gap:1rem;align-items:center;padding:.6rem 1.2rem;background:#fff;border-bottom:1px solid #ddd}
#bar{flex:1;height:10px;background:#e4e4e0;border-radius:5px;overflow:hidden}#fill{height:100%;background:#2f7d4f;width:0}
main{max-width:1100px;margin:1rem auto;padding:0 1.2rem}
h1{font-size:1.15rem;margin:.2rem 0}.meta{color:#555}.value{font:600 2.1rem/1.2 ui-monospace,monospace;margin:.6rem 0 .3rem;
word-break:break-word;background:#fff;border:2px solid #333;border-radius:8px;padding:.6rem .9rem}
.file{background:#fff;border:1px solid #ddd;border-radius:8px;margin:.7rem 0;padding:.5rem .8rem}
.file pre{background:#fafaf7;border:1px solid #eee;padding:.5rem;overflow:auto;max-height:18rem;font-size:12.5px;margin:.4rem 0 0}
.btns{display:flex;gap:.6rem;align-items:center;margin:.9rem 0;flex-wrap:wrap}
button{font-size:1rem;padding:.55rem 1.1rem;border-radius:7px;border:1px solid #888;background:#fff;cursor:pointer}
button.right{border-color:#2f7d4f}button.wrong{border-color:#b3261e}button.unsure{border-color:#8a6d00}
button.on.right{background:#2f7d4f;color:#fff}button.on.wrong{background:#b3261e;color:#fff}button.on.unsure{background:#8a6d00;color:#fff}
input#note{flex:1;min-width:16rem;font:1rem ui-monospace,monospace;padding:.5rem;border:1px solid #888;border-radius:7px}
.keys{color:#666;font-size:.85rem}a{color:#1a5fb4}
</style></head><body>
<header><strong>License audit</strong><span id="count"></span><div id="bar"><div id="fill"></div></div>
<a href="/results">results</a></header>
<main id="m"></main>
<script>
let items=[],ans={},cur=0;
const $=s=>document.querySelector(s);
function el(t,a={},...kids){const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='class')e.className=v;else e.setAttribute(k,v)}
 for(const k of kids){e.append(k instanceof Node?k:document.createTextNode(k??''))}return e}
function link(href,text){if(!href)return document.createTextNode(text+' (no link for this host)');const a=el('a',{href,target:'_blank',rel:'noopener noreferrer'},text);return a}
function progress(){const n=Object.keys(ans).filter(p=>items.some(i=>i.project===p)).length;
 $('#count').textContent=`${cur+1} / ${items.length}  ·  answered ${n}`;$('#fill').style.width=(100*n/items.length)+'%'}
function show(){const it=items[cur],m=$('#m');m.replaceChildren();const a=ans[it.project]||{};
 m.append(el('h1',{},it.project),
  el('div',{class:'meta'},'commit ',el('code',{},it.commit.slice(0,12)),'  ·  ',link(it.repo,'repository at this commit'),
    `  ·  confidence ${it.confidence}  ·  evidence ${it.evidence_kind}  ·  version choice ${it.version_choice}`),
  el('div',{class:'meta'},'Proposed SPDX value:'),el('div',{class:'value'},it.value),
  it.other.length?el('div',{class:'meta'},'Other root licenses (not in the value): '+it.other.join(', ')):'');
 const btns=el('div',{class:'btns'});
 for(const[v,k,lab]of[['right','1','Right'],['wrong','2','Wrong'],['unsure','3','Unsure']]){
  const b=el('button',{class:v+(a.verdict===v?' on':'')},`${lab} (${k})`);b.onclick=()=>answer(v);btns.append(b)}
 const note=el('input',{id:'note',placeholder:'note or the correct value (optional); Enter saves and goes next, Esc leaves the field'});note.value=a.note||'';
 note.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();const v=ans[it.project]?.verdict;
  if(!v&&note.value){alert('Choose Right, Wrong or Unsure first (buttons or 1/2/3 after Esc).');return}answer(v,true)}
  else if(e.key==='Escape'){note.blur()}e.stopPropagation()});
 btns.append(note,el('button',{},'Next (Enter)'));btns.lastChild.onclick=()=>next();m.append(btns,
  el('div',{class:'keys'},'Keys: 1 Right · 2 Wrong · 3 Unsure · Enter next · ← → move · n focus the note'));
 for(const f of it.files){m.append(el('div',{class:'file'},el('strong',{},f.path),` (${f.role}, ${f.use}: ${f.says})  `,
   link(f.raw,'raw file'),'  ',f.view?link(f.view,'view'):'',el('pre',{},f.excerpt)))}
 progress()}
async function answer(v,goNext){if(!v)return next();const it=items[cur],note=$('#note').value;
 const r=await fetch('/api/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project:it.project,verdict:v,note})});
 if(!r.ok){alert('not saved: '+await r.text());return}ans[it.project]={verdict:v,note};show();if(goNext)next()}
function next(){if(cur<items.length-1){cur++;show();window.scrollTo(0,0)}}
function prev(){if(cur>0){cur--;show();window.scrollTo(0,0)}}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;
 if(e.key==='1')answer('right');else if(e.key==='2')answer('wrong');else if(e.key==='3')answer('unsure');
 else if(e.key==='Enter'||e.key==='ArrowRight')next();else if(e.key==='ArrowLeft')prev();
 else if(e.key==='n'){e.preventDefault();$('#note').focus()}});
(async()=>{items=await (await fetch('/api/items')).json();ans=await (await fetch('/api/answers')).json();
 const first=items.findIndex(i=>!ans[i.project]);cur=first<0?0:first;show()})();
</script></body></html>"""


def results_page(r):
    def pct(x):
        return "-" if x is None or x != x else f"{100 * x:.1f}%"
    rows = "".join(f"<tr><td>{c}</td><td>{v['wrong']} / {v['judged']}</td><td>{pct(v['rate'])}</td>"
                   f"<td>{pct(v['wilson'][0])} to {pct(v['wilson'][1])}</td></tr>"
                   for c, v in r["by_confidence"].items())
    import html
    wl = "".join(f"<li><code>{html.escape(w['project'])}</code>: {html.escape(w['value'])} "
                 f"&rarr; {html.escape(w['note'] or '(no note)')}</li>" for w in r["wrong_list"])
    w = (f"<p>Weighted by stratum size (the {r['weighted_population']:,} strata members): <b>{pct(r['weighted'])}</b>, "
         f"95% interval {pct(r['weighted_ci'][0])} to {pct(r['weighted_ci'][1])} (normal approximation).</p>"
         if "weighted" in r else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>License audit results</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}}
td,th{{padding:.3rem .8rem;border-bottom:1px solid #ddd;text-align:left}}</style></head><body>
<p><a href="/">back to the audit</a></p><h1>Results</h1>
<p>Answered {r['answered']} of {r['items']} (unsure {r['unsure']}). Judged (right or wrong): {r['judged']}.</p>
<p>Error rate: <b>{pct(r['rate'])}</b> ({r['wrong']} wrong of {r['judged']}), 95% Wilson interval
{pct(r['wilson'][0])} to {pct(r['wilson'][1])}.</p>{w}
<table><tr><th>confidence</th><th>wrong</th><th>rate</th><th>95% interval</th></tr>{rows}</table>
<h2>Wrong values</h2><ul>{wl}</ul></body></html>"""


class H(BaseHTTPRequestHandler):
    server_version = "audit"

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; "
                         "style-src 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "bad host")
        if self.path == "/":
            return self._send(200, PAGE)
        if self.path == "/api/items":
            return self._send(200, json.dumps(load_items()), "application/json")
        if self.path == "/api/answers":
            return self._send(200, json.dumps({p: {"verdict": a["verdict"], "note": a["note"]}
                                               for p, a in load_answers().items()}), "application/json")
        if self.path == "/results":
            return self._send(200, results_page(results(load_items(), load_answers())))
        if self.path == "/api/results":
            return self._send(200, json.dumps(results(load_items(), load_answers())), "application/json")
        return self._send(404, "not found")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, "bad host")
        if self.path != "/api/answer" or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(400, "bad request")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 10_000:
            return self._send(413, "too large")
        try:
            body = json.loads(self.rfile.read(n))
            project, verdict = str(body["project"]), str(body["verdict"])
            note = " ".join(str(body.get("note", "")).split())[:500]
        except (ValueError, KeyError, TypeError):
            return self._send(400, "bad json")
        if verdict not in VERDICTS or project not in {i["project"] for i in load_items()}:
            return self._send(400, "bad answer")
        save_answer(project, verdict, note)
        return self._send(200, "{}", "application/json")

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=2731)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((HOST, a.port), H)
    print(f"audit page on http://{HOST}:{a.port}/ ({len(load_items())} items, answers in {ANSWERS})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
