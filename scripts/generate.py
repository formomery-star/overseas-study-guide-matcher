"""Offline guide generator. All input HTML is escaped; unknown evidence remains unknown."""
from pathlib import Path
import argparse,json,re,html,math,datetime,hashlib,subprocess,os,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
E=lambda x:html.escape(str(x if x is not None else '待确认'),quote=True)
DB=json.loads((ROOT/'database/universities.json').read_text(encoding='utf8'))
EV=json.loads((ROOT/'database/evidence.json').read_text(encoding='utf8'))
PS=json.loads((ROOT/'database/policy_sources.json').read_text(encoding='utf8'))
BY={r['id']:r for r in DB}
RECOMMENDATION_POLICY=json.loads((ROOT/'database/recommendation_policy.json').read_text(encoding='utf8'))
RECOMMENDATION_ROLES=RECOMMENDATION_POLICY['roles']
DIM=['学术基础','竞赛成果','自主学习','实践协作','语言适应','兴趣职业']
MAJ={'CS':'计算机科学','DS':'数据科学','CE':'计算机工程','EE':'电气电子工程'}
SOURCE='https://qs-topuniversities.cn/university-rankings/world-university-rankings/2026'
def link(k):
 s=EV['sources'].get(k)
 if s:return f'<a href="{E(s["url"])}">{E(k)} {E(s["title"])}</a>'
 if k in PS:return f'<a href="{E(PS[k][1])}">{E(PS[k][0])}</a>'
 return ''
def refs(keys):return ' · '.join(link(k) for k in dict.fromkeys(keys.split()))
def card(title,value,body='',cls=''):
 return f'<div class="box {cls}"><div class="label">{E(title)}</div><div class="value">{E(value)}</div><p>{E(body)}</p></div>'
def radar(labels,values):
 cx,cy,r=210,175,115;n=len(labels)
 def xy(i,t=1):
  a=-math.pi/2+2*math.pi*i/n;return cx+r*t*math.cos(a),cy+r*t*math.sin(a)
 def pts(v):return ' '.join(f'{xy(i,t)[0]:.1f},{xy(i,t)[1]:.1f}' for i,t in enumerate(v))
 b=''.join(f'<polygon points="{pts([t]*n)}" fill="none" stroke="#d3dfd9"/>' for t in [.25,.5,.75,1])
 if all(v is not None for v in values):b+=f'<polygon points="{pts([v/100 for v in values])}" fill="#13857e" fill-opacity=".15" stroke="#13857e" stroke-width="3"/>'
 for i,(label,v) in enumerate(zip(labels,values)):
  x,y=xy(i);b+=f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="#d3dfd9"/>'
  if v is not None:
   x,y=xy(i,v/100);b+=f'<circle cx="{x}" cy="{y}" r="5" fill="#13857e"/>'
  x,y=xy(i,1.30);b+=f'<text x="{x}" y="{y}" text-anchor="middle" fill="#315c58" font-size="15">{E(label)}</text><text x="{x}" y="{y+20}" text-anchor="middle" fill="#b18132" font-size="16">{E(v if v is not None else "待核")}</text>'
 return '<svg viewBox="0 0 420 370" class="radar">'+b+'</svg>'
def wheel(status):
 b='';cx=260;cy=230
 for i,(lab,st) in enumerate(zip(DIM,status)):
  a=-math.pi/2+i*math.pi/3;x=cx+164*math.cos(a);y=cy+164*math.sin(a)
  b+=f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="#cddbd5" stroke-width="3"/><circle cx="{x}" cy="{y}" r="56" fill="{"#e0eee6" if st!="待补" else "#f3ead8"}"/><text x="{x}" y="{y-8}" text-anchor="middle" font-size="19" fill="#1b625c">{lab}</text><text x="{x}" y="{y+20}" text-anchor="middle" font-size="17" fill="#987428">{st}</text>'
 b+=f'<circle cx="{cx}" cy="{cy}" r="62" fill="#087e80"/><text x="{cx}" y="{cy-6}" text-anchor="middle" font-size="23" fill="white">六维画像</text><text x="{cx}" y="{cy+22}" text-anchor="middle" font-size="15" fill="white">证据状态图</text>'
 return '<svg viewBox="0 0 520 470" class="wheel">'+b+'</svg>'
class Report:
 def __init__(self,title,context,asof):self.title=title;self.context=context;self.asof=asof;self.pages=[];self.md=[]
 def page(self,title,sub,body,sources='',tag='图解指南'):
  self.pages.append(f'<section class="page"><header><span>{E(self.context)}</span><span class="tag">{E(tag)}</span></header><main><h1>{E(title)}</h1><div class="sub">{E(sub)}</div>{body}</main><footer><span>{sources}</span><span>{self.asof} | PAGENUM</span></footer></section>')
  txt=re.sub(r'<(style|svg)\b[^>]*>.*?</\1>','',body,flags=re.S)
  txt=re.sub(r'</(?:div|p|h\d|li)>','\n',txt)
  self.md+=['## '+title,sub,html.unescape(re.sub('<[^>]*>','',txt)),html.unescape(re.sub('<[^>]*>','',sources))]
 def save(self,dest,pdf=True):
  dest.mkdir(parents=True,exist_ok=True)
  pages=[p.replace('PAGENUM',f'{i+1:02d} / {len(self.pages)}') for i,p in enumerate(self.pages)]
  css=(ROOT/'templates/guide.css').read_text(encoding='utf8')
  (dest/'指南.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'+E(self.title)+'</title><style>'+css+'</style><body>'+''.join(pages)+'</body></html>',encoding='utf8')
  (dest/'指南.md').write_text('# '+self.title+'\n\n'+'\n\n'.join(self.md),encoding='utf8')
  if pdf:
   node=os.environ.get('GUIDE_NODE') or shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
   subprocess.run([node,str(ROOT/'scripts/render.cjs'),str(dest/'指南.html')],check=True)
  return dest
def school_pages(report,s):
 proxy=s['abc_proxy'] or [None]*5;labels=['研究','校友','资源','全球化','声誉']
 mapping=['引用/教师指标','雇主声誉＋就业结果均分','师生比指标','国际师生＋研究网络均分','学术声誉指标']
 left=f'<div class="box"><div class="label">ABC五维 · QS代理参照</div><div class="hero">{E(s["abc_proxy_total"])}</div>{radar(labels,proxy)}<div class="tiny">研究35% / 校友35% / 资源20% / 全球化5% / 声誉5%；本工具映射，非QS官方ABC排名。</div></div>'
 if s['deep']:
  right=''.join(f'<div class="row"><b>{E(lab)}</b><strong>{E(v)}</strong><p>{E(desc)} {refs(keys)}</p></div>' for lab,v,desc,keys in s['deep']['abcnotes'])
 else:
  right=''.join(f'<div class="row"><b>{lab}</b><strong>{E(v)}</strong><p>{E(desc)}；标准化分 / 100</p></div>' for lab,v,desc in zip(labels,proxy,mapping))
 right+=f'<div class="callout">QS 2026 世界排名 <b>{E(s["qs2026_rank"])}</b> · {E(s["location"])}<br>左为代理指标，右侧事实独立列示；完整ABC仍需论文原始量、师均经费等。</div>'
 report.page(s['name'],'1 / 3　ABC实力画像 · 可比指标与数据边界','<div class="split">'+left+'<div>'+right+'</div></div>',f'<a href="{SOURCE}">QS2026 官方榜单与指标</a> · <a href="{E(s["qs_profile"])}">学校档案</a>', '学校一览 · ABC')
 d=s['deep'];values=s['alumni_scores'];known=[v for v in values if v is not None]
 total=str(round(sum(known)/6)) if len(known)==6 else (f'{math.floor(sum(known)/6)}–{math.ceil((sum(known)+(6-len(known))*100)/6)}' if known else '待核')
 left='<div class="box"><div class="label">校友六维 · 公开证据观察分</div><div class="hero">'+total+'</div>'+radar(['中国规模','国内组织','商界','传播可见','公共领域','公益社群'],values)+f'<p>已评分 {len(known)} / 6；等权分档。缺项保留区间；分数不是人脉获得概率。</p></div>'
 right='';keys=[]
 for i,rule in enumerate(EV['rules']):
  t=d['overview'][i] if d else [rule['dimension'],'待采集','没有已核事实，不能根据声望或榜单名次推定。','']
  keys+=t[3].split()
  right+=f'<div class="row alumni"><b>{E(t[0])}</b><strong>{E(values[i] if values[i] is not None else "待核")}</strong><p><em>{E(t[1])}</em> · {E(t[2])} {refs(t[3])}</p></div>'
 report.page('校友资源，分数背后有什么',s['name']+' · 2 / 3　特色校友六维','<div class="split">'+left+'<div>'+right+'</div></div>',refs(' '.join(keys)), '特色校友圈')
 if d:
  sc=d['scale'];body='<div class="band"><div><h2>'+E(sc['title'])+'</h2><p>'+E(sc['note'])+'</p></div><div class="tiles">'+''.join(card(l,v) for l,v in zip(sc['labels'],sc['values']))+'</div></div>'
  body+='<div class="grid two">'+''.join(card(t[0],t[1],t[2]) for t in d['details'])+'</div>'
  if d.get('action'):body+='<div class="callout">'+E(d['action'])+'</div>'
  sources=refs(d['detailrefs'])
 else:
  body='<div class="band"><div><h2>实例尚未核验</h2><p>保留相同三页版式；当前属于资料草稿。</p></div><div class="hero">待补实</div></div><div class="grid two">'+''.join(card(t,'待核',x) for t,x in [('中国学生规模','需校方按国籍、学籍和年份分列，不能拿全部国际生替代。'),('商界与公共人物','需核真实学位、毕业年和任职事实；历史人物单独标记。'),('国内校友活动','需中国分会入口与近三年带日期的活动记录。'),('公益与行业社群','需成果数字、发生地、年份及参与入口。')])+'</div>'
  sources=f'<a href="{E(s["qs_profile"])}">QS学校信息入口；不构成六维校友事实来源</a>'
 report.page('人物、活动与可参与的机会',s['name']+' · 3 / 3　实例与使用方式',body,sources,'校友圈 · 具体实例')
def read_profile(path):
 text=path.read_text(encoding='utf-8-sig')
 if path.suffix.lower()=='.md':
  m=re.findall(r'```json\s*(.*?)\s*```',text,re.S)
  if len(m)!=1:raise ValueError('标准档案MD必须有且仅有一个JSON代码块；原始问卷请先整理为标准档案。')
  text=m[0]
 p=json.loads(text)
 for k in ['student_id','name','entry_year','academic','interests','family','evidence']:
  if k not in p:raise ValueError('缺少必需字段：'+k)
 if not re.fullmatch('[a-zA-Z0-9_-]{1,64}',p['student_id']):raise ValueError('student_id仅可含英文数字下划线横线')
 if type(p['entry_year']) is not int or not 2026<=p['entry_year']<=2040:raise ValueError('入学年份无效')
 for k in ['annual_budget_cny','total_budget_cny']:
  v=p['family'].get(k)
  if v is not None and (not isinstance(v,(int,float)) or v<=0):raise ValueError(k+'必须为正数人民币元或null')
 if len(p['interests'].get('major_codes',[]))>6:raise ValueError('最多三条路线，每条两个专业')
 if any(code not in MAJ for code in p['interests'].get('major_codes',[])):p['_outside_scope']=True
 for x in p['academic'].get('tests',[]):
  if x.get('kind')=='AP' and (not isinstance(x.get('score'),(int,float)) or not 1<=x['score']<=5):raise ValueError('AP分数必须为1–5')
 plan=p.get('planning',{})
 if not 0<=plan.get('annual_inflation',.03)<=.2:raise ValueError('年涨幅请用0–0.2之间的小数')
 if any(not isinstance(v,(int,float)) or v<=0 for v in plan.get('fx',{'USD':7.2,'SGD':5.5}).values()):raise ValueError('规划汇率必须为正数')
 return p
def budget(s,p,major=None):
 c=s['cost']
 if not c:return None
 fx={**{'USD':7.2,'SGD':5.5},**p.get('planning',{}).get('fx',{})}[c['currency']]
 inflation=p.get('planning',{}).get('annual_inflation',.03)
 tuition=c.get('tuition_by_major',{}).get(major,c['tuition'])
 totals=[tuition+v+c['other'] for v in c['living']]
 start=p['entry_year']-c['year'];factor=(1+inflation)**start
 annual=[round(v*fx*factor) for v in totals]
 mult=sum((1+inflation)**(start+i) for i in range(4))
 total=[round(v*fx*mult) for v in totals]
 f=p['family'];a=f.get('annual_budget_cny');t=f.get('total_budget_cny')
 if (a is not None and annual[0]>a) or (t is not None and total[0]>t):status='超出已填预算'
 elif a is None or t is None:status='预算待确认'
 elif annual[1]>a or total[1]>t:status='预算边缘，需精算'
 else:status='基础估算在预算内；另加未含项'
 return dict(native=totals,annual=annual,total=total,status=status,fx=fx,inflation=inflation,tuition=tuition)
def region_ok(s,p):
 allowed=p.get('regions',[]);parents=p['family'].get('regions',[])
 def match(a):return not a or s['group'] in a or s['location'] in a or ('美国' in a and s['location']=='United States') or ('新加坡' in a and s['location']=='Singapore')
 return match(allowed) and match(parents)
def gates(s,p,major):
 a=p['academic'];result=[]
 if not region_ok(s,p):result.append('地区偏好不符')
 b=budget(s,p,major)
 if b:result.append(b['status'])
 if not a.get('transcript_verified'):result.append('完整校内成绩待核')
 if not a.get('diploma'):result.append('毕业资格待确认')
 if not a.get('english'):result.append('英语成绩待补')
 tests=a.get('tests',[])
 if s['id']=='mit' and not any(t.get('kind') in ['SAT','ACT'] for t in tests):result.append('SAT/ACT待补')
 if s['id']=='nus':
  if not any(t.get('kind')=='AP' and t.get('subject')=='Calculus BC' and t['score']>=3 for t in tests):result.append('若适用AP组合：Calculus BC待补')
  result.append('NUS资格类别与完整组合须人工核验')
 en=a.get('english')
 if en and en.get('kind')=='IELTS' and s['id'] in ['umass','purdue']:
  if en.get('overall',0)<6.5 or (en.get('subscores') and min(en['subscores'])<6):result.append('IELTS未达当前参照门槛')
  if not en.get('subscores'):result.append('IELTS分项待核')
 result.append('2028招生细则待发布' if p['entry_year']==2028 else '入学年份政策须复核')
 return result
def choose(p):
 requested=p['interests'].get('major_codes',[])
 evidence=p['academic'].get('tests',[])
 if p.get('_outside_scope'):return [],'意向方向超出四校技术专业库，需补专业与院校后再匹配'
 if requested:codes=list(dict.fromkeys(requested));mode='学生自报意向；需要成绩与实际任务验证'
 elif any(t.get('kind')=='AP' and t.get('subject')=='Computer Science A' for t in evidence):codes=['CS','DS','CE','EE'];mode='基于已学计算机课程的探索候选；孩子兴趣尚待本人确认'
 else:return [],'兴趣与专业证据不足；先补问卷，再给路线，不套用计算机建议'
 selected=[]
 for code in codes:
  candidates=[s for s in DB if code in s['programs'] and s['id'] not in ['mit','nus'] and region_ok(s,p)]
  candidates=[s for s in candidates if budget(s,p,code)['status']!='超出已填预算']
  candidates=[s for s in candidates if 'IELTS未达当前参照门槛' not in gates(s,p,code)]
  # Within 4-school verified program coverage only. Budget is a gate, not an ability score.
  priority=['umass','purdue'] if code=='CS' else ['purdue']
  candidates.sort(key=lambda s:priority.index(s['id']) if s['id'] in priority else 99)
  # The legacy pool has no independently reviewed Asian fit decision. Never copy
  # the Asian benchmark into that role merely to fill the fourth card.
  selected.append({'major':code,'global':'mit','asia':'nus','asia_fit':None,'asia_fit_status':'pending_evidence_review','fit':candidates[0]['id'] if candidates else None,'gates':{sid:gates(BY[sid],p,code) for sid in ['mit','nus']+([candidates[0]['id']] if candidates else [])}})
 return selected,mode
def student_report(p,asof):
 report=Report(p['name']+' · 专属留学探索指南',f'{p["name"]} / {p["entry_year"]} 本科方向探索',asof)
 a=p['academic'];ev=p['evidence'];fa=p['family'];intr=p['interests']
 tests=a.get('tests',[])
 body='<div class="band"><div><h2>'+E(p['name'])+'</h2><p>'+E(p.get('grade','年级待确认'))+' · '+E(a.get('curriculum','课程体系待确认'))+'</p></div><div class="hero">'+str(p['entry_year'])+'</div></div>'
 body+='<div class="grid four">'+''.join(card(t['subject'],str(t['score'])+' / '+str(t.get('max',5)),t.get('status','自报，待核')) for t in tests[:4])+'</div>'
 body+='<div class="grid two">'+card('奖项与活动',str(len(ev.get('awards',[])))+'项奖项申报','；'.join(x['name'] for x in ev.get('awards',[])[:3]) or '本次未申报')+card('家庭专业背景',fa.get('father','待确认'),fa.get('mother','待确认'))+'</div><div class="callout">家庭可投入资源：'+E(fa.get('support','待确认'))+'；预算：'+E(str(fa['annual_budget_cny'])+'元/年' if fa.get('annual_budget_cny') else '待确认')+'。完整成绩与兴趣决定下一步，职业背景不直接折算成孩子能力。</div>'
  # Interest evidence must remain visible, rather than only altering an internal route code.
 body+='<div class="tiny">最喜欢的课：'+E(' / '.join(intr.get('favorite_subjects',[])) or '待本人填写')+'；喜欢的任务：'+E(' / '.join(intr.get('liked_tasks',[])) or '待本人填写')+'；校内成绩：'+E(a.get('school_summary') or '完整成绩单待补')+'</div>'
 report.page('履历一览，先看已知事实','01 / 个人资料 · 正式、申报和待核分开',body,tag='个人画像')
 states=['部分资料' if tests or a.get('transcript_verified') else '待补','待核申报' if ev.get('awards') else '未申报','有描述' if ev.get('self_learning') else '待补','待核申报' if ev.get('activities') else '未申报','有描述' if a.get('english') or ev.get('adaptation') else '待补','有意向' if intr.get('major_codes') or intr.get('favorite_subjects') else '待补']
 desc=['各科成绩、满分制、课程难度与趋势','主办方、证书、个人贡献和成绩分位','近期自学成果、改错与持续投入','真实作品、团队职责与可核成果','英语分项、实际沟通和独立生活经历','喜欢与讨厌的任务、职业价值和本人选择']
 body='<div class="split"><div>'+wheel(states)+'</div><div>'+''.join(f'<div class="row"><b>{DIM[i]}</b><strong>{states[i]}</strong><p>{desc[i]}</p></div>' for i in range(6))+'</div></div><div class="tiny">学术硬实力＝学术基础＋竞赛；学习底层能力＝自主学习＋实践协作；跨文化适配＝语言适应；性格职业匹配＝兴趣职业。短问卷仅形成证据画像，不代替心理测量。</div>'
 report.page('六维画像，找准需要补充的证据','02 / 多维状态图 · 不把缺资料记为低能力',body,tag='六维画像')
 chosen,mode=choose(p)
 for start in range(len(chosen)):
  subset=chosen[start:start+1];body=''
  for row in subset:
   code=row['major'];body+='<h2>'+E(MAJ[code])+'</h2><div class="grid two">'
   for spec in RECOMMENDATION_ROLES:
    role,key=spec['label'],spec['key']
    sid=row[key]
    if sid is None:
     detail='综合核对成绩、活动表现、兴趣及家庭预算后独立筛选；当前资料与筛选核验尚未完成。' if key=='asia_fit' else '当前库内候选受预算/地区限制；需扩充合适院校，不硬塞名校。'
     body+=card(role,'待完成适配核验' if key=='asia_fit' else '暂无可核匹配',detail,spec['style']);continue
    sc=BY[sid];issues=row['gates'][sid];body+=card(role,sc['name'],sc['programs'][code]+'；'+ '；'.join(issues[:3]),spec['style'])
   body+='</div>'
  report.page('精准匹配，从路线走到学校',mode,body+'<div class="callout">亚洲双推荐：专业标杆＋实际匹配。标杆看专业实力，实际匹配看孩子与家庭条件；缺证据不硬填。现有条件候选仅来自已补实的4校，未计算录取概率。</div>',refs('Q1 Q2 Q3'),tag='精准匹配 ★ 亚洲双推荐')
 if not chosen:report.page('先确认方向，再推荐院校',mode,card('需要学生补充','最喜欢的课＋最愿意做的任务','当前不输出院校推荐，避免将未知兴趣自动归成计算机。'),tag='精准匹配 · 待资料')
 ids=list(dict.fromkeys(row[spec['key']] for row in chosen for spec in RECOMMENDATION_ROLES if row[spec['key']]))
 if chosen:
  body='<div class="grid two">'+''.join(card(BY[sid]['name'],'申请证据清单','；'.join(BY[sid]['admissions']['summary'][:2])) for sid in ids)+'</div><div class="callout">个人缺口详见随附《匹配说明.md》。完整成绩、实际毕业证、语言分项与家庭预算未核实前，候选不能升级成确认适配。</div>'
  report.page('把录取要求，变成可准备的材料','招生规则：2026/27参照；申请年份重新核验',body,refs(' '.join(k for sid in ids for k in BY[sid]['admissions']['sources'])),tag='录取证据')
 for sid in ids:school_pages(report,BY[sid])
 # Every school/major with a different price appears once, including NUS DS.
 costrows=[];seen=set()
 for row in chosen:
  for sid in [row[spec['key']] for spec in RECOMMENDATION_ROLES]:
   if not sid:continue
   sc=BY[sid];b=budget(sc,p,row['major']);key=(sid,b['tuition'])
   if key in seen:continue
   seen.add(key);costrows.append((sc,b,row['major']))
 for start in range(0,len(costrows),4):
  body='<div class="grid two">'
  for sc,b,major in costrows[start:start+4]:
   c=sc['cost'];native=f'{b["native"][0]:,.0f}–{b["native"][1]:,.0f} {c["currency"]}'
   value=f'{b["annual"][0]/10000:.1f}–{b["annual"][1]/10000:.1f}万/年'
   detail=f'学费/校费 {b["tuition"]:,}；食宿生活 {c["living"][0]:,}–{c["living"][1]:,}；其他 {c["other"]:,}，均为{c["currency"]}。基准合计 {native}。四年约 {b["total"][0]/10000:.1f}–{b["total"][1]/10000:.1f}万元。{b["status"]}。'
   body+=card(sc['name']+' · '+MAJ[major],value,detail)
  fx={**{'USD':7.2,'SGD':5.5},**p.get('planning',{}).get('fx',{})};infl=p.get('planning',{}).get('annual_inflation',.03)
  body+=f'</div><div class="callout">规划汇率 USD={fx["USD"]}、SGD={fx["SGD"]}，非实时汇率；年涨幅{infl*100:g}%。2026/27为基数推到入学年，四年逐年复利。大多为9个月学年；逐校未含项目见匹配说明；不提前扣未获奖学金。</div>'
  report.page('费用预算，分开看再汇总','03 / 本币原始费用 → 入学年人民币情景 → 四年估算',body,refs(' '.join(k for sc,b,major in costrows[start:start+4] for k in sc['cost']['sources'])),tag='费用预算')
 if chosen:
  report.page('回国就业，先用作品验证方向','04 / 企业与岗位为探索例子；具体在招岗位另核','<div class="grid two">'+card('跨国企业 / 汽车工业','博世中国','嵌入式、工业软件与自动化；先看团队任务和实际岗位要求。')+card('国企 / 通信数字化','中国移动','软件开发、数据平台与网络技术；按省公司和研究院核验岗位。')+card('国内产业巨头','华为','系统软件、硬件与智能汽车；工程交付和专业深度都需要作品验证。')+card('大型科技公司','腾讯','后台开发、数据工程与算法应用；具体团队和招聘要求不同。')+'</div><div class="callout">企业分类可交叉；这里是方向映射，不能理解为校友内推或录用承诺。</div>','<a href="https://www.bosch.com.cn/careers/job-offers/internship/">博世职业入口</a> · <a href="https://career.huawei.com/reccampportal/globle/huawei-special-recruitment.html">华为招聘</a> · <a href="https://zhaopin.sh.chinamobile.com/zhaopin/portal.shtml?method=campusIndex">中国移动上海</a> · <a href="https://careers.tencent.com/">腾讯招聘</a>',tag='就业方向')
  wages={'CS':('Java开发',1.89),'DS':('算法工程师',2.19),'CE':('嵌入式软件开发',1.95),'EE':('电气工程师',1.24)}
  body='<div class="grid two">'
  for row in chosen:
   title,monthly=wages[row['major']];body+=card(title,f'{monthly*12:.1f}万元 / 年',f'月均招聘薪酬{monthly:.2f}万元 × 12；对应{MAJ[row["major"]]}探索方向。')
  body+='</div><div class="callout">长三角2026年第一季度招聘市场平均值，覆盖不同资历。不是应届起薪、到手收入或毕业年预测；奖金股票未另估。</div>'
  report.page('岗位薪酬，用同一市场口径比较','2026 Q1 · 长三角 · 年化招聘平均价',body,'<a href="https://www.mohrss.gov.cn/SYrlzyhshbzb/laodongguanxi_/fwyd/202607/t20260708_579828.html">人社部：2026年1季度市场招聘薪酬（2026-07-08）</a>',tag='薪酬参照')
  report.page('向行业前20%努力，先定义成果','成长时间是建议安排，薪资分位尚无可比样本','<div class="grid four">'+card('现在','2–4周试做','用代码/装置/数据项目验证任务偏好，留下测试与复盘。')+card('本科','约4年','算法、统计、系统或电路打底；积累课程项目、研究与实习。')+card('选择深造','按岗位需要','算法研究、芯片、机器人等可进一步评估硕博；学制和机会另核。')+card('职业阶段','持续交付复杂项目','从独立模块到复杂系统，积累可靠性、成本与协作成果。')+'</div><div class="band"><div><h2>作品 → 实习 → 复杂项目</h2><p>这是能力成长路线，不是保证晋升的时间表。</p></div><div class="hero">持续验证</div></div><div class="callout">缺少同岗同资历第80百分位薪资数据，不能给出进入前20%的确定年限、年薪或最终岗位承诺。</div>',tag='成长与深造')
 body='<div class="grid two">'+card('学生本人','最喜欢3门课＋喜欢/讨厌的任务','近期自学、合作、英语使用与适应场景，各写几个词。')+card('学校资料','各学期成绩＋准确考试科目','正式/预估分开；奖项与活动附可核证据。')+card('家长补充','年度/总预算＋可提供的实际支持','不要只填职业名称；写可以提供什么、每月多少时间。')+card('下一次更新','补资料 → 重新生成','同一学生用独立编号；系统保留每次版本，不混入其他学生资料。')+'</div>'
 report.page('补齐这些，下一版更接近真实选择','学校、学生、家长各补少量资料',body,tag='下一步')
 return report,{'student_id':p['student_id'],'mode':mode,'choices':chosen,'schools':ids,'profile_status':states,'limits':['技术专业4项/已补实4校','不提供录取概率','就业薪酬分位尚未入库'],'cost_rows':[{'id':s['id'],'major':m,**b} for s,b,m in costrows]}
def resolve_school(query):
 q=query.lower().strip();aliases={'麻省理工':'mit','mit':'mit','nus':'nus','新国大':'nus','新加坡国立':'nus','普渡':'purdue','purdue':'purdue','umass':'umass','马萨诸塞大学阿默斯特':'umass','香港大学':'university-hong-kong'}
 q=aliases.get(q,q)
 exact=[r for r in DB if q in [r['id'].lower(),r['name'].lower()]]
 hits=exact or [r for r in DB if q in r['id'].lower() or q in r['name'].lower()]
 if len(hits)!=1:raise ValueError('院校不存在或有多个匹配，请用数据库编号：'+', '.join(r['id'] for r in hits[:10]))
 return hits[0]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--student',type=Path);ap.add_argument('--school');ap.add_argument('--out',type=Path);ap.add_argument('--no-pdf',action='store_true');ap.add_argument('--as-of',default=datetime.date.today().isoformat());ap.add_argument('--list',action='store_true');args=ap.parse_args()
 if args.list:
  print('\n'.join(r['id']+' | '+r['name'] for r in DB));return
 if bool(args.student)==bool(args.school):ap.error('请只选择 --student 或 --school')
 now=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 if args.student:
  p=read_profile(args.student);report,manifest=student_report(p,args.as_of);folder=p['student_id']+'_'+now
 else:
  s=resolve_school(args.school);report=Report(s['name']+' · 三页学校一览','学校一览 / '+s['name'],args.as_of);school_pages(report,s);folder=s['id']+'_'+now;manifest={'school_id':s['id'],'school_pages':3,'alumni_verified_dimensions':sum(v is not None for v in s['alumni_scores']),'draft':s['deep'] is None}
 dest=args.out or ROOT/'results'/folder
 if dest.exists() and any(dest.iterdir()):raise ValueError('输出目录非空，请换新目录，避免覆盖既有报告')
 manifest['data_version']='2026-09-15';manifest['generated_at']=datetime.datetime.now().isoformat();manifest['database_sha256']=hashlib.sha256((ROOT/'database/universities.json').read_bytes()).hexdigest()
 manifest['recommendation_policy_version']=RECOMMENDATION_POLICY['version']
 manifest['recommendation_policy_sha256']=hashlib.sha256((ROOT/'database/recommendation_policy.json').read_bytes()).hexdigest()
 stale=(datetime.date.fromisoformat(args.as_of)-datetime.date(2026,9,15)).days>90
 manifest['policy_stale']=stale
 if args.student:manifest['school_cost_exclusions']={sid:BY[sid]['cost']['exclusions'] for sid in manifest['schools']}
 if stale:
  report.context+=' / 政策待复核'
  # Existing page strings were already generated; prepend visible page-level freshness tag.
  report.pages=[p.replace('<span class="tag">','<span class="tag">政策过期需复核 · ') for p in report.pages]
 report.save(dest,not args.no_pdf)
 shutil.copyfile(ROOT/'database/universities.json',dest/'数据库快照.json')
 (dest/'生成记录.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 (dest/'匹配说明.md').write_text('# 本次生成依据\n\n```json\n'+json.dumps(manifest,ensure_ascii=False,indent=2)+'\n```\n\n## 原始来源\n\n'+ '\n'.join(f'- [{v[0]}]({v[1]})' for v in PS.values())+'\n\n[QS世界榜单]('+SOURCE+')\n\n院校校友每项链接见PDF/HTML及database/院校对应MD。',encoding='utf8')
 if args.student:
  shutil.copyfile(args.student,dest/('输入档案'+args.student.suffix))
  (dest/'标准档案快照.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
 print(str(dest))
if __name__=='__main__':
 try:main()
 except (ValueError,KeyError,FileNotFoundError) as e:print('生成未完成：'+str(e),file=sys.stderr);sys.exit(2)
