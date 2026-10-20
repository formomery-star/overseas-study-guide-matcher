"""Automatic timing comparison and phase diagnosis for real CLI generations."""
import datetime as dt
import json
import statistics
from pathlib import Path
import uuid

def diagnose(current,history):
    peers=[h for h in history if h.get('scope')==current['scope'] and h.get('success')]
    peers.sort(key=lambda h:h['at']);last=peers[-1] if peers else None
    median=statistics.median(h['elapsed_seconds'] for h in peers[-3:]) if peers else None
    changed={k:current['phases'].get(k,0)-last.get('phases',{}).get(k,0) for k in current['phases']} if last else {}
    slower=bool(last and (current['elapsed_seconds']>last['elapsed_seconds'] or current['elapsed_seconds']>median))
    slowest=max(changed,key=changed.get) if changed and max(changed.values())>0 else None
    actions={'form_to_selection':'核对项目数量、规则版本与转档耗时；同输入复测后再调整解析或索引',
             'content_preparation':'核对学校页数、岗位样本及缺口数；不能通过少展示缺口提速',
             'save_and_pdf':'复测浏览器启动与PDF生成，检查字体和版面；不跳过验版'}
    return {'previous_id':last['id'] if last else None,'median_seconds':median,'slower':slower,
            'same_input':last.get('form_sha256')==current.get('form_sha256') if last else None,
            'same_database':last.get('database_hashes')==current.get('database_hashes') if last else None,
            'phase_delta_seconds':changed,'largest_increase_phase':slowest,
            'status':'待同输入复测' if slower else '未发现同范围变慢' if last else '建立基线',
            'action':actions.get(slowest,'保留本次基线，后续同范围自动比较'),
            'boundary':'自动定位环节，不据单次波动宣称已找到根因或已优化；代码修复仍需回归验收'}

def record_generation(manifest,out,history_dir=None):
    history_dir=Path(history_dir) if history_dir else Path(__file__).resolve().parents[1]/'任务管理/流程优化/自动生成计时'
    history_dir.mkdir(parents=True,exist_ok=True)
    record={'id':uuid.uuid4().hex,'at':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        'success':True,'scope':{'major_ids':manifest['major_ids'],'pages':manifest['pages'],'pdf':manifest['pdf_generated']},
        'elapsed_seconds':manifest['elapsed_seconds'],'phases':manifest['phase_seconds'],
        'form_sha256':manifest['form_sha256'],'database_hashes':manifest['database_hashes']}
    history=[]
    for p in history_dir.glob('*.json'):
        try:history.append(json.loads(p.read_text(encoding='utf-8')))
        except (ValueError,OSError):continue
    record['diagnosis']=diagnose(record,history)
    value=json.dumps(record,ensure_ascii=False,indent=2)+'\n'
    (history_dir/(record['id']+'.json')).write_text(value,encoding='utf-8')
    (out/'自动优化记录.json').write_text(value,encoding='utf-8')
    d=record['diagnosis']
    (out/'流程优化.md').write_text('# 本次自动生成耗时复核\n\n'+f"耗时 {record['elapsed_seconds']:.3f} 秒；状态：{d['status']}。\n\n"+d['action']+'。\n\n'+d['boundary']+'。\n',encoding='utf-8')
    return record
