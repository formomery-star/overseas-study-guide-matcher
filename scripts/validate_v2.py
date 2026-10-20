"""Validate evidence links and compute conservative readiness, independently of targets.

This validates recorded evidence integrity, not truth of source contents or student fit.
No network access. No v2 record is consumed by the legacy generator yet.
"""
import argparse
import datetime as dt
import json
import math
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def is_url(value):return isinstance(value,str) and urlparse(value).scheme in ('http','https') and bool(urlparse(value).netloc)
def valid_date(value):
    try:return dt.date.fromisoformat(value)
    except (ValueError,TypeError):return None

def job_source_identity_errors(rows,evidence):
    """One URL can publish several jobs only with reviewed collection locators.

    A locator is an internal section label, not an invented publisher job ID.
    Renaming a locator cannot duplicate the same employer/title within an article.
    """
    errors=[];groups={}
    def norm(s):return ''.join(unicodedata.normalize('NFKC',s).split()).casefold() if isinstance(s,str) else ''
    for row in rows:
        url=row.get('source_url')
        if not is_url(url):continue  # main validator reports malformed URLs
        url=urlparse(url)._replace(fragment='').geturl()
        groups.setdefault(url,[]).append(row)
    for url,group in groups.items():
        locators=set();identities=set()
        for row in group:
            rid=row.get('id');kind=row.get('source_kind','individual')
            if kind not in ('individual','collection'):
                errors.append(f'{rid}: invalid source_kind');continue
            if kind=='individual':
                if len(group)>1:errors.append(f'{rid}: duplicate source job URL (collection metadata required)')
                continue
            locator=norm(row.get('source_locator'))
            if not locator or locator in locators:errors.append(f'{rid}: missing/duplicate collection locator')
            locators.add(locator)
            identity=[]
            for field in ('employer','title'):
                fact=row.get('facts',{}).get(field,{})
                value=norm(fact.get('value'));identity.append(value)
                refs=fact.get('evidence_ids',[])
                refs=refs if isinstance(refs,list) else []
                linked=any(isinstance(x,str) and is_url(evidence.get(x,{}).get('url')) and
                           urlparse(evidence[x]['url'])._replace(fragment='').geturl()==url for x in refs)
                if not value or fact.get('status')!='verified' or not linked:
                    errors.append(f'{rid}: collection {field} needs verified article evidence')
            key=tuple(identity)
            if key in identities:errors.append(f'{rid}: duplicate collection employer/title')
            identities.add(key)
    return errors

def cost_coverage_gaps(costs):
    """Exact, reviewed component accounting; never infer coverage from prose.

    excluded_covered_by maps an excluded item to the component explicitly including
    the identical item. It neither moves money nor changes source/freshness gates.
    Missing/malformed coverage and overlapping inclusion remain unresolved.
    """
    keys=('tuition','living_cost','other_costs');gaps=[];included={};excluded={};maps={}
    for key in keys:
        cost=costs.get(key)
        if not isinstance(cost,dict):
            gaps.append(f'{key}:cost_coverage_missing');continue
        if cost.get('coverage_complete') is not True:
            gaps.append(f'{key}:cost_coverage_incomplete')
        for field,target in [('included',included),('excluded',excluded)]:
            items=cost.get(field)
            if (not isinstance(items,list) or any(not isinstance(x,str) or not x.strip() for x in items)
                    or len(items)!=len(set(items))):
                gaps.append(f'{key}:{field}_invalid');target[key]=set()
            else:target[key]=set(items)
        mapping=cost.get('excluded_covered_by',{})
        if not isinstance(mapping,dict):
            gaps.append(f'{key}:coverage_mapping_invalid');mapping={}
        maps[key]=mapping
    for key in keys:
        inc=included.get(key,set());exc=excluded.get(key,set());mapping=maps.get(key,{})
        if inc & exc:gaps.append(f'{key}:included_excluded_overlap')
        if set(mapping)-exc:gaps.append(f'{key}:coverage_mapping_not_excluded')
        for item in sorted(exc):
            target=mapping.get(item)
            if (not isinstance(target,str) or target not in keys or target==key
                    or item not in included.get(target,set())):
                gaps.append(f'{key}:uncovered:{item}')
    for i,key in enumerate(keys):
        for other in keys[i+1:]:
            for item in sorted(included.get(key,set()) & included.get(other,set())):
                gaps.append(f'{key}/{other}:duplicate_inclusion:{item}')
    return gaps

def payment_schedule_errors(cost,key,years):
    """A reviewed full-course other-cost schedule, expressed in base-year prices.

    Index zero includes pre-arrival payments. This is a study-year cash-flow
    allocation, not a promise about dates or a mechanism for filling missing fees.
    """
    if cost.get('period')!='payment_schedule':
        return ['payments_require_schedule_period'] if 'payments' in cost else []
    errors=[]
    if key!='other_costs':errors.append('schedule_only_supported_for_other_costs')
    if (type(years) not in (int,float) or not math.isfinite(years) or years<=0 or years!=int(years)
            or type(cost.get('schedule_years')) is not int or cost['schedule_years']!=years):
        return errors+['schedule_duration_mismatch']
    rows=cost.get('payments')
    if not isinstance(rows,list) or not rows:return errors+['nonempty_payments_required']
    ids=set();low=0.0;high=0.0;unbounded=False
    finite=lambda x:type(x) in (int,float) and math.isfinite(x)
    for row in rows:
        if not isinstance(row,dict):errors.append('invalid_payment');continue
        pid=row.get('id');year=row.get('year_index');lo=row.get('amount_min');hi=row.get('amount_max')
        if not isinstance(pid,str) or not pid.strip() or pid in ids:errors.append('payment_id_missing_or_duplicate')
        else:ids.add(pid)
        if type(year) is not int or not 0<=year<years:errors.append('payment_year_outside_course')
        if not isinstance(row.get('label'),str) or not row['label'].strip():errors.append('payment_label_required')
        if any(k in row for k in ('currency','base_year','fee_mode')):errors.append('payment_must_use_component_units')
        lower_only=hi is None and row.get('bound_type')=='lower_only'
        if not finite(lo) or lo<0 or (not lower_only and (not finite(hi) or hi<lo)):
            errors.append('invalid_payment_bounds');continue
        low+=lo
        if lower_only:unbounded=True
        else:high+=hi
    if errors:return errors
    if not finite(low) or not finite(high):return ['payment_sum_overflow']
    top_low=cost.get('amount_min');top_high=cost.get('amount_max')
    if not finite(top_low) or not math.isclose(top_low,low,rel_tol=1e-9,abs_tol=1e-6):errors.append('payment_lower_sum_mismatch')
    if unbounded:
        if top_high is not None or cost.get('bound_type')!='lower_only':errors.append('unbounded_payment_requires_unbounded_total')
    elif not finite(top_high) or not math.isclose(top_high,high,rel_tol=1e-9,abs_tol=1e-6):
        errors.append('payment_upper_sum_mismatch')
    return errors

def check_type(value,kind):
    return {'string':lambda:isinstance(value,str) and bool(value.strip()),
            'number':lambda:type(value) in (int,float) and value>0,
            'boolean':lambda:type(value) is bool,
            'array':lambda:isinstance(value,list) and len(value)>0,
            'object':lambda:isinstance(value,dict) and len(value)>0}[kind]()

def inspect_fact(fact,kind,evidence,contract,today,ttl,path):
    errors=[]; gaps=[]
    if not isinstance(fact,dict):return [f'{path}: fact must be an object'],[path]
    for key in ['value','status','evidence_ids','scope']:
        if key not in fact:errors.append(f'{path}: missing {key}')
    status=fact.get('status'); value=fact.get('value'); refs=fact.get('evidence_ids',[])
    if status not in contract['fact_states']:errors.append(f'{path}: invalid state')
    if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs):
        errors.append(f'{path}: invalid evidence references');refs=[]
    for ref in refs:
        if ref not in evidence:errors.append(f'{path}: broken evidence link {ref}')
    if status in ('verified','not_applicable'):
        if not refs or not fact.get('scope'):errors.append(f'{path}: reviewed fact needs evidence and scope')
        if status=='verified' and not check_type(value,kind):errors.append(f'{path}: wrong or missing {kind} value')
        if status=='not_applicable' and (value is not None or not fact.get('reason')):
            errors.append(f'{path}: not_applicable needs null value and reason')
    elif status in ('unknown','unavailable') and value is not None:
        errors.append(f'{path}: unknown/unavailable must not contain an asserted value')
    elif value is not None and not check_type(value,kind):errors.append(f'{path}: invalid extracted value type')
    fresh=True
    for ref in refs:
        e=evidence.get(ref,{})
        checked=valid_date(e.get('checked_on'))
        if not checked or not e.get('reviewed_by') or not 0<=(today-checked).days<=ttl:fresh=False
    if status not in ('verified','not_applicable') or not refs or not fresh or errors:gaps.append(path)
    return errors,gaps

def validate(root=ROOT,as_of=None):
    today=dt.date.fromisoformat(as_of) if as_of else dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    base=root/'database/v2';contract=read(base/'contract.json');tax=read(base/'taxonomy.json')
    programs=read(base/'programs.json');jobs=read(base/'jobs.json');evidence_rows=read(base/'evidence.json')
    school_ids={x['id'] for x in read(root/'database/universities.json')}
    errors=[]; evidence={}; family_ids=set();major_ids=set()
    for f in tax['families']:
        if f['id'] in family_ids:errors.append(f"duplicate family: {f['id']}")
        family_ids.add(f['id'])
    for m in tax['majors']:
        if m['id'] in major_ids:errors.append(f"duplicate major: {m['id']}")
        if m['family_id'] not in family_ids:errors.append(f"unknown family for {m['id']}")
        major_ids.add(m['id'])
    for e in evidence_rows:
        eid=e.get('id')
        if not eid or eid in evidence:errors.append(f'duplicate/missing evidence id: {eid}')
        evidence[eid]=e
        for k in contract['evidence_required']:
            if k not in e:errors.append(f'{eid}: missing evidence field {k}')
        if not is_url(e.get('url')):errors.append(f'{eid}: invalid URL')
        checked=valid_date(e.get('checked_on'))
        if not checked or checked>today:errors.append(f'{eid}: invalid/future check date')
        if e.get('source_type') not in contract['source_types']:errors.append(f'{eid}: invalid source type')
        if not e.get('scope') or not e.get('summary'):errors.append(f'{eid}: missing scope/summary')
    errors.extend(job_source_identity_errors(jobs,evidence))
    reports={'programs':[],'jobs':[]};seen=set();program_keys=set()
    for kind,records in [('program',programs),('job',jobs)]:
        for row in records:
            rid=row.get('id');local=[];gaps=[]
            if not rid or rid in seen:local.append(f'duplicate/missing record id: {rid}')
            seen.add(rid)
            for k in contract[f'{kind}_required']:
                if k not in row:local.append(f'{rid}: missing {k}')
            if row.get('review') not in contract['review_states']:local.append(f'{rid}: invalid review state')
            if row.get('review')!='reviewed':gaps.append('record_review')
            facts=row.get('facts',{})
            for key,field_type in contract[f'{kind}_fields'].items():
                es,gs=inspect_fact(facts.get(key),field_type,evidence,contract,today,contract[f'{kind}_ttl_days'],f'{rid}.{key}')
                local.extend(es);gaps.extend(gs)
            if kind=='program':
                mids=row.get('major_ids',[])
                if row.get('school_id') not in school_ids:local.append(f'{rid}: unknown school')
                pkey=tuple(row.get(k) for k in ('school_id','campus_key','degree_key','policy_year'))
                if pkey in program_keys:local.append(f'{rid}: duplicate program/campus/policy year')
                program_keys.add(pkey)
                if type(row.get('policy_year')) is not int:local.append(f'{rid}: policy_year must be an actual documented year')
                for key in ['high_school_entry','international_eligible']:
                    if facts.get(key,{}).get('value') is not True:gaps.append(key)
                if facts.get('degree_level',{}).get('value') not in ('bachelor','integrated_undergraduate'):
                    gaps.append('undergraduate_degree_required')
                for key in contract['program_fields']:
                    if facts.get(key,{}).get('status')=='not_applicable' and key not in ('licensure_path',):
                        gaps.append(f'{key}:not_applicable_cannot_clear_core_requirement')
                gaps.extend(cost_coverage_gaps({key:facts.get(key,{}).get('value')
                    if facts.get(key,{}).get('status')=='verified' else None
                    for key in ('tuition','living_cost','other_costs')}))
                for key in ['tuition','living_cost','other_costs']:
                    f=facts.get(key,{})
                    if f.get('status')=='verified':
                        v=f.get('value') or {}
                        local.extend(f'{rid}.{key}:{msg}' for msg in payment_schedule_errors(v,key,facts.get('duration_years',{}).get('value')))
                        required=('currency','period','amount_min','amount_max','included','excluded')
                        if any(k not in v for k in required):local.append(f'{rid}.{key}: incomplete cost breakdown')
                        else:
                            lo,hi=v['amount_min'],v['amount_max']
                            finite=lambda x:type(x) in (int,float) and math.isfinite(x)
                            lower_only=hi is None and v.get('bound_type')=='lower_only'
                            if not finite(lo) or lo<0 or (not lower_only and (not finite(hi) or hi<lo)):
                                local.append(f'{rid}.{key}: invalid cost bounds')
                            elif lower_only:gaps.append(f'{key}:upper_bound_unknown')
                for key in ['credential_requirements','subject_requirements','english_requirements','additional_requirements','tuition','living_cost','other_costs']:
                    for ref in facts.get(key,{}).get('evidence_ids',[]):
                        if evidence.get(ref,{}).get('source_type')!='university_official':gaps.append(f'{key}:official_source_required')
            else:
                links=row.get('major_links',[]);mids=[x.get('major_id') for x in links]
                if any(not x.get('basis') for x in links):local.append(f'{rid}: major link lacks rationale')
                url=row.get('source_url')
                if not is_url(url):local.append(f'{rid}: invalid job URL')
                observed=valid_date(row.get('observed_on'))
                if not observed or observed>today:local.append(f'{rid}: invalid observation date')
                elif (today-observed).days>contract['job_ttl_days']:gaps.append('stale_observation')
                if row.get('published_on') is not None and not valid_date(row.get('published_on')):local.append(f'{rid}: invalid publication date')
                published=valid_date(row.get('published_on'))
                if published and (published>today or (today-published).days>contract['job_ttl_days']):gaps.append('publication_outside_window')
                salary=facts.get('salary',{})
                if salary.get('status')=='verified':
                    v=salary.get('value') or {}
                    if any(k not in v for k in ['raw','currency','period','min','max','months','tax_basis']):local.append(f'{rid}: incomplete salary units')
                    elif not (type(v['min']) in (int,float) and type(v['max']) in (int,float) and 0<=v['min']<=v['max']):local.append(f'{rid}: invalid salary range')
                    if v.get('months') is not None and (type(v['months']) not in (int,float) or v['months']<=0):local.append(f'{rid}: invalid salary months')
            if not mids or any(m not in major_ids for m in mids):local.append(f'{rid}: missing or unknown major')
            errors.extend(local)
            reports[kind+'s'].append({'id':rid,'ready':not local and not gaps,'gaps':gaps,'errors':local})
    # Invalid evidence or taxonomy must never produce a ready catalog.
    if errors:
        for rows in reports.values():
            for r in rows:r['ready']=False
    ready_program_ids={r['id'] for r in reports['programs'] if r['ready']}
    ready_job_ids={r['id'] for r in reports['jobs'] if r['ready']}
    coverage={}
    for mid in sorted(major_ids):
        ps=[p for p in programs if p.get('id') in ready_program_ids and mid in p['major_ids']]
        js=[j for j in jobs if j.get('id') in ready_job_ids and any(x['major_id']==mid for x in j['major_links'])]
        coverage[mid]={'ready_programs':len(ps),'distinct_schools':len({p['school_id'] for p in ps}),
                       'ready_jobs':len(js),'distinct_employers':len({j['facts']['employer']['value'] for j in js})}
    return {'as_of':str(today),'valid':not errors,'errors':errors,'families':len(family_ids),'majors':len(major_ids),
            'program_records':len(programs),'ready_programs':len(ready_program_ids),'job_records':len(jobs),
            'ready_jobs':len(ready_job_ids),'evidence_records':len(evidence_rows),'records':reports,'coverage':coverage,
            'note':'Readiness verifies documented fields only, not admission likelihood or 2028 policy applicability. Legacy records are not counted here.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--as-of');parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=validate(as_of=args.as_of)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['records','coverage']},ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['valid'] else 1)

if __name__=='__main__':main()
