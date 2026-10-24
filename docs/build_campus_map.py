"""Generate offline interactive and static campus-planning diagrams (Graphviz required)."""
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def branch(name, children, kind='proposed', note=''):
    return {'name': name, 'kind': kind, 'note': note, 'children': [branch(c, [], kind) if isinstance(c, str) else c for c in children]}


requested = [
    branch('Campus Transport', [
        'Bus code / series → route → destination campus',
        'Pickup points and alternative buses to the same campus',
        'Daily rotating bus QR: scan → sign in → choose numbered seat',
        'One seat per rider; prevent duplicate seat claims',
        'Seated / standing check-in; remaining seat count',
        'Check-out releases seat; reservations are separate',
        'Drivers, students or staff may contribute GPS with consent',
        'OpenStreetMap + Leaflet; last-update time and GPS accuracy',
        'Stale / offline status; no report means unknown, not cancelled',
        'QR screen or fresh print daily; copied QR is not proof of presence',
        'Browser GPS needs HTTPS, permission and connectivity',
        'Foreground updates only; locked-screen tracking is not guaranteed',
    ], 'requested', 'NiceGUI prototype exists. Odoo implementation has not started. Campus-level transport policies and standing limits need specification.'),
    branch('Campus Energy', [
        'Green generation: solar / wind / other sources',
        'Campus energy consumption and surplus',
        'Battery charge / discharge and stored balance',
        'Distribution / export quantity and destination',
        'Energy balance, losses and campus-wise readings',
        'Admin / explicitly assigned energy role only',
        'Live meter / inverter integration is a later design decision',
    ], 'requested', 'The existing prototype has a manual kWh ledger, not physical energy-control equipment.'),
    branch('Campus Time-sheet', [
        'Regular and medical leave tracking',
        'Holiday calendar and campus rules / engagements',
        'Request → approval / rejection → review notes',
        'Own-request privacy; authorized leave managers',
        'Prevent self-approval and duplicate overlapping requests',
        'Workweeks, quotas and local policies need specification',
        'Hourly time entry / payroll is not in the prototype',
    ], 'requested', 'Leave workflows exist in the prototype. A complete attendance/payroll system was not requested for the first version.'),
    branch('Campus Training', [
        'Role-based learning: student / staff / other assigned roles',
        'Industry-based learning and industry assignments',
        'Course catalogue and eligibility',
        'Enrollment and progress / completion',
        'Assessment, certificates and LMS integration: later scope',
    ], 'requested', 'Role/industry enrollment and self-reported completion exist in the prototype.'),
    branch('Campus Compute', [
        'Module name confirmed; requirements pending',
        'Resource types / users / quotas: to be defined',
        'Scheduling / allocation / costing: to be defined',
    ], 'pending', 'Only a clearly marked placeholder exists. Do not infer an implemented compute service.'),
    branch('Campus Recruitment', [
        'Module name mentioned; requirements pending',
        'Clarify staff hiring versus student placement workflows',
    ], 'pending', 'Not implemented. Hiring and placements may need separate apps.'),
    branch('Campus Innovations', [
        'Idea submission and innovation challenges',
        'Evaluation and prototype development',
        'Funding / incubation / startup support',
        'Patents / intellectual property / technology transfer',
    ], 'requested', 'Module requested. This lifecycle is a proposed starting structure; no innovation workflow has been implemented.'),
]

proposed = [
    branch('Academics & Students', ['Admissions', 'Student records and documents', 'Courses and LMS', 'Timetable and academic calendar', 'Attendance', 'Exams and results']),
    branch('Research & Grants', ['Research projects', 'Grant applications and budgets', 'Ethics approvals', 'Publications', 'Research collaboration']),
    branch('Industry & Careers', ['Industry partnerships', 'Consultancy', 'Internships', 'Student placements']),
    branch('People / HR', ['Staff records', 'Joining / transfers / exit', 'Role and department assignments', 'Staff recruitment linkage']),
    branch('Resources & Purchasing', ['Library', 'Labs and equipment booking', 'Assets and inventory', 'Procurement', 'Room and facility booking']),
    branch('Campus Services', ['Hostel', 'Dining / canteen', 'Maintenance', 'Helpdesk and service requests', 'Visitors']),
    branch('Student Life', ['Clubs and societies', 'Student council', 'Sports', 'Events and registration', 'Volunteering']),
    branch('Wellbeing & Safety', ['Health services', 'Counselling', 'Accessibility support', 'Emergency / incident reporting', 'Grievances']),
    branch('IT Services', ['IT support', 'Network access', 'Software licences', 'Compute-service integration']),
    branch('Wider Sustainability', ['Water', 'Waste', 'Environmental and carbon reporting', 'Energy-module linkage']),
    branch('Finance', ['Fees and payments', 'Scholarships', 'Budgets and expenses', 'Accounts']),
    branch('Community', ['Parent / guardian portal', 'Alumni', 'Donations', 'Community outreach']),
    branch('Governance & Quality', ['Committees', 'Policies and documents', 'Accreditation', 'Quality assurance']),
]

foundation = [
    branch('Organization & Configuration', ['College group → campus → college → department', 'Academic year / semester', 'Enable only selected apps per campus', 'Campus-specific branding / language / forms / numbering', 'Campus-specific rules and approval policies'], 'foundation'),
    branch('Identity & Permissions', ['Single login / optional SSO', 'One person profile; multiple roles', 'Role + campus scoped access', 'Group-admin cross-campus visibility rules', 'Joining → transfer → graduation / resignation → alumni'], 'foundation'),
    branch('Shared Experience', ['App launcher and consistent navigation', 'Common forms / tables / filters / search', 'Mobile and desktop layouts', 'Accessibility and localization', 'Shared-resource booking across campuses'], 'foundation'),
    branch('Shared Workflows', ['Approvals and review history', 'Documents', 'Notifications and announcements', 'Events and registrations', 'Campus and group-level reports'], 'foundation'),
    branch('Integrations & Operations', ['ERP / SSO / payments / biometric devices', 'GPS / energy meter interfaces', 'Excel import / migration / duplicate resolution', 'Audit history / privacy / retention', 'Backup / restore / monitoring', 'Poor-connectivity and offline requirements'], 'foundation'),
]

constraints = [
    'Current code: Python + NiceGUI + SQLite; not Odoo',
    'Odoo option: Python backend + XML / JavaScript-Owl UI + PostgreSQL',
    'Odoo Community first; verify each app and dependency licence',
    'Open-source maps: no mandatory paid key; hosting and tile-policy limits remain',
    'Institutional service-catalogue research has NOT been completed',
    'MIT / IIT / Oxford are reference institutions, not verified source lists',
    'Analysis only: no Odoo migration or new platform launcher has started',
    'Agree scope / Odoo version / deployment before implementation',
]

data = branch('Campus App Platform', [
    branch('Requested campus apps', requested, 'requested', 'User-named apps. Prototype status is recorded per app; inclusion does not mean an Odoo app already exists.'),
    branch('Additional app catalogue', proposed, 'proposed', 'Suggestions for completeness. Not approved implementation scope, and not a verified university service inventory.'),
    branch('Common platform foundation', foundation, 'foundation', 'Shared services used by every enabled app, with campus-specific policies.'),
    branch('Status & feasibility boundaries', constraints, 'pending', 'Planning constraints and implementation limits from this conversation.'),
], 'root', 'Discussion handoff: Campus App → apps → modules/features. Institutional research pending. Planning does not authorize implementation.')

counter = 0

def assign(node, depth=0):
    global counter
    node['id'] = f'n{counter}'
    counter += 1
    node['depth'] = depth
    for child in node['children']:
        assign(child, depth + 1)

assign(data)
(ROOT / 'campus-platform-map.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))

colors = {'root': '#16352f', 'requested': '#13786c', 'proposed': '#47638e', 'foundation': '#7950a0', 'pending': '#a66a16'}


def dot_quote(value):
    return json.dumps(value, ensure_ascii=False)


# Static overview: every app, its scope and the common foundation in a connected diagram.
lines = ['digraph Campus {', 'graph [rankdir=LR,bgcolor="#f7f9fc",pad="0.6",nodesep="0.23",ranksep="0.9",splines=polyline,label="CAMPUS APP PLATFORM — discussion mind map\\nRequested apps • Proposed catalogue • Shared foundation | Institutional research pending",labelloc=t,fontname="DejaVu Sans",fontsize=23,fontcolor="#16352f"];', 'node [shape=box,style="rounded,filled",fillcolor=white,color="#d6dee7",fontname="DejaVu Sans",fontsize=12,margin="0.18,0.13"];', 'edge [color="#b1bdca",arrowsize=0.5];']
lines.append(f'{data["id"]} [label="CAMPUS APP\\nPLATFORM",fillcolor="#16352f",fontcolor=white,fontsize=22];')
for group in data['children']:
    color = colors[group['kind']]
    lines.append(f'{group["id"]} [label={dot_quote(group["name"])},fillcolor="{color}",fontcolor=white,fontsize=17];')
    lines.append(f'{data["id"]} -> {group["id"]};')
    for item in group['children']:
        label = item['name'] + ('\n' + '\n'.join('• ' + c['name'] for c in item['children']) if item['children'] else '')
        label = label.replace('\n', '\\l') + '\\l'
        # Keep Graphviz line-break escapes literal in its label syntax.
        label_literal = '"' + label.replace('"', '\\"') + '"'
        lines.append(f'{item["id"]} [label={label_literal},color="{colors[item["kind"]]}",fontcolor="#263345"];')
        lines.append(f'{group["id"]} -> {item["id"]};')
lines.append('}')
(ROOT / 'campus-platform-map.dot').write_text('\n'.join(lines))
for extension in ('svg', 'pdf'):
    subprocess.run(['dot', f'-T{extension}', str(ROOT / 'campus-platform-map.dot'), '-o', str(ROOT / f'campus-platform-map.{extension}')], check=True)

# Separate overview image stays legible at screen size; full features are in SVG/PDF/HTML.
compact = ['digraph Overview {', 'graph [rankdir=LR,bgcolor="#f7f9fc",pad="0.5",nodesep="0.18",ranksep="0.7",label="CAMPUS APP — overview | Detailed interactive map in companion HTML",labelloc=t,fontname="DejaVu Sans",fontsize=20];', 'node [shape=box,style="rounded,filled",fontname="DejaVu Sans",fontsize=12,margin="0.16,0.10",fillcolor=white,color="#ccd6df"];', 'edge [color="#b2beca"];', 'root [label="CAMPUS APP",fillcolor="#16352f",fontcolor=white,fontsize=20];']
for group in data['children'][:3]:
    compact.append(f'{group["id"]} [label={dot_quote(group["name"])},fillcolor="{colors[group["kind"]]}",fontcolor=white];')
    compact.append(f'root -> {group["id"]};')
    for item in group['children']:
        compact.append(f'{item["id"]} [label={dot_quote(item["name"])},color="{colors[item["kind"]]}"];')
        compact.append(f'{group["id"]} -> {item["id"]};')
compact.append('}')
(ROOT / 'campus-platform-overview.dot').write_text('\n'.join(compact))
subprocess.run(['dot', '-Tpng', '-Gdpi=110', str(ROOT / 'campus-platform-overview.dot'), '-o', str(ROOT / 'campus-platform-overview.png')], check=True)

TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Campus App — Interactive Mind Map</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#223244;font:14px system-ui,Arial,sans-serif}header{padding:20px 24px 12px;background:#fff;border-bottom:1px solid #dce4ee}h1{margin:0 0 5px;font-size:25px;letter-spacing:-.6px}header p{margin:0;color:#637185;font-size:13px}.toolbar{display:flex;gap:8px;flex-wrap:wrap;padding:12px 24px;background:white;border-bottom:1px solid #dce4ee}button,input{font:inherit;border:1px solid #ccd7e3;border-radius:8px;padding:8px 11px;background:white;color:#263c51}button{cursor:pointer}button:hover{background:#edf5f3}button:focus-visible,input:focus-visible{outline:3px solid #26a99a}input{min-width:180px;flex:1;max-width:360px}.legend{display:flex;gap:15px;padding:9px 24px;flex-wrap:wrap;font-size:12px;background:#fff}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}main{display:grid;grid-template-columns:minmax(0,1fr) 290px;height:calc(100dvh - 196px);min-height:460px}#canvas{overflow:hidden;position:relative;touch-action:none;background-image:radial-gradient(#dce4ee .8px,transparent .8px);background-size:19px 19px}svg{display:block;width:100%;height:100%;user-select:none}aside{background:white;border-left:1px solid #dce4ee;padding:20px;overflow:auto}aside h2{font-size:19px;margin:0 0 10px}aside p{line-height:1.65;color:#5a6878}#path{font-size:12px;color:#728195;line-height:1.6}#details{white-space:pre-wrap}#children{line-height:1.7;padding-left:19px}#hint{position:absolute;bottom:12px;left:12px;padding:7px 10px;border-radius:8px;background:#ffffffeb;font-size:11px;color:#66758a;pointer-events:none}#search-results{padding:0 24px;background:#fff;max-height:120px;overflow:auto;display:none}#search-results button{margin:4px;text-align:left;font-size:12px}.node{cursor:pointer}.node rect{filter:drop-shadow(0 2px 2px #1b294510)}.node:hover rect{stroke-width:3}.node.selected rect{stroke:#f2ad3c;stroke-width:3}#status{font-size:11px;color:#6a7889;align-self:center}a{color:#13786c}.note{color:#8b641d!important;font-size:12px}#fullscreen{margin-left:auto}@media(max-width:760px){header{padding:14px}h1{font-size:20px}.toolbar{padding:9px 14px;gap:5px}.toolbar button{font-size:12px;padding:7px}.legend{padding:8px 14px;gap:8px}main{grid-template-columns:1fr;height:68dvh;min-height:420px}aside{border-left:0;border-top:1px solid #dce4ee;max-height:260px}#canvas{height:68dvh;min-height:420px}main{height:auto}.toolbar input{max-width:none;width:100%}#hint{max-width:90%}}
</style></head><body>
<header><h1>Campus App <span style="color:#13786c">/ Mind map</span></h1><p>Connected apps → modules → features. Click a node to expand or collapse; select a topic to see its scope.</p></header>
<div class="toolbar"><input id="search" aria-label="Search apps and features" placeholder="Search apps, features, rules…"><button id="overview">Overview</button><button id="expand">Expand all</button><button id="fit">Fit map</button><button id="plus" aria-label="Zoom in">＋</button><button id="minus" aria-label="Zoom out">−</button><button id="fullscreen">Full screen</button><span id="status"></span></div>
<div id="search-results" role="region" aria-label="Search results"></div>
<div class="legend"><span><i class="dot" style="background:#13786c"></i>User-requested apps</span><span><i class="dot" style="background:#47638e"></i>Suggested additional scope</span><span><i class="dot" style="background:#7950a0"></i>Shared foundation</span><span><i class="dot" style="background:#a66a16"></i>Needs definition / constraints</span></div>
<main><section id="canvas" aria-label="Interactive campus mind map"><svg id="map" role="img" aria-label="Connected campus app hierarchy"><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#aebdcb"/></marker></defs><g id="viewport"></g></svg><div id="hint">Drag to pan · Scroll / + − to zoom · Pinch on touch · Click boxes to explore</div></section><aside><div id="path"></div><h2 id="title">Campus App Platform</h2><p id="details"></p><ul id="children"></ul><p class="note">Planning reference from our discussion. University service catalogues have not been researched or verified. This is not a claim of MIT, IIT or Oxford coverage.</p><p class="note">The current prototype is NiceGUI/Python/SQLite. No Odoo migration is included in this map.</p></aside></main>
<script>
const DATA=__DATA__;
const colors={root:'#16352f',requested:'#13786c',proposed:'#47638e',foundation:'#7950a0',pending:'#a66a16'};
const ns='http://www.w3.org/2000/svg', svg=document.getElementById('map'), viewport=document.getElementById('viewport'), canvas=document.getElementById('canvas');
const all=[], byId=new Map(); function index(n,p){n.parent=p;n.open=n.depth===0||n.id===DATA.children[0].id;all.push(n);byId.set(n.id,n);n.children.forEach(c=>index(c,n))}index(DATA,null);
let x=30,y=30,scale=1,selected=DATA,visible=[],bounds={width:1200,height:700};
function el(tag,attrs={}){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);return e}
function wrap(text,len=32){const words=text.split(' '),out=[];let line='';for(const word of words){if((line+' '+word).trim().length>len&&line){out.push(line);line=word}else line+=(line?' ':'')+word}if(line)out.push(line);return out}
function transform(){viewport.setAttribute('transform',`translate(${x},${y}) scale(${scale})`)}
function details(n){selected=n;const path=[];for(let p=n;p;p=p.parent)path.unshift(p.name);document.getElementById('path').textContent=path.slice(0,-1).join(' → ');document.getElementById('title').textContent=n.name;document.getElementById('details').textContent=n.note||(n.children.length?'Expand this branch to explore its modules and features.':'Feature from the discussion; detailed workflow and feasibility may still need agreement.');const list=document.getElementById('children');list.replaceChildren();n.children.forEach(c=>{const li=document.createElement('li');const b=document.createElement('button');b.textContent=c.name;b.style.cssText='border:0;padding:3px 0;text-align:left;background:none;color:'+colors[c.kind];b.onclick=()=>focus(c);li.append(b);list.append(li)})}
function draw(){visible=[];let next=0;function layout(n){n.lines=wrap(n.name,n.depth===0?23:32);n.h=Math.max(56,n.lines.length*17+27);visible.push(n);const children=n.open?n.children:[];if(children.length){const first=next;children.forEach(layout);n.y=(first+next-1)*44}else{n.y=next*88;next++}n.x=n.depth*320}layout(DATA);
// Reflow based on actual row heights so long feature names never overlap.
let bottom=0;function position(n){const children=n.open?n.children:[];if(children.length){children.forEach(position);n.y=(children[0].y+children[children.length-1].y)/2}else{n.y=bottom+n.h/2;bottom+=n.h+19}}position(DATA);
viewport.replaceChildren();const edges=el('g',{'fill':'none','stroke':'#b5c3d2','stroke-width':'1.5'});visible.forEach(n=>{if(!n.parent)return;const p=n.parent;edges.append(el('path',{d:`M${p.x+276},${p.y} C${p.x+298},${p.y} ${n.x-24},${n.y} ${n.x},${n.y}`,'marker-end':'url(#arrow)'}))});viewport.append(edges);
visible.forEach(n=>{const g=el('g',{'class':'node'+(n===selected?' selected':''),transform:`translate(${n.x},${n.y-n.h/2})`,tabindex:'0',role:'button','aria-label':n.name+(n.children.length?(n.open?' collapse':' expand'):''),'data-id':n.id});const dark=n.depth<2;g.append(el('rect',{width:276,height:n.h,rx:11,fill:dark?colors[n.kind]:'#fff',stroke:colors[n.kind],'stroke-width':dark?0:1.3}));const text=el('text',{x:15,y:(n.h-n.lines.length*17)/2+13,fill:dark?'#fff':'#25364a','font-size':n.depth===0?17:13,'font-weight':n.depth<3?600:400});n.lines.forEach((line,i)=>{const t=el('tspan',{x:15,dy:i?17:0});t.textContent=line;text.append(t)});g.append(text);if(n.children.length){const badge=el('text',{x:258,y:18,'text-anchor':'middle','font-size':13,fill:dark?'#e4f1ed':colors[n.kind]});badge.textContent=n.open?'−':'+';g.append(badge)}g.onclick=()=>{details(n);if(n.children.length)n.open=!n.open;draw()};g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();g.onclick()}};viewport.append(g)});bounds={width:Math.max(...visible.map(n=>n.x))+276,height:Math.max(bottom,...visible.map(n=>n.y+n.h/2))};document.getElementById('status').textContent=visible.length+' / '+all.length+' nodes';transform()}
function fit(){const w=canvas.clientWidth,h=canvas.clientHeight;scale=Math.max(.055,Math.min(1.3,(w-60)/bounds.width,(h-50)/bounds.height));x=(w-bounds.width*scale)/2;y=(h-bounds.height*scale)/2;transform()}
function overview(){all.forEach(n=>n.open=n.depth===0||n.id===DATA.children[0].id);details(DATA);draw();fit()}
function focus(n){for(let p=n.parent;p;p=p.parent)p.open=true;if(n.children.length)n.open=true;details(n);draw();scale=.95;x=canvas.clientWidth/2-(n.x+138)*scale;y=canvas.clientHeight/2-n.y*scale;transform()}
function zoom(factor,cx=canvas.clientWidth/2,cy=canvas.clientHeight/2){const target=Math.max(.05,Math.min(2.5,scale*factor)),r=target/scale;x=cx-(cx-x)*r;y=cy-(cy-y)*r;scale=target;transform()}
document.getElementById('overview').onclick=overview;document.getElementById('expand').onclick=()=>{all.forEach(n=>n.open=true);draw();fit()};document.getElementById('fit').onclick=fit;document.getElementById('plus').onclick=()=>zoom(1.3);document.getElementById('minus').onclick=()=>zoom(1/1.3);document.getElementById('fullscreen').onclick=async()=>{try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen()}catch{document.getElementById('status').textContent='Full screen unavailable in this viewer'}};
canvas.addEventListener('wheel',e=>{e.preventDefault();const r=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.13:1/1.13,e.clientX-r.left,e.clientY-r.top)},{passive:false});
const pointers=new Map();let dragged=false,previousDistance=0;canvas.addEventListener('pointerdown',e=>{pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});dragged=false;if(!e.target.closest('.node'))canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;const old=pointers.get(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});if(pointers.size===2){const [a,b]=[...pointers.values()],distance=Math.hypot(a.x-b.x,a.y-b.y);if(previousDistance){const r=canvas.getBoundingClientRect();zoom(distance/previousDistance,(a.x+b.x)/2-r.left,(a.y+b.y)/2-r.top)}previousDistance=distance}else if(!e.target.closest('.node')){x+=e.clientX-old.x;y+=e.clientY-old.y;transform()} });for(const event of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(event,e=>{pointers.delete(e.pointerId);previousDistance=0});
document.getElementById('search').addEventListener('input',e=>{const query=e.target.value.trim().toLowerCase(),result=document.getElementById('search-results');result.replaceChildren();result.style.display=query?'block':'none';if(!query)return;const matches=all.filter(n=>n.name.toLowerCase().includes(query)).slice(0,25);if(!matches.length)result.textContent='No matching topic';matches.forEach(n=>{const b=document.createElement('button');b.textContent=(n.parent?n.parent.name+' → ':'')+n.name;b.onclick=()=>focus(n);result.append(b)})});
window.addEventListener('resize',fit);details(DATA);draw();requestAnimationFrame(fit);
</script></body></html>'''
(ROOT / 'campus-platform-map.html').write_text(TEMPLATE.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/')))
print(f'Generated {counter} connected nodes: HTML, JSON, SVG, PDF and overview PNG.')
