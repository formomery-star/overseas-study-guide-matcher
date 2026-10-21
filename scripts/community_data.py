"""Offline contribution staging. Never writes the live catalog or fetches submitted URLs."""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = {'official_name', 'duration_years', 'teaching_languages', 'tuition',
          'living_cost', 'other_costs', 'admission_detail_reference',
          'standardised_tests', 'career_outcomes', 'career_detail_reference',
          'alumni_network', 'alumni_caveat'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(proposal):
    require(isinstance(proposal, dict), '提交必须是JSON对象')
    require(set(proposal) == {'schema_version', 'contribution_id', 'license', 'changes'}, '提交字段不符合v1规范')
    require(type(proposal['schema_version']) is int and proposal['schema_version'] == 1, '版本必须为1')
    require(isinstance(proposal['contribution_id'], str) and 0 < len(proposal['contribution_id']) <= 100, '贡献编号不能为空')
    require(proposal['license'] == 'CC0-1.0', '仅接受贡献者有权以CC0提供的事实整理，不接收网页全文')
    changes = proposal['changes']
    require(isinstance(changes, list) and 0 < len(changes) <= 100, '每批1—100项')
    seen = set()
    for c in changes:
        require(isinstance(c, dict) and set(c) == {'program_id', 'field', 'expected_sha256', 'value', 'scope', 'evidence'}, '变更字段不符合规范')
        require(isinstance(c['program_id'], str) and c['program_id'].strip(), '项目ID不能为空')
        require(c['field'] in FIELDS, '不支持该字段；可执行招生规则必须单独代码评审')
        key = (c['program_id'], c['field'])
        require(key not in seen, '同批重复项目字段')
        seen.add(key)
        require(isinstance(c['expected_sha256'], str) and len(c['expected_sha256']) == 64 and all(x in '0123456789abcdef' for x in c['expected_sha256']), '必须提供旧字段SHA256；空字段也需hash')
        require(c['value'] is not None and c['value'] != '' and c['value'] != [], '不能提交空值')
        require(isinstance(c['scope'], str) and c['scope'].strip(), '适用范围必填')
        if c['field'] == 'duration_years':
            require(type(c['value']) in (int, float) and 0 < c['value'] <= 10, '学制必须为0—10之间数字')
        if c['field'] in {'tuition', 'living_cost', 'other_costs'}:
            v = c['value']
            require(isinstance(v, dict), '费用必须为结构化对象')
            require(type(v.get('amount')) in (int, float) and v['amount'] >= 0, '费用金额不得为负或文本')
            for k in ('currency', 'period', 'student_status'):
                require(isinstance(v.get(k), str) and v[k].strip(), '费用缺少' + k)
        e = c['evidence']
        require(isinstance(e, dict) and set(e) == {'id','url','publisher','source_type','checked_on','data_period','scope','summary'}, '来源字段缺失或混入审核标记')
        require(all(isinstance(v, str) and v.strip() for v in e.values()), '来源每项必须非空文本')
        u = urlsplit(e['url'])
        require(u.scheme == 'https' and u.hostname and not u.username and not u.password, '来源须为HTTPS且不含凭据')
        require(e['source_type'] == 'university_official', '本批仅支持大学官方来源；域名真实性仍由维护者核验')
        age = (dt.date.today() - dt.date.fromisoformat(e['checked_on'])).days
        require(0 <= age <= 90, '核验日期须在过去90天内')
    json.dumps(proposal, allow_nan=False)
    return {'status': 'awaiting_review', 'sha256': digest(proposal), 'changes': len(changes)}


def review(proposal, reviewer, note):
    validate(proposal)
    require(reviewer.strip() and note.strip(), '审核人和逐项来源/范围核验说明不能为空')
    return {'proposal_sha256': digest(proposal), 'reviewer': reviewer, 'note': note,
            'decision': 'approved', 'reviewed_at': dt.datetime.now(dt.timezone.utc).isoformat()}


def stage(proposal, approval, base, out):
    validate(proposal)
    require(approval.get('decision') == 'approved' and approval.get('proposal_sha256') == digest(proposal), '未批准或批准后内容被修改')
    require(approval.get('reviewer') and approval.get('note'), '缺少审核记录')
    base = Path(base)
    paths = {k: base / (k + '.json') for k in ('programs', 'evidence')}
    raw = {k: p.read_bytes() for k,p in paths.items()}
    data = {k: json.loads(v.decode('utf-8-sig')) for k,v in raw.items()}
    require(all(isinstance(v, list) for v in data.values()), '基础库必须为记录数组，预览占位文件不能发布')
    programs = {p['id']: p for p in data['programs']}
    evidence = {e['id']: e for e in data['evidence']}
    require(len(programs) == len(data['programs']) and len(evidence) == len(data['evidence']), '基础库存在重复ID')
    diff = []
    for c in proposal['changes']:
        require(c['program_id'] in programs, '未知项目ID，先由维护者登记学校/专业/年度')
        p = programs[c['program_id']]
        old = p.setdefault('facts', {}).get(c['field'])
        require(digest(old) == c['expected_sha256'], '旧值已变化，须重新核对，禁止覆盖')
        e = copy.deepcopy(c['evidence'])
        e['reviewed_by'] = approval['reviewer']
        require(e['id'] not in evidence or evidence[e['id']] == e, '来源ID冲突')
        evidence[e['id']] = e
        new = {'value':c['value'], 'scope':c['scope'], 'status':'verified', 'evidence_ids':[e['id']]}
        p['facts'][c['field']] = new
        diff.append({'program_id':p['id'], 'field':c['field'], 'before':old, 'after':new})
    require(all(p.read_bytes() == raw[k] for k,p in paths.items()), '基础库并发变化，重新运行')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write_new(out/'programs.json', data['programs'])
    write_new(out/'evidence.json', list(evidence.values()))
    write_new(out/'review.json', approval)
    write_new(out/'diff.json', diff)
    manifest = {'status':'staged_not_deployed', 'proposal_sha256':digest(proposal),
                'base_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in raw.items()},
                'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}}
    write_new(out/'manifest.json', manifest)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('validate'); v.add_argument('proposal')
    h = sub.add_parser('hash-field'); h.add_argument('programs'); h.add_argument('program_id'); h.add_argument('field')
    r = sub.add_parser('review'); r.add_argument('proposal'); r.add_argument('--reviewer', required=True); r.add_argument('--note', required=True); r.add_argument('--out', required=True)
    s = sub.add_parser('stage'); s.add_argument('proposal'); s.add_argument('--approval', required=True); s.add_argument('--base', required=True); s.add_argument('--out', required=True)
    a = ap.parse_args()
    if a.cmd == 'hash-field':
        p = next(p for p in read(a.programs) if p['id'] == a.program_id)
        print(digest(p.get('facts', {}).get(a.field))); return
    p = read(a.proposal)
    if a.cmd == 'validate': result = validate(p)
    elif a.cmd == 'review':
        result = review(p, a.reviewer, a.note); write_new(a.out, result)
    else: result = stage(p, read(a.approval), a.base, a.out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, StopIteration) as exc:
        raise SystemExit('处理未完成：' + str(exc))
