
const $=s=>document.querySelector(s);
function esc(v=""){return String(v).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}
function researchId(){
  const parts=location.pathname.split("/").filter(Boolean);
  return parts[parts.length-1];
}
async function getReport(){
  const id=researchId();
  const res=await fetch(`/api/research/${encodeURIComponent(id)}/report`);
  if(!res.ok) throw new Error("报告读取失败");
  return res.json();
}
function list(items){
  return items?.length?`<ul>${items.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:"<p>暂无。</p>";
}
function render(r){
  const q=r.question,h=r.final_hypothesis,m=r.metrics;
  document.title=`AI Scientist 报告 · ${q.title}`;
  $("#paper").innerHTML=`
    <div class="cover">
      <div class="brand">AI SCIENTIST · FINAL RESEARCH REPORT</div>
      <h1>最终科研报告</h1>
      <div class="subtitle">Science125 #${q.id} · ${esc(q.title)}</div>
      <div class="meta">
        <div><span>研究领域</span><b>${esc(q.category||"—")}</b></div>
        <div><span>三重审查轮次</span><b>${r.review_rounds}</b></div>
        <div><span>报告生成时间</span><b>${esc(r.generated_at.replace("T"," "))}</b></div>
      </div>
    </div>

    <section>
      <div class="section-no">01 · RESEARCH QUESTION</div>
      <h2>研究问题与背景</h2>
      <h3>${esc(q.title)}</h3>
      <p>${esc(r.problem_background||"")}</p>
    </section>

    <section>
      <div class="section-no">02 · FINAL HYPOTHESIS</div>
      <h2>最终科学假设</h2>
      <blockquote><strong>${esc(h.title||"")}</strong><br>${esc(h.summary||"")}</blockquote>
      <div class="conclusion">
        <b>FINAL CONCLUSION · 最终综合结论</b>
        <p>${esc(r.conclusion||"")}</p>
      </div>
    </section>

    <section>
      <div class="section-no">03 · TRI-GATE REVIEW</div>
      <h2>三重科学审查结论</h2>
      <div class="gates">
        <div class="gate"><strong>⚖ 思辨审查</strong><p>${esc(r.review_summary.debate||"")}</p></div>
        <div class="gate"><strong>⌕ 溯源审查</strong><p>${esc(r.review_summary.trace||"")}</p></div>
        <div class="gate"><strong>⌘ 因果审查</strong><p>${esc(r.review_summary.causal||"")}</p></div>
      </div>
      <div class="metrics">
        <div><span>综合评分</span><b>${m.score??"—"}/100</b></div>
        <div><span>支持证据</span><b>${m.support_evidence??"—"}</b></div>
        <div><span>反向证据</span><b>${m.counter_evidence??"—"}</b></div>
        <div><span>有效引用</span><b>${m.citations??"—"}</b></div>
        <div><span>审查轮次</span><b>${r.review_rounds}</b></div>
      </div>
    </section>

    <section>
      <div class="section-no">04 · FALSIFIABILITY</div>
      <h2>可证伪条件</h2>
      <p>${esc(r.falsification||"暂无")}</p>
    </section>

    <section>
      <div class="section-no">05 · LIMITATIONS</div>
      <h2>研究局限</h2>
      ${list(r.limitations)}
    </section>

    <section>
      <div class="section-no">06 · NEXT STUDY</div>
      <h2>后续研究计划</h2>
      ${list(r.research_plan)}
    </section>

    <section>
      <div class="section-no">07 · HUMAN IN THE LOOP</div>
      <h2>人工专家介入记录</h2>
      ${r.human_feedback?.length
        ? r.human_feedback.map(f=>`<div class="feedback"><time>${esc(f.time||"")}</time><b>${esc(f.message)}</b><small>影响审查：${esc((f.impacted_gates||[]).join("、"))}</small></div>`).join("")
        : "<p>本次研究无人工专家介入记录。</p>"}
    </section>

    <div class="footer-note">
      AI Scientist Mock Report · 正式版本应由真实模型、真实文献与实际统计验证结果生成。
    </div>
  `;
}
(async()=>{
  try{render(await getReport())}catch(e){$("#paper").innerHTML=`<div class="loading">${esc(e.message)}</div>`}
})();
$("#printReport").onclick=()=>window.print();
function downloadMarkdown(){
  const id=researchId();
  const link=document.createElement("a");
  link.href=`/api/research/${encodeURIComponent(id)}/report.md`;
  link.download=`ai-scientist-report-${id}.md`;
  link.hidden=true;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
$("#downloadMd").onclick=downloadMarkdown;
