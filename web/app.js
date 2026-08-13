
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

function motionEnabled(){ return !!window.gsap; }
function textTargets(root){
  if(!root) return [];
  return [...root.querySelectorAll(".chat-name,.bubble,.eyebrow,h3,h4,p,.gate h4,.gate p,.gate-result,.round-badge,.detail-btn,.final-metrics,.conclusion-box,.report-actions,.human-tip")]
    .filter((element,index,items)=>!items.some(other=>other!==element && other.contains(element)));
}
function animateTextBlocks(root,{delay=.05,stagger=.045}={}){
  if(!motionEnabled()) return;
  const targets=textTargets(root);
  if(!targets.length) return;
  window.gsap.fromTo(targets,{autoAlpha:0,y:8},{autoAlpha:1,y:0,duration:.38,delay,stagger,ease:"power2.out",clearProps:"transform,opacity,visibility"});
}
function splitWelcomeHeadline(){
  const headline=$(".welcome h1");
  if(!headline || headline.dataset.split) return headline;
  const walker=document.createTreeWalker(headline,NodeFilter.SHOW_TEXT);
  const nodes=[];
  while(walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node=>{
    const fragment=document.createDocumentFragment();
    [...node.textContent].forEach(character=>{
      const span=document.createElement("span");
      span.className="headline-char";
      span.textContent=character === " " ? "\u00a0" : character;
      fragment.append(span);
    });
    node.replaceWith(fragment);
  });
  headline.dataset.split="true";
  return headline;
}
function animateIn(element,{y=10,x=0,scale=1,duration=.48,delay=0}={}){
  if(!motionEnabled() || !element) return;
  window.gsap.fromTo(element,{autoAlpha:0,y,x,scale},{autoAlpha:1,y:0,x:0,scale:1,duration,delay,ease:"power3.out",clearProps:"transform,opacity,visibility"});
}
function animateWelcome(replay=false){
  if(!motionEnabled()) return;
  const welcome=$(".welcome");
  if(!welcome || (welcome.dataset.animated && !replay)) return;
  welcome.dataset.animated="true";
  if(replay) window.gsap.killTweensOf([welcome,...welcome.querySelectorAll("*")]);
  const orbit=welcome.querySelector(".welcome-orbit");
  const headline=splitWelcomeHeadline();
  const supporting=[welcome.querySelector(".welcome-kicker"),welcome.querySelector("h1")?.nextElementSibling,welcome.querySelector(".welcome-actions")].filter(Boolean);
  const chars=[...headline.querySelectorAll(".headline-char")];
  window.gsap.set([orbit,...supporting],{autoAlpha:0,y:14});
  window.gsap.set(chars,{autoAlpha:0,y:24,rotateX:-68,transformOrigin:"50% 100%"});
  window.gsap.timeline({defaults:{ease:"power3.out"}})
    .to(orbit,{autoAlpha:1,y:0,duration:.48})
    .to(welcome.querySelector(".welcome-kicker"),{autoAlpha:1,y:0,duration:.36},"-=.12")
    .to(chars,{autoAlpha:1,y:0,rotateX:0,duration:.5,stagger:.028,clearProps:"transform,opacity,visibility"},"-=.08")
    .to(supporting.slice(1),{autoAlpha:1,y:0,duration:.42,stagger:.1,clearProps:"transform,opacity,visibility"},"-=.18");
  window.gsap.to(orbit,{rotate:360,duration:9,repeat:-1,ease:"none"});
  window.gsap.to(orbit,{y:-5,duration:2.4,repeat:-1,yoyo:true,ease:"sine.inOut"});
  window.gsap.to(orbit.querySelectorAll("span,i,b"),{scale:1.32,duration:1.15,repeat:-1,yoyo:true,stagger:.16,ease:"sine.inOut"});
}
function animateNewChatItem(){
  const row=$("#chatInner > .chat-row:last-child");
  animateIn(row,{y:14,duration:.42});
  animateTextBlocks(row,{delay:.1,stagger:.035});
}


let currentResearchId = null;
let currentQuestion = null;
let currentEventSource = null;
let reviewCard = null;
let questionsCache = [];
let historyCache = [];
let activeTyping = null;
let reviewRenderQueue = [];
let reviewRenderBusy = false;

function typingSurface(target){
  return target?.closest(".bubble,.system-note");
}
function finishTyping(){
  if(!activeTyping) return;
  window.clearTimeout(activeTyping.timer);
  activeTyping.entries.forEach(entry=>{
    if(entry.target?.isConnected){
      entry.target.textContent=entry.text;
      typingSurface(entry.target)?.classList.remove("is-typing");
    }
  });
  activeTyping=null;
}
function queueTypingEntries(entries){
  const prepared=entries
    .filter(entry=>entry?.target?.isConnected)
    .map(entry=>({target:entry.target,text:String(entry.text??"")}));
  if(!prepared.length) return;

  prepared.forEach(entry=>{ entry.target.textContent=""; });
  if(activeTyping){
    const state=activeTyping;
    const targets=new Set(prepared.map(entry=>entry.target));
    const current=state.entries[state.index];
    const pending=state.entries.slice(state.index+1).filter(entry=>!targets.has(entry.target));
    if(current && targets.has(current.target)){
      typingSurface(current.target)?.classList.remove("is-typing");
      window.clearTimeout(state.timer);
      state.entries=[...state.entries.slice(0,state.index),...prepared,...pending];
      state.index=state.entries.length-pending.length-prepared.length;
      state.character=0;
      state.timer=window.setTimeout(()=>typeNextTypingEntry(state),0);
    }else{
      state.entries=[...state.entries.slice(0,state.index+1),...pending,...prepared];
    }
    return;
  }

  activeTyping={entries:prepared,index:0,character:0,timer:null};
  typeNextTypingEntry(activeTyping);
}
function typeNextTypingEntry(state){
  if(activeTyping!==state) return;
  const entry=state.entries[state.index];
  if(!entry){ activeTyping=null; return; }
  if(!entry.target.isConnected){ state.index++; state.character=0; typeNextTypingEntry(state); return; }
  const chars=[...entry.text];
  const surface=typingSurface(entry.target);
  surface?.classList.add("is-typing");
  const tick=()=>{
    if(activeTyping!==state) return;
    if(!entry.target.isConnected){
      state.index++;
      state.character=0;
      typeNextTypingEntry(state);
      return;
    }
    const last=chars[state.character];
    const step=/[\uFF0C\u3001\uFF1A\uFF1B]/.test(last||"") ? 1 : Math.min(2,chars.length-state.character);
    state.character+=step;
    entry.target.textContent=chars.slice(0,state.character).join("");
    scrollBottom();
    if(state.character>=chars.length){
      surface?.classList.remove("is-typing");
      state.index++;
      state.character=0;
      state.timer=window.setTimeout(()=>typeNextTypingEntry(state),65);
      return;
    }
    const pause=/[\u3002\uFF01\uFF1F]/.test(chars[state.character-1]) ? 125 : /[\uFF0C\u3001\uFF1A\uFF1B]/.test(chars[state.character-1]) ? 62 : 24;
    state.timer=window.setTimeout(tick,pause);
  };
  tick();
}
function typeAssistantText(target,text){
  queueTypingEntries([{target,text}]);
}
function waitForTyping(){
  return new Promise(resolve=>{
    const check=()=>activeTyping ? window.setTimeout(check,24) : resolve();
    check();
  });
}
function enqueueReviewRender(render){
  reviewRenderQueue.push(render);
  if(reviewRenderBusy) return;
  reviewRenderBusy=true;
  const next=async()=>{
    const action=reviewRenderQueue.shift();
    if(!action){ reviewRenderBusy=false; return; }
    action();
    await waitForTyping();
    window.setTimeout(next,110);
  };
  next();
}
const GATE_META = {
  debate: {name:"思辨审查", icon:"⚖", cls:"debate", desc:"主动寻找反例、边界条件、替代解释与理论漏洞。"},
  trace: {name:"溯源审查", icon:"⌕", cls:"trace", desc:"核验引用真实性、原文语义一致性与证据支持强度。"},
  causal: {name:"因果审查", icon:"⌘", cls:"causal", desc:"检查混杂因素、统计稳定性以及相关性是否被误写为因果。"},
};

function esc(text=""){
  return String(text).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
}

async function api(url, options={}){
  const res=await fetch(url,{
    headers:{"Content-Type":"application/json",...(options.headers||{})},
    ...options
  });
  if(!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`);
  return res.json();
}

function setWorkspaceMode(active){
  const app=$(".app");
  app.classList.toggle("has-research",!!active);
  const composer=$(".composer-wrap");
  if(motionEnabled() && active){
    window.gsap.fromTo(composer,{autoAlpha:0,y:18},{autoAlpha:1,y:0,duration:.42,ease:"power3.out",clearProps:"transform,opacity,visibility"});
  }
}
function animateShell(){
  if(!motionEnabled()) return;
  const groups=[
    $(".brand"),$(".new-btn"),$(".left-search"),$(".history-title"),$(".history"),$(".left-footer"),
    $(".topbar")
  ].filter(Boolean);
  window.gsap.fromTo(groups,{autoAlpha:0,y:10},{autoAlpha:1,y:0,duration:.42,stagger:.045,ease:"power2.out",clearProps:"transform,opacity,visibility"});
}
function scrollBottom(){
  requestAnimationFrame(()=>$("#chatWrap").scrollTo({top:$("#chatWrap").scrollHeight,behavior:motionEnabled()?"smooth":"auto"}));
}

function closeStream(){
  if(currentEventSource){
    currentEventSource.close();
    currentEventSource=null;
  }
}

function setComposerEnabled(enabled, needsHuman=false){
  $("#expertInput").disabled=!enabled;
  $("#sendBtn").disabled=!enabled;
  $("#stopBtn").disabled=!enabled;
  $(".composer-box").classList.toggle("needs-human",!!needsHuman);
  $("#expertInput").placeholder=needsHuman
    ?"已达到自动审查上限，请输入专家意见以继续研究…"
    :enabled
      ?"向 AI Scientist 提出专家意见，例如：请重点检查低资源地区的外推边界…"
      :"开始研究后，可随时在这里提出专家意见…";
  $(".composer-hint").textContent=needsHuman
    ?"当前研究需要专家判断；提交意见后系统会重新执行受影响的审查"
    :"人工意见会加入当前研究，并重新执行受影响的审查环节";
}

function addUserMessage(text){
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row user">
    <div class="chat-avatar">RS</div>
    <div class="chat-content"><div class="chat-name">Researcher</div><div class="bubble">${esc(text)}</div></div>
  </div>`);
  animateNewChatItem();
  scrollBottom();
}

function addAssistantMessage(text){
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row">
    <div class="chat-avatar">AI</div>
    <div class="chat-content"><div class="chat-name">AI Scientist</div><div class="bubble"><span class="typed-text" aria-live="polite"></span></div></div>
  </div>`);
  const row=$("#chatInner > .chat-row:last-child");
  animateIn(row,{y:14,duration:.42});
  typeAssistantText(row.querySelector(".typed-text"),text);
  scrollBottom();
}

function addSystemNote(text){
  $("#chatInner").insertAdjacentHTML("beforeend",`<div class="system-note"><span class="typed-text" aria-live="polite"></span></div>`);
  typeAssistantText($("#chatInner > .system-note:last-child .typed-text"),text);
  scrollBottom();
}

function addHypothesisCard(h){
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row">
    <div class="chat-avatar">AI</div>
    <div class="chat-content" style="max-width:100%">
      <div class="chat-name">AI Scientist</div>
      <div class="hypothesis-card">
        <span class="eyebrow">CANDIDATE HYPOTHESIS</span>
        <h3>${esc(h.title)}</h3>
        <p>${esc(h.summary||"")}</p>
        ${h.falsifiable?`<div class="hypothesis-meta"><b>可证伪条件：</b>${esc(h.falsifiable)}</div>`:""}
      </div>
    </div>
  </div>`);
  animateNewChatItem();
  scrollBottom();
}

function createReviewCard(round){

  const id=`review-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row">
    <div class="chat-avatar">AI</div>
    <div class="chat-content" style="max-width:100%">
      <div class="chat-name">AI Scientist</div>
      <div class="research-card" id="${id}">
        <div class="research-card-head">
          <div><span class="eyebrow">TRI-GATE SCIENTIFIC VALIDATION</span><h3>第 ${round} 轮 · 三重科学审查</h3></div>
          <span class="round-badge">自动审查中</span>
        </div>
        <div class="gates">
          ${["debate","trace","causal"].map(g=>{
            const m=GATE_META[g];
            return `<div class="gate ${m.cls}" data-gate="${g}">
              <div class="gate-top">
                <div class="gate-title"><div class="gate-icon">${m.icon}</div><h4>${m.name}</h4></div>
                <span class="status pending">等待中</span>
              </div>
              <p>${m.desc}</p>
              <div class="meter"><i style="width:0%"></i></div>
              <div class="gate-audit" aria-live="polite"></div>
              <div class="gate-score"><span>评分</span><b>—</b></div>
              <div class="gate-result">等待审查结果</div>
              <button class="detail-btn" data-gate="${g}">查看详细审查 →</button>
            </div>`;
          }).join("")}
        </div>
        <div class="revision-strip" style="display:none">
          <div class="rev-icon">↻</div>
          <div><b>本轮存在未通过项</b><p>系统会根据固定审查标准修订假设，不会为了“过审”自动降低标准。</p></div>
        </div>
      </div>
    </div>
  </div>`);
  const card=$("#"+id);
  reviewCard=card;
  card.querySelectorAll(".detail-btn").forEach(btn=>{
    btn.onclick=()=>openGateDrawer(btn.dataset.gate,card);
  });
  animateIn(card,{y:18,duration:.5});
  scrollBottom();
}

function statusText(status){
  return {pending:"等待",running:"审查中",passed:"通过",failed:"未通过",conditional:"有条件通过"}[status]||status;
}

function addAuditStep(event){
  if(!reviewCard) return;
  const gate=reviewCard.querySelector(`[data-gate="${event.gate}"]`);
  if(!gate) return;
  const badge=gate.querySelector(".status");
  if(badge.classList.contains("pending")){
    badge.className="status running";
    badge.textContent="\u5ba1\u67e5\u4e2d";
  }
  gate.classList.add("is-auditing");
  const meter=gate.querySelector(".meter i");
  const progress=Math.min(82,12+(event.step/event.total_steps)*70);
  if(motionEnabled()) window.gsap.to(meter,{width:`${progress}%`,duration:.32,ease:"power2.out"});
  else meter.style.width=`${progress}%`;
  const trace=gate.querySelector(".gate-audit");
  const item=document.createElement("div");
  item.className=`audit-step ${event.stage||"focus"}`;
  item.innerHTML=`<span class="audit-index">${String(event.step).padStart(2,"0")}</span><div><b>${esc(event.label||"\u5ba1\u67e5\u8bb0\u5f55")}</b><p class="audit-text"></p></div>`;
  item.querySelector(".audit-text").textContent=event.text||"";
  trace.append(item);
  animateIn(item,{y:7,duration:.3});
  scrollBottom();
}

function updateGate(gate,status,progress=100,issues=[],detail=null){
  if(!reviewCard) return;
  const el=reviewCard.querySelector(`[data-gate="${gate}"]`); if(!el) return;
  const badge=el.querySelector(".status");
  badge.className=`status ${status}`;
  badge.textContent=statusText(status);
  const meter=el.querySelector(".meter i");
  if(motionEnabled()) window.gsap.to(meter,{width:`${progress}%`,duration:.42,ease:"power2.out"});
  else meter.style.width=`${progress}%`;
  el.classList.remove("is-auditing");
  const gateResult=el.querySelector(".gate-result");
  gateResult.textContent=detail?.verdict || issues?.[0] || statusText(status);
  el.querySelector(".gate-score b").textContent=detail?.score!=null?`${detail.score}/100`:"—";
  el.dataset.detail=JSON.stringify(detail||{gate,status,issues});
  if(motionEnabled()){
    window.gsap.fromTo(el.querySelector(".status"),{autoAlpha:0,x:-5},{autoAlpha:1,x:0,duration:.28,ease:"power2.out"});
    window.gsap.fromTo(el.querySelector(".gate-score b"),{scale:.82},{scale:1,duration:.3,ease:"back.out(2)"});
  }
}

function showReviewFailed(e){
  if(reviewCard){
    reviewCard.querySelector(".revision-strip").style.display="flex";
    reviewCard.querySelector(".round-badge").textContent="未通过 · 准备修订";
  }
  addSystemNote(`第 ${e.round} 轮未通过 · 固定审查标准共发现 ${e.revision_count} 个待修订问题`);
}

function addRevisionCard(e){
  const changes=e.changes||[];
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row">
    <div class="chat-avatar">AI</div>
    <div class="chat-content">
      <div class="chat-name">AI Scientist</div>
      <div class="bubble"><span class="typed-text structured-typed" aria-live="polite"></span></div>
    </div>
  </div>`);
  const revisionRow=$("#chatInner > .chat-row:last-child");
  animateIn(revisionRow,{y:14,duration:.42});
  typeAssistantText(revisionRow.querySelector(".typed-text"),["正在修订候选假设",...changes.map(change=>`• ${change}`)].join("\n"));
  scrollBottom();
}

function showHumanRequired(e){
  setComposerEnabled(true,true);

  if(reviewCard){
    reviewCard.querySelector(".round-badge").textContent="达到自动审查上限";
    reviewCard.querySelector(".round-badge").classList.add("human");
  }

  const unresolved=e.unresolved||[];
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row">
    <div class="chat-avatar">AI</div>
    <div class="chat-content" style="max-width:100%">
      <div class="chat-name">AI Scientist</div>
      <div class="human-required">
        <span class="eyebrow">HUMAN REVIEW REQUIRED</span>
        <h3>已完成 3 轮自动审查，仍有问题无法可靠解决</h3>
        <p>${esc(e.message||"需要专家提供新的判断或约束。")}</p>
        <div class="unresolved-list">
          ${unresolved.length?unresolved.slice(0,6).map(x=>`
            <div class="unresolved-item">
              <span>${esc(x.gate_name||x.gate)}</span>
              <b>${esc(x.title)}</b>
              <small>建议：${esc(x.recommendation||"请专家判断")}</small>
            </div>`).join(""):`<div class="unresolved-item"><b>当前仍有未通过审查项</b><small>请在下方输入专家意见。</small></div>`}
        </div>
        <div class="human-tip">↓ 请使用下方聊天框介入研究</div>
      </div>
    </div>
  </div>`);
  const humanCard=$("#chatInner > .chat-row:last-child .human-required");
  animateIn(humanCard,{y:18,duration:.5});
  addAssistantMessage("我不会继续自动修改直到“强行过审”。请提供新的专家意见、边界条件或证据要求，我会在保持原审查标准的前提下重新验证。");
  scrollBottom();
  loadHistory();
}

function addFinalResult(result,afterFeedback=false){
  setComposerEnabled(true,false);

  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row">
    <div class="chat-avatar">AI</div>
    <div class="chat-content" style="max-width:100%">
      <div class="chat-name">AI Scientist</div>
      <div class="final-card">
        <span class="eyebrow">FINAL RESEARCH RESULT</span>
        <h3>✓ ${afterFeedback?"吸收专家意见后重新审查完成":"三重科学审查达到可接受状态"}</h3>
        <p><b>${esc(result.title||"最终科学假设")}</b></p>
        <p>${esc(result.hypothesis||"")}</p>
        <div class="final-metrics">
          <div><span>可信评分</span><b>${result.score??"—"}/100</b></div>
          <div><span>支持证据</span><b>${result.support_evidence??"—"}</b></div>
          <div><span>反向证据</span><b>${result.counter_evidence??"—"}</b></div>
          <div><span>有效引用</span><b>${result.citations??"—"}</b></div>
        </div>
        ${result.conclusion?`<div class="conclusion-box"><span>最终综合结论</span><p>${esc(result.conclusion)}</p></div>`:""}
        ${result.falsification?`<div class="hypothesis-meta"><b>可证伪条件：</b>${esc(result.falsification)}</div>`:""}
        ${result.research_plan?.length?`<ul class="plan-list">${result.research_plan.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:""}
        <div class="report-actions">
          <button class="report-primary" onclick="loadFullReport()">查看完整科研报告</button>
          <button class="report-secondary" onclick="openReportPage()">打印 / 保存 PDF</button>
          <button class="report-secondary" onclick="downloadMarkdownReport()">下载 Markdown</button>
        </div>
      </div>
    </div>
  </div>`);
  const finalCard=$("#chatInner > .chat-row:last-child .final-card");
  animateIn(finalCard,{y:18,duration:.54});
  addAssistantMessage("当前结果已经形成正式结论，但研究仍然开放。你可以继续提出专家意见，系统会保留历史并重新审查受影响部分。");
  scrollBottom();
  loadHistory();
}

function handleEvent(e){
  switch(e.type){
    case "message": addAssistantMessage(e.text); break;
    case "progress":
      addSystemNote(`${e.label}完成${e.documents?` · 已检索 ${e.documents} 篇文献`:""}`);
      break;
    case "hypothesis":
      addHypothesisCard(e.hypothesis);
      addSystemNote("候选假设已生成 · 即将进入三重科学审查");
      break;
    case "review_started":
      enqueueReviewRender(()=>createReviewCard(e.round));
      break;
    case "audit_step":
      enqueueReviewRender(()=>addAuditStep(e));
      break;
    case "gate_update":
      enqueueReviewRender(()=>updateGate(e.gate,e.status,e.progress,e.issues,e.detail));
      break;
    case "review_failed":
      showReviewFailed(e);
      break;
    case "revision_started":
      addRevisionCard(e);
      break;
    case "feedback_received":
      addSystemNote(`人工意见已加入 · 重新审查：${(e.impacted_gates||[]).map(x=>GATE_META[x]?.name||x).join("、")}`);
      break;
    case "human_intervention_required":
      showHumanRequired(e);
      break;
    case "final_result":
      addFinalResult(e.result,!!e.after_feedback);
      break;
    case "stream_end":
      closeStream();
      break;
  }
}

function openStream(reason="start"){
  if(!currentResearchId) return;
  closeStream();
  currentEventSource=new EventSource(`/api/research/${currentResearchId}/stream?reason=${encodeURIComponent(reason)}`);
  currentEventSource.onmessage=ev=>{
    try{handleEvent(JSON.parse(ev.data))}catch(err){console.error(err)}
  };
  currentEventSource.onerror=()=>closeStream();
}

async function startResearch(question){
  if(!question || window.researchStarting) return;
  window.researchStarting=true;
  const buttons=[...document.querySelectorAll("#questionGrid button")];
  buttons.forEach(button=>{button.disabled=true;button.classList.add("is-loading");});
  try{
    closeQuestionModal();
    setWorkspaceMode(true);
    currentQuestion=question;
    finishTyping();
    reviewRenderQueue=[];
    reviewRenderBusy=false;
    $("#topQid").textContent=`#${question.id}`;
    $("#topTitle").textContent=question.title;
    $("#topCategory").textContent=question.category;
    $("#chatInner").innerHTML="";
    addUserMessage(`开始研究 Science125 #${question.id}：${question.title}`);
    setComposerEnabled(true,false);

    const data=await api("/api/research/start",{
      method:"POST",body:JSON.stringify({question_id:question.id})
    });
    currentResearchId=data.research_id;
    await loadHistory();
    openStream("start");
  }catch(error){
    setWorkspaceMode(false);
    setComposerEnabled(false,false);
    addSystemNote(`研究启动失败：${error.message||"请稍后重试"}`);
    openQuestionModal();
  }finally{
    window.researchStarting=false;
    buttons.forEach(button=>{button.disabled=false;button.classList.remove("is-loading");});
  }
}

async function sendFeedback(){
  const text=$("#expertInput").value.trim();
  if(!text||!currentResearchId) return;
  addUserMessage(text);
  $("#expertInput").value="";
  try{
    const res=await api(`/api/research/${currentResearchId}/feedback`,{
      method:"POST",body:JSON.stringify({message:text})
    });
    addSystemNote(`专家意见已提交 · 影响：${res.impacted_gates.map(x=>GATE_META[x]?.name||x).join("、")}`);
    setComposerEnabled(true,false);
    openStream("feedback");
    await loadHistory();
  }catch(err){
    addAssistantMessage("提交意见失败："+err.message);
  }
}

async function stopResearch(){
  if(!currentResearchId) return;
  await api(`/api/research/${currentResearchId}/stop`,{method:"POST"});
  closeStream();
  addSystemNote("研究已停止");
  setComposerEnabled(false,false);
  await loadHistory();
}

async function loadHistory(){
  try{
    const data=await api("/api/research");
    historyCache=data.items||[];
    renderHistory();
  }catch{
    $("#historyList").innerHTML=`<div class="history-empty">历史研究读取失败</div>`;
  }
}

function renderHistory(){
  const q=$("#historySearch").value.trim().toLowerCase();
  const rows=historyCache.filter(x=>`${x.question?.title||""} ${x.note||""}`.toLowerCase().includes(q));
  if(!rows.length){
    $("#historyList").innerHTML=`<div class="history-empty">没有匹配的历史研究</div>`;
    return;
  }
  $("#historyList").innerHTML=`<div class="date-label">SQLite 持久化研究记录</div>`+rows.map(r=>`
    <button class="history-item ${r.id===currentResearchId?"active":""}" data-id="${r.id}">
      <span class="dot ${r.status}"></span>
      <b>${esc(r.question.title)}</b>
      <small>${esc(r.note||r.stage)} · 第 ${r.round} 轮</small>
    </button>`).join("");
  $$(".history-item").forEach(btn=>btn.onclick=()=>loadResearch(btn.dataset.id));
}

async function loadResearch(id){
  closeStream();
  const r=await api(`/api/research/${id}`);
  currentResearchId=id;
  setWorkspaceMode(true);
  currentQuestion=r.question;
  finishTyping();
  reviewRenderQueue=[];
  reviewRenderBusy=false;
  $("#topQid").textContent=`#${r.question.id}`;
  $("#topTitle").textContent=r.question.title;
  $("#topCategory").textContent=r.question.category;
  $("#chatInner").innerHTML="";

  setComposerEnabled(r.status!=="stopped",r.status==="needs_human");
  addUserMessage(`查看历史研究：${r.question.title}`);

  if(r.hypothesis) addHypothesisCard(r.hypothesis);

  reviewCard=null;
  if(r.round){
    createReviewCard(r.round);
    ["debate","trace","causal"].forEach(g=>{
      const x=r.gates?.[g]||{status:"pending",progress:0};
      updateGate(g,x.status,x.progress,x.issues||[],x.detail||null);
    });
  }

  if(r.status==="needs_human"){
    showHumanRequired({
      round:r.round,
      failed_gates:Object.entries(r.gates||{}).filter(([_,v])=>v.status==="failed").map(([g])=>g),
      unresolved:Object.entries(r.gates||{}).flatMap(([g,v])=>(v.detail?.issues||[]).map(i=>({
        gate:g,gate_name:GATE_META[g]?.name||g,title:i.title,severity:i.severity,recommendation:i.recommendation
      }))),
      message:r.note
    });
  }else if(r.result){
    addFinalResult(r.result,!!r.result.human_feedback_applied);
  }else{
    addAssistantMessage(`当前研究状态：${r.note||r.stage}。`);
  }
  renderHistory();
}

async function loadQuestions(){
  const q=$("#questionSearch").value.trim();
  const cat=$("#questionCategory").value;
  const data=await api(`/api/questions?q=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}`);
  questionsCache=data.items||[];
  $("#questionCount").textContent=`找到 ${data.total} 个问题 · #27 可专门演示“自动 3 轮仍失败 → 人工介入”分支`;
  $("#questionGrid").innerHTML=questionsCache.slice(0,60).map(item=>`
  <article class="question-card">
    <div class="qno">#${item.id}</div>
    <h4>${esc(item.title)}</h4>
    <p>${esc(item.summary)}</p>
    <footer>
      <span>${esc(item.category)}</span>
      ${item.id===27?`<span class="demo-human">人工介入 Demo</span>`:""}
      <button data-id="${item.id}">开始研究 →</button>
    </footer>
  </article>`).join("");
  if(!$("#questionGrid").dataset.bound){
    $("#questionGrid").dataset.bound="true";
    $("#questionGrid").addEventListener("click",event=>{
      const button=event.target.closest("button[data-id]");
      if(!button) return;
      const q=questionsCache.find(x=>String(x.id)===String(button.dataset.id));
      if(q) startResearch(q);
    });
  }
  if(motionEnabled()){
    window.gsap.fromTo("#questionGrid .question-card",{autoAlpha:0,y:12},{autoAlpha:1,y:0,duration:.3,stagger:.025,ease:"power2.out",clearProps:"transform,opacity,visibility"});
  }
}

function openQuestionModal(){
  $("#questionModalBg").classList.add("open");
  $("#questionModal").classList.add("open");
  const modal=$("#questionModal");
  if(motionEnabled()){
    window.gsap.killTweensOf(modal);
    window.gsap.fromTo(modal,{autoAlpha:0,y:18},{autoAlpha:1,y:0,duration:.32,ease:"power3.out",clearProps:"transform,opacity,visibility"});
  }
  loadQuestions();
}
function closeQuestionModal(){
  const modal=$("#questionModal");
  if(window.gsap){
    window.gsap.killTweensOf(modal);
    window.gsap.set(modal,{clearProps:"transform,opacity,visibility"});
  }
  $("#questionModalBg").classList.remove("open");
  modal.classList.remove("open");
}

function renderCriterion(c){
  const cls=c.result==="通过"?"ok":c.result==="未通过"?"bad":"warn";
  return `<div class="criterion"><span class="criterion-result ${cls}">${esc(c.result)}</span><div><b>${esc(c.name)}</b><p>${esc(c.detail)}</p></div></div>`;
}

function openGateDrawer(gate,card){
  const el=card?.querySelector(`[data-gate="${gate}"]`);
  let detail=null;
  try{detail=el?.dataset.detail?JSON.parse(el.dataset.detail):null}catch{}
  $("#drawerTitle").textContent=(detail?.gate_name||GATE_META[gate].name)+"详情";

  if(!detail){
    $("#drawerContent").innerHTML=`<div class="issue"><b>暂无详细审查结果</b><p>该审查尚未返回结构化详情。</p></div>`;
  }else{
    $("#drawerContent").innerHTML=`
      <div class="review-verdict">
        <div><span>审查状态</span><b class="${detail.status}">${esc(detail.status_name)}</b></div>
        <div><span>审查评分</span><strong>${detail.score}/100</strong></div>
        <h3>${esc(detail.verdict)}</h3>
        <p>${esc(detail.summary)}</p>
      </div>

      <div class="drawer-section">
        <h4>审查标准</h4>
        ${(detail.criteria||[]).map(renderCriterion).join("")||"<p>暂无。</p>"}
      </div>

      <div class="drawer-section">
        <h4>发现的问题与修改建议</h4>
        ${(detail.issues||[]).length?(detail.issues||[]).map(i=>`
          <div class="deep-issue">
            <div class="deep-issue-head"><b>${esc(i.title)}</b><span class="severity ${i.severity==="高"?"high":i.severity==="中"?"mid":"low"}">${esc(i.severity)}</span></div>
            <p><strong>依据：</strong>${esc(i.evidence)}</p>
            <p><strong>建议：</strong>${esc(i.recommendation)}</p>
          </div>`).join(""):`<div class="pass-empty">✓ 当前没有阻断性问题</div>`}
      </div>

      <div class="drawer-section">
        <h4>审查证据</h4>
        ${(detail.evidence||[]).map(x=>`
          <div class="evidence-item"><b>${esc(x.source)}</b><p>${esc(x.detail)}</p></div>`).join("")||"<p>暂无。</p>"}
      </div>`;
  }

  $("#drawerBg").classList.add("open");
  $("#drawer").classList.add("open");
  if(motionEnabled()){
    const drawer=$("#drawer");
    window.gsap.killTweensOf(drawer);
    window.gsap.fromTo(drawer,{x:26,autoAlpha:0},{x:0,autoAlpha:1,duration:.34,ease:"power3.out",clearProps:"transform,opacity,visibility"});
    animateTextBlocks(drawer,{delay:.12,stagger:.028});
  }
}
function closeDrawer(){
  const drawer=$("#drawer");
  if(window.gsap){
    window.gsap.killTweensOf(drawer);
    window.gsap.set(drawer,{clearProps:"transform,opacity,visibility"});
  }
  $("#drawerBg").classList.remove("open");
  drawer.classList.remove("open");
}

function reportStatusText(status){
  return {
    completed: "\u5df2\u5b8c\u6210",
    running: "\u8fdb\u884c\u4e2d",
    needs_human: "\u9700\u8981\u4eba\u5de5\u4ecb\u5165",
    stopped: "\u5df2\u505c\u6b62",
  }[status] || status || "\u5df2\u5b8c\u6210";
}
function renderReportList(items){
  return (items||[]).length
    ? `<ul class="report-list">${items.map(item=>`<li>${esc(item)}</li>`).join("")}</ul>`
    : '<p class="report-empty">\u6682\u65e0\u8bb0\u5f55</p>';
}
function renderFullReport(report){
  const existing=$("#fullReportCard");
  if(existing) existing.remove();
  const question=report.question||{};
  const hypothesis=report.final_hypothesis||{};
  const metrics=report.metrics||{};
  const reviewSummary=Object.entries(report.review_summary||{}).map(([gate,summary])=>`
    <div><b>${esc(GATE_META[gate]?.name||gate)}</b><p>${esc(summary)}</p></div>`).join("");
  $("#chatInner").insertAdjacentHTML("beforeend",`
  <div class="chat-row report-row" id="fullReportCard">
    <div class="chat-avatar">AI</div>
    <div class="chat-content" style="max-width:100%">
      <div class="chat-name">AI Scientist \u00b7 Full Research Report</div>
      <article class="inline-report-card">
        <div class="inline-report-head">
          <div><span class="eyebrow">FULL RESEARCH REPORT</span><h3>${esc(report.report_title||"\u5b8c\u6574\u79d1\u7814\u62a5\u544a")}</h3><p>Science125 #${esc(question.id||"")} \u00b7 ${esc(question.title||"")}</p></div>
          <span class="report-status">${reportStatusText(report.status)}</span>
        </div>
        <section><h4>\u7814\u7a76\u95ee\u9898</h4><p>${esc(report.problem_background||"")}</p></section>
        <section><h4>\u6700\u7ec8\u79d1\u5b66\u5047\u8bbe</h4><h5>${esc(hypothesis.title||"")}</h5><p>${esc(hypothesis.summary||"")}</p></section>
        <section><h4>\u4e09\u91cd\u5ba1\u67e5\u7ed3\u8bba</h4><div class="report-review-grid">${reviewSummary||'<p class="report-empty">\u6682\u65e0\u5ba1\u67e5\u7ed3\u8bba</p>'}</div></section>
        <section><h4>\u7814\u7a76\u6307\u6807</h4><div class="inline-report-metrics"><div><span>\u53ef\u4fe1\u8bc4\u5206</span><b>${metrics.score??"\u2014"}/100</b></div><div><span>\u652f\u6301\u8bc1\u636e</span><b>${metrics.support_evidence??"\u2014"}</b></div><div><span>\u53cd\u5411\u8bc1\u636e</span><b>${metrics.counter_evidence??"\u2014"}</b></div><div><span>\u6709\u6548\u5f15\u7528</span><b>${metrics.citations??"\u2014"}</b></div></div></section>
        <section><h4>\u6700\u7ec8\u7efc\u5408\u7ed3\u8bba</h4><p>${esc(report.conclusion||"")}</p></section>
        <section><h4>\u53ef\u8bc1\u4f2a\u6761\u4ef6</h4><p>${esc(report.falsification||"")}</p></section>
        <section><h4>\u7814\u7a76\u5c40\u9650</h4>${renderReportList(report.limitations)}</section>
        <section><h4>\u540e\u7eed\u7814\u7a76\u8ba1\u5212</h4>${renderReportList(report.research_plan)}</section>
        <div class="inline-report-actions"><button class="report-secondary" onclick="openReportPage()">打印 / 保存 PDF</button><button class="report-secondary" onclick="downloadMarkdownReport()">\u4e0b\u8f7d Markdown</button><button class="report-secondary" onclick="this.closest('.report-row').remove()">\u6536\u8d77\u62a5\u544a</button></div>
      </article>
    </div>
  </div>`);
  animateIn($("#fullReportCard .inline-report-card"),{y:18,duration:.5});
  scrollBottom();
}
async function loadFullReport(){
  if(!currentResearchId) return;
  const button=document.querySelector(".report-primary");
  if(button){button.disabled=true;button.textContent="\u6b63\u5728\u52a0\u8f7d\u62a5\u544a\u2026";}
  try{
    const report=await api(`/api/research/${encodeURIComponent(currentResearchId)}/report`);
    renderFullReport(report);
  }catch(error){
    addAssistantMessage("\u5b8c\u6574\u79d1\u7814\u62a5\u544a\u52a0\u8f7d\u5931\u8d25\uff1a"+(error.message||"\u8bf7\u7a0d\u540e\u91cd\u8bd5"));
  }finally{
    if(button){button.disabled=false;button.textContent="\u67e5\u770b\u5b8c\u6574\u79d1\u7814\u62a5\u544a";}
  }
}

function openReportPage(){
  if(currentResearchId) window.open(`/report/${encodeURIComponent(currentResearchId)}`,"_blank");
}

function downloadMarkdownReport(){
  if(!currentResearchId) return;
  const link=document.createElement("a");
  link.href=`/api/research/${encodeURIComponent(currentResearchId)}/report.md`;
  link.download=`ai-scientist-report-${currentResearchId}.md`;
  link.hidden=true;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

$("#newResearchBtn").onclick=openQuestionModal;
$("#welcomeStart").onclick=openQuestionModal;
$("#closeQuestionModal").onclick=closeQuestionModal;
$("#questionModalBg").onclick=closeQuestionModal;
$("#questionSearch").addEventListener("input",()=>{clearTimeout(window._qs);window._qs=setTimeout(loadQuestions,180)});
$("#questionCategory").onchange=loadQuestions;
$("#historySearch").addEventListener("input",renderHistory);
$("#sendBtn").onclick=sendFeedback;
$("#expertInput").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendFeedback()}});
$("#stopBtn").onclick=stopResearch;
$("#closeDrawer").onclick=closeDrawer;
$("#drawerBg").onclick=closeDrawer;

(async function init(){
  setWorkspaceMode(false);
  animateShell();
  animateWelcome();
  try{
    const health=await api("/api/health");
    $("#apiStatus").innerHTML=`<i></i> ${health.storage==="sqlite"?"SQLite 已连接":"API 在线"}`;
  }catch{
    $("#apiStatus").textContent="API 离线";
  }
  await loadHistory();
})();
