const groups = {
  student: [
    ["姓名","text","学生姓名"],["学校年级","text","学校及年级"],["毕业年月","text","预计高中毕业年月，如2027年6月"],["入学年月","text","目标本科入学年月，如2028年9月"],
    ["课程体系","select","课程体系",["AP","IB DP","A-Level","普通高中高考体系","普通高中美术/艺术方向","加拿大课程","其他国际课程","其他 / 尚未确定"]],
    ["毕业资格","text","预计取得的高中毕业证或资格；不确定可留空"],["学校所在地","text","国家/地区、城市"],["国籍居留类别","text","可选填类别；不要填写证件号码"],
    ["留学地区","multi","希望考虑的留学地区",["美国","英国","加拿大","澳大利亚","新加坡","中国香港","日本","欧洲其他地区","其他","尚未想好"]],
    ["就业地点","text","未来倾向就业国家/地区；不确定可留空"],["学校年级_备用","hidden",""]
  ],
  academic: [["成绩材料状态","select","高中成绩单",["学校统一提供","已附","待补"]],["成绩说明","textarea","成绩、课程与正式考试说明（可写GPA/年级、英语总分与小分、日期、版本、预估/模考/计划）"],["IB各科目授课语言说明","textarea","IB学生可选：逐科授课语言；此项未经核验不会用于语言豁免"]],
  awards: [["奖项状态","select","奖项情况",["有且附证明","有，证明待补","无"]]],
  activity: [["活动状态","select","作品或活动情况",["有且附证明","有，证明待补","无"]]],
  interests: [
    ["喜欢学科","textarea","最喜欢的学科（最多3门，逗号分隔）"],["不喜欢学科","text","最不喜欢的学科（可选）"],
    ["愿意任务","multi","最愿意长期做的任务（可多选2项）",[["A","解题 / 分析数据"],["B","编程 / 做装置"],["C","实验 / 探索自然"],["D","阅读 / 写作 / 语言"],["E","设计 / 艺术创作"],["F","组织 / 商业策划"],["G","帮助 / 教学 / 照护"],["H","表演 / 音乐"],["I","体育 / 户外"],["J","其他"],["K","暂不确定"]]],
    ["不愿意任务","multi","最不喜欢的任务（可选）",[["A","解题 / 分析数据"],["B","编程 / 做装置"],["C","实验 / 探索自然"],["D","阅读 / 写作 / 语言"],["E","设计 / 艺术创作"],["F","组织 / 商业策划"],["G","帮助 / 教学 / 照护"],["H","表演 / 音乐"],["I","体育 / 户外"],["J","其他"],["K","暂不确定"]]],
    ["意向专业职业","textarea","想探索的专业或职业（尽量具体）"],["工作看重","multi","未来工作看重（可多选）",["兴趣","收入","稳定","创造 / 挑战","帮助别人","工作生活平衡","尚未想好"]],
    ["留学地区","multi","",[]]
  ],
  learning: [["主动学习内容","textarea","最近一个月主动学习了什么？留下了什么成果？"],["学习成果","text","可选：作品/课程/结果"],["遇阻处理","textarea","最近遇到困难时怎么处理？"],["合作角色","text","最近一次合作中的实际角色"],["合作贡献","textarea","你的具体贡献"],["本人职责","textarea","活动中的具体职责"],["活动时长","text","持续时间"],["英语使用","multi","近3个月实际用英语做过什么",["读材料并记笔记","听课并完成任务","做展示并回答问题","用英语持续合作","尚未做到"]],["英语场景","textarea","具体场景/课程/成果"],["新环境行为","multi","近期如何适应新环境",["独立安排日常","遇到陌生规则主动求助","与不同背景者合作","尚无相关机会"]],["新环境场景","textarea","具体场景"],
    ["作品准备状态","text","艺术/作品类方向：作品集、演出或赛事材料现状（可选）"],["作品链接","text","可选作品链接；请确认链接可公开访问，不要放密码"],["接受额外考核","select","是否愿意准备作品、试演、面试或额外考核",["是","否","待定"]],["执业地区","text","如涉及执照/执业，意向国家或地区（可选）"],["接受较长训练","select","是否接受较长培养、额外考试或训练",["是","否","待定"]],["特殊方向","text","特别兴趣方向（可选）"],["不能接受","textarea","不能接受的任务/环境（可选）"]],
  family: [["年预算万元","number","每年留学支出上限（人民币万元）"],["总预算万元","number","全部培养预算上限（人民币万元）"],["依赖奖助","select","是否必须依赖奖助学金",["是","否","待定"]],["接受预科","select","是否接受预科/衔接课程/延长学制",["是","否","待定"]],["父亲职业","text","父亲行业/岗位（可选；不用于推导预算）"],["母亲职业","text","母亲行业/岗位（可选；不用于推导预算）"],["实际支持","multi","家庭实际能提供的支持（可多选）",["暂不能提供","专业指导","行业交流","项目协助","经济支持","其他"]],["每月支持小时","number","家长每月可投入的时间（小时，可选）"],["家长期望","textarea","家长期望孩子探索的方向"],["家长可接受地区","multi","家长可接受的留学地区",["美国","英国","加拿大","澳大利亚","新加坡","中国香港","日本","欧洲其他地区","其他"]],["亲子分歧","textarea","学生与家长意见不同之处（可选）"],["最长培养年数","number","最长可接受培养年数（可选）"]]
};

function makeField(spec, parent) {
  const [name,type,label,options] = spec;
  if(type === "hidden") return;
  const wrap = document.createElement("label"); wrap.className = "field" + (type === "textarea" ? " full" : "");
  const span = document.createElement("span"); span.textContent = label; wrap.appendChild(span);
  if(type === "textarea") { const el=document.createElement("textarea"); el.name=name; el.rows=3; el.maxLength=5000; el.placeholder="可留空；仅按实际情况填写"; wrap.appendChild(el); }
  else if(type === "select") { const el=document.createElement("select"); el.name=name; const empty=document.createElement("option");empty.value="";empty.textContent="请选择 / 暂不确定";el.appendChild(empty);(options||[]).forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;el.appendChild(o)});wrap.appendChild(el); }
  else if(type === "multi") { const box=document.createElement("div");box.className="checks";(options||[]).forEach(v=>{const value=Array.isArray(v)?v[0]:v,txt=Array.isArray(v)?v[1]:v;const l=document.createElement("label");l.className="choice";const i=document.createElement("input");i.type="checkbox";i.name=name;i.value=value;const s=document.createElement("span");s.textContent=txt;l.append(i,s);box.appendChild(l)});wrap.appendChild(box); }
  else { const el=document.createElement("input"); el.name=name; el.type=type === "number"?"number":"text"; el.maxLength=type==="number"?undefined:500; if(type==="number"){el.min="0";el.step="0.1";} wrap.appendChild(el); }
  parent.appendChild(wrap);
}
Object.entries(groups).forEach(([key,specs])=>{const id=key+"-fields",el=document.getElementById(id);if(el)specs.forEach(s=>makeField(s,el));});
for(const requiredField of ["姓名","课程体系","意向专业职业"]){const field=document.querySelector(`#intake-form [name="${requiredField}"]`);if(field){field.required=true;field.setAttribute("aria-required","true");}}
// Keep the single canonical study-region field rather than collecting duplicate values.
document.querySelectorAll('[name="留学地区"]').forEach((el,i)=>{if(i>0)el.closest(".field")?.remove()});

const gradeList=document.getElementById("grades");
function addGrade(){const row=document.createElement("div");row.className="grade-row";row.innerHTML='<label>体系 / 考试<input data-k="system" maxlength="80" placeholder="AP / IB / IELTS"></label><label>科目<input data-k="subject" maxlength="120" placeholder="准确科目名"></label><label>级别<input data-k="level" maxlength="20" placeholder="HL / SL（可选）"></label><label>成绩<input data-k="value" maxlength="20" placeholder="成绩"></label><label>满分<input data-k="scale" maxlength="20" placeholder="满分"></label><label>日期<input data-k="date" maxlength="20" placeholder="YYYY-MM 或 YYYY-MM-DD"></label><label>成绩类型<select data-k="record_type"><option value="">请选择</option><option value="official">正式</option><option value="predicted">预估</option><option value="mock">模考</option><option value="school_grade">校内成绩</option><option value="planned">计划</option></select></label><button type="button" class="remove" aria-label="删除成绩行">移除</button>';row.querySelector(".remove").onclick=()=>row.remove();gradeList.appendChild(row)}
document.getElementById("add-grade").addEventListener("click",addGrade); addGrade();

function readForm(){const out={};for(const el of document.querySelectorAll("#intake-form [name]")){if(el.name==="学校年级_备用"||el.type==="file")continue;if(el.type==="checkbox"){if(el.checked){(out[el.name]??=[]).push(el.value)}continue;}const v=el.value.trim();if(v)out[el.name]=v;}
 const academic=[];for(const row of gradeList.querySelectorAll(".grade-row")){const r={};row.querySelectorAll("[data-k]").forEach(el=>{if(el.value.trim())r[el.dataset.k]=el.value.trim()});if(Object.keys(r).length){if(r.value!==undefined)r.value=Number(r.value);if(r.scale!==undefined)r.scale=Number(r.scale);if(r.subject&&!r.record_type)r.record_type="unspecified";academic.push(r)}}if(academic.length)out["学术记录"]=academic;
 return out;}

const form=document.getElementById("intake-form"),button=document.getElementById("submit"),result=document.getElementById("result");
form.addEventListener("submit",async e=>{e.preventDefault();result.className="";result.textContent="正在安全提交…";button.disabled=true;try{const dataForm=new FormData();dataForm.append("answers",JSON.stringify(readForm()));for(const f of document.getElementById("attachments").files)dataForm.append("attachments",f,f.name);const res=await fetch("/api/submissions",{method:"POST",body:dataForm});const data=await res.json();if(!res.ok)throw new Error(data.message||data.error||"submit_failed");sessionStorage.setItem("intakeReceipt",data.receipt);result.className="result-card";result.innerHTML='<strong>问卷已收妥，正在生成内部预览</strong><p>请保存本次查询码。当前预览仅管理员可见，锁定模板通用生成验收后才会开放正式交付。</p><code></code><div class="status-line">状态：<span>排队中</span></div>';result.querySelector("code").textContent=data.receipt;poll();}catch(err){result.className="error";result.textContent="提交未成功，请检查必填项后重试。如持续失败，请联系项目管理员。"+(err.message?" "+err.message:"");}finally{button.disabled=false;}});
async function poll(){const receipt=sessionStorage.getItem("intakeReceipt");if(!receipt)return;try{const r=await fetch("/api/status/"+encodeURIComponent(receipt));const d=await r.json();if(r.ok){const status={queued:"排队中",generating_preview:"正在生成内部预览",preview_ready:"内部预览已生成，等待管理员审核",failed:"生成遇到问题，管理员将复核"};const line=document.querySelector("#result .status-line span");if(line)line.textContent=status[d.status]||d.status;if(["queued","generating_preview"].includes(d.status))setTimeout(poll,2500);}}catch{}}

