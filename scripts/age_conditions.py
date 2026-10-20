"""Scoped Leeds age process. No automatic approval of safeguarding or visas."""
import datetime as dt

def age_on(birth, on):
    return on.year-birth.year-((on.month,on.day)<(birth.month,birth.day))

def check(value, policy_year, today):
    def answer(state, reason, **extra):
        return dict(state=state,reason=reason,**extra)
    unknown=lambda reason,**extra:answer('unknown',reason,**extra)
    if type(policy_year) is not int or not 2000<=policy_year<=2100 or not isinstance(value,dict):
        return unknown('入学年度或独立年龄资料待核')
    try:reviewed=dt.date.fromisoformat(value.get('reviewed_on',''))
    except (TypeError,ValueError):return unknown('年龄与签证适用性审阅日期待核')
    if not 0<=(today-reviewed).days<=90 or not isinstance(value.get('reviewer'),str) or not value['reviewer'].strip():
        return unknown('年龄与签证适用性审阅过期、未来或缺审阅人')
    try:birth=dt.date.fromisoformat(value.get('date_of_birth',''))
    except (TypeError,ValueError):return unknown('出生日期待核')
    anchor=dt.date(policy_year,10,1)
    if birth>today or birth>=anchor:return unknown('出生日期与时间基准不一致')
    age=age_on(birth,anchor);visa=value.get('requires_student_visa')
    if type(visa) is not bool:return unknown('是否需要Student visa须单独核验，不能按国籍猜测',age_at_october_1=age)
    common=dict(age_at_october_1=age,anchor_date=anchor.isoformat())
    if age<16:
        if visa:return answer('not_satisfied','按该校政策：10月1日未满16且需要Student visa，不能受理此路径',**common)
        return unknown('未满16且不需Student visa：需个别风险评估与University Secretary批准，不能自动拒绝或放行',
                       required_processes=['individual_age_risk_assessment','university_secretary_approval','parental_consent_and_relationship','individual_safeguarding_conditions'],**common)
    if age<18:
        return unknown('16–17岁：需学校年龄风险评估、监护同意及个案保障条件；材料已备不代表学校批准',
                       required_processes=['age_risk_assessment','parental_consent_and_relationship','individual_safeguarding_conditions'],
                       uk_local_guardian='recommended_not_universally_required',**common)
    if not visa:return answer('satisfied','10月1日已满18且不需Student visa；该页无额外年龄招生流程',**common)
    try:cas=dt.date.fromisoformat(value.get('cas_issued_on',''))
    except (TypeError,ValueError):return unknown('需Student visa：CAS实际签发日期待核，不能用预计日期放行',**common)
    if not birth<=cas<=today or cas>anchor:
        return unknown('CAS日期不是可核验的既往签发日或不属本规则时间范围',**common)
    age_cas=age_on(birth,cas);common['age_at_cas']=age_cas
    if age_cas>=18:return answer('satisfied','10月1日与CAS签发时均满18；该页无额外年龄招生流程',**common)
    if age_cas==17:return unknown('CAS签发时17岁：需核学校办理的监护同意和关系证明流程',
                                required_processes=['cas_parental_consent','guardian_relationship_evidence'],**common)
    return unknown('CAS时未满17的个案超出当前已核成人分支，需学校确认',**common)
