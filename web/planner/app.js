const DAY_NAMES = ["SEG", "TER", "QUA", "QUI", "SEX"];
const TAGS = { Arte: "#ffc400", Duplo: "#12c8b0", GTO: "#f5008d", Konica: "#8b67c5", SM: "#00a9e0", Pessoal: "#efefef" };
const STORE_KEY = "m87-planner-web-v1";
const PAIRING_KEY = "m87-planner-pairing-key";
const emptyTask = () => ({ id: crypto.randomUUID(), client:"", text:"", notes:"", done:false, tag:"", updatedAt:Date.now() });
const blankLines = (count = 32) => Array.from({ length:count }, emptyTask);
const startOfWeek = (value = new Date()) => { const d = new Date(value); d.setHours(12,0,0,0); d.setDate(d.getDate() - ((d.getDay()+6)%7)); return d; };
const keyOf = (d) => startOfWeek(d).toISOString().slice(0,10);
const addDays = (d, n) => { const next=new Date(d); next.setDate(next.getDate()+n); return next; };
const week = (date) => ({ start:keyOf(date), priorities:blankLines(4), days:Object.fromEntries(DAY_NAMES.map((day)=>[day,blankLines()])), notes:"" });

class LocalAdapter {
  load() { try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {version:1,weeks:{},approvals:[]}; } catch { return {version:1,weeks:{},approvals:[]}; } }
  save(data) { localStorage.setItem(STORE_KEY, JSON.stringify(data)); }
}

class RemoteAdapter {
  constructor(endpoint) { this.endpoint=endpoint; this.pending=null; this.timer=null; }
  headers() { return {"X-M87-Workspace-Key":localStorage.getItem(PAIRING_KEY) || ""}; }
  async pull() {
    const response=await fetch(this.endpoint, {headers:this.headers()});
    if (!response.ok) { const error=new Error(`sync ${response.status}`); error.status=response.status; throw error; }
    return response.json();
  }
  queue(data) {
    clearTimeout(this.timer);
    this.pending=structuredClone(data);
    this.timer=setTimeout(()=>this.push(), 500);
  }
  async push() {
    if (!this.pending) return;
    const payload=this.pending; this.pending=null;
    try {
      const response=await fetch(this.endpoint, {method:"PUT",headers:{"Content-Type":"application/json",...this.headers()},body:JSON.stringify(payload)});
      if (!response.ok) throw new Error(`sync ${response.status}`);
    } catch (error) { this.pending=payload; console.warn("M87 Planner offline; sync will retry on the next change.", error); }
  }
}

class Planner {
  constructor() { this.adapter=new LocalAdapter(); this.data=this.adapter.load(); this.sync=location.hostname.endsWith(".workers.dev") ? new RemoteAdapter("/api/planner") : null; this.current=startOfWeek(); this.dragged=null; this.selectedTag=""; this.editing=null; this.ensureWeek(); this.bindDialog(); this.bindPairing(); this.render(); this.pullRemote(); }
  async pullRemote() { if (!this.sync) return; try { const remote=await this.sync.pull(); if (remote?.weeks && remote?.approvals) { this.data=remote; this.adapter.save(this.data); this.ensureWeek(); this.render(); } } catch (error) { if (error.status===401) this.openPairing(); else console.warn("M87 Planner iniciou offline.", error); } }
  ensureWeek() { const k=keyOf(this.current); if (!this.data.weeks[k]) this.data.weeks[k]=week(this.current); const current=this.data.weeks[k]; for (const day of DAY_NAMES) { current.days[day] ||= []; while (current.days[day].length<32) current.days[day].push(emptyTask()); } return current; }
  save() { this.adapter.save(this.data); this.sync?.queue?.(this.data); }
  currentWeek() { return this.ensureWeek(); }
  render() { const current=this.currentWeek(); const root=document.querySelector("#app"); root.innerHTML=`<section class="planner"><div class="bar">M87 - TO DO</div><div class="head"><div class="planner-title">PLANNER SEMANAL ${this.current.getFullYear()}</div><div class="week-nav"><button data-week="-1" aria-label="Semana anterior">‹</button><button data-week="0">HOJE</button><button data-week="1" aria-label="Próxima semana">›</button></div><select class="date-picker" aria-label="Data"><option>${this.dateText(this.current)}</option></select><button class="active">CANETA</button><button>BORRACHA</button></div><div class="todo">${current.priorities.map((task,i)=>this.todoRow(task,i)).join("")}</div><section class="days">${DAY_NAMES.map((name,index)=>this.dayColumn(name,index)).join("")}</section><section class="bottom"><section class="panel"><div class="calendar">${[0,1].map(offset=>this.month(addDays(this.current,offset*31))).join("")}</div></section><section class="panel"><div class="panel-title">AGUARDANDO</div><div class="approvals" data-zone="approvals">${this.data.approvals.map(task=>this.taskRow(task,"approvals")).join("")}</div></section><section class="panel"><div class="panel-title">NOTAS DA SEMANA</div><textarea class="notes" placeholder="Notas da semana">${this.escape(current.notes || "")}</textarea></section></section></section>`; this.bindPage(); }
  dateText(date) { return date.toLocaleDateString("pt-BR",{day:"2-digit",month:"2-digit",year:"numeric"}); }
  todoRow(task,index) { return `<label class="todo-row"><input class="check" type="checkbox" data-priority-check="${index}" ${task.done?"checked":""}><input data-priority="${index}" value="${this.escape(task.text)}"></label>`; }
  dayColumn(day,index) { const date=addDays(this.current,index); const items=this.currentWeek().days[day]; return `<section class="day" data-zone="${day}"><div class="day-head">${day} · ${String(date.getDate()).padStart(2,"0")}<span>⌄</span></div><div class="tasks" data-zone="${day}">${items.map(task=>this.taskRow(task,day)).join("")}</div></section>`; }
  taskRow(task,zone) { if (!this.hasContent(task)) return `<div class="empty-line" data-create="${zone}"></div>`; const color=TAGS[task.tag]||"#777"; const complete=task.done?"done":""; const next=zone==="SEX"?" friday-action":""; return `<article class="task ${complete}" draggable="true" data-id="${task.id}" data-zone="${zone}" style="--tag:${color}"><input class="check" type="checkbox" ${task.done?"checked":""} aria-label="Concluir"><div class="task-content">${task.client?`<span class="task-client">${this.escape(task.client)}</span>${task.text?" - ":""}`:""}${this.escape(task.text)}</div><button class="delete" aria-label="Excluir">×</button><button class="next-monday${next}" aria-label="Mover para segunda">→</button></article>`; }
  hasContent(task) { return Boolean(task.client?.trim() || task.text?.trim()); }
  month(date) { const first=new Date(date.getFullYear(),date.getMonth(),1); const last=new Date(date.getFullYear(),date.getMonth()+1,0); const start=(first.getDay()+6)%7; const cells=["S","T","Q","Q","S","S","D"].map(x=>`<span class="weekday">${x}</span>`); for(let i=0;i<start;i++)cells.push("<span></span>"); const activeStart=this.current; const activeEnd=addDays(this.current,6); for(let day=1;day<=last.getDate();day++){const value=new Date(date.getFullYear(),date.getMonth(),day); const active=value>=activeStart&&value<=activeEnd; cells.push(`<span class="${active?"active":""}">${String(day).padStart(2,"0")}</span>`);} const title=date.toLocaleDateString("pt-BR",{month:"long",year:"numeric"}).toUpperCase(); return `<div class="month"><h3>${title}</h3><div class="month-grid">${cells.join("")}</div></div>`; }
  bindPage() { const root=document.querySelector("#app"); root.querySelectorAll("[data-week]").forEach(button=>button.addEventListener("click",()=>{const offset=Number(button.dataset.week); this.current=offset ? addDays(this.current,offset*7) : startOfWeek(); this.ensureWeek(); this.save(); this.render();})); root.querySelector(".notes").addEventListener("input",(e)=>{this.currentWeek().notes=e.target.value; this.save();}); root.querySelectorAll("[data-priority]").forEach(input=>input.addEventListener("input",()=>{const task=this.currentWeek().priorities[input.dataset.priority]; task.text=input.value; task.updatedAt=Date.now(); this.save();})); root.querySelectorAll("[data-priority-check]").forEach(check=>check.addEventListener("change",()=>{this.currentWeek().priorities[check.dataset.priority].done=check.checked; this.save();})); root.querySelectorAll("[data-create]").forEach(line=>line.addEventListener("dblclick",()=>this.openTask(null,line.dataset.create))); root.querySelectorAll(".task").forEach(item=>this.bindTask(item)); root.querySelectorAll("[data-zone]").forEach(zone=>this.bindDropZone(zone)); }
  bindTask(element) { element.addEventListener("dragstart",()=>{this.dragged=element; element.classList.add("dragging");}); element.addEventListener("dragend",()=>{this.dragged=null; document.querySelectorAll(".drop-before").forEach(x=>x.classList.remove("drop-before")); element.classList.remove("dragging");}); element.addEventListener("dragover",(event)=>{event.preventDefault(); element.classList.add("drop-before");}); element.addEventListener("dragleave",()=>element.classList.remove("drop-before")); element.addEventListener("dblclick",(event)=>{if(!event.target.matches("button,input")) this.openTask(element.dataset.id,element.dataset.zone);}); element.querySelector("input").addEventListener("change",(event)=>{const task=this.findTask(element.dataset.id); task.done=event.target.checked; task.updatedAt=Date.now(); this.save(); this.render();}); element.querySelector(".delete").addEventListener("click",()=>this.removeTask(element.dataset.id)); element.querySelector(".next-monday").addEventListener("click",()=>this.moveToNextMonday(element.dataset.id)); }
  bindDropZone(zone) { zone.addEventListener("dragover",(event)=>event.preventDefault()); zone.addEventListener("drop",(event)=>{event.preventDefault(); if(!this.dragged)return; const target=event.target.closest(".task"); this.moveTask(this.dragged.dataset.id,zone.dataset.zone,target?.dataset.id);}); }
  findTask(id) { for (const w of Object.values(this.data.weeks)) for(const tasks of Object.values(w.days)) { const found=tasks.find(x=>x.id===id); if(found)return found; } return this.data.approvals.find(x=>x.id===id); }
  removeFromSource(id) { for (const w of Object.values(this.data.weeks)) for(const tasks of Object.values(w.days)) { const i=tasks.findIndex(x=>x.id===id); if(i>=0)return tasks.splice(i,1)[0]; } const i=this.data.approvals.findIndex(x=>x.id===id); return i>=0?this.data.approvals.splice(i,1)[0]:null; }
  moveTask(id,target,anchor) { const task=this.removeFromSource(id); if(!task)return; task.updatedAt=Date.now(); const list=target==="approvals"?this.data.approvals:this.currentWeek().days[target]; const index=anchor?list.findIndex(x=>x.id===anchor):-1; if(index>=0) list.splice(index,0,task); else { const blank=list.findIndex(x=>!this.hasContent(x)); blank>=0?list.splice(blank,0,task):list.push(task); } this.save(); this.render(); }
  moveToNextMonday(id) { const task=this.removeFromSource(id); if(!task)return; const monday=addDays(this.current,7); this.current=startOfWeek(monday); const list=this.currentWeek().days.SEG; const blank=list.findIndex(x=>!this.hasContent(x)); list.splice(blank>=0?blank:list.length,0,task); this.save(); this.render(); }
  openTask(id,zone) { this.editing={id,zone}; const task=id?this.findTask(id):emptyTask(); this.editTask=task; document.querySelector("#task-client").value=task.client||""; document.querySelector("#task-text").value=task.text||""; document.querySelector("#task-notes").value=task.notes||""; this.selectedTag=task.tag||""; this.renderTags(); document.querySelector("#task-dialog").showModal(); document.querySelector("#task-client").focus(); }
  bindDialog() { const dialog=document.querySelector("#task-dialog"); dialog.querySelectorAll("[data-close]").forEach(button=>button.addEventListener("click",()=>dialog.close())); dialog.querySelector("#task-form").addEventListener("submit",(event)=>{event.preventDefault();this.saveTask(false);}); dialog.querySelector("#task-done").addEventListener("click",()=>this.saveTask(true)); }
  bindPairing() { const dialog=document.querySelector("#pairing-dialog"); dialog.querySelector("#pairing-form").addEventListener("submit",(event)=>{event.preventDefault(); const key=document.querySelector("#pairing-key").value.trim(); if (!key) return; localStorage.setItem(PAIRING_KEY,key); dialog.close(); this.pullRemote();}); }
  openPairing() { const dialog=document.querySelector("#pairing-dialog"); if (!dialog.open) { dialog.showModal(); document.querySelector("#pairing-key").focus(); } }
  renderTags() { const root=document.querySelector("#task-tags"); root.innerHTML=Object.entries(TAGS).map(([name,color])=>`<button type="button" class="tag-option ${name===this.selectedTag?"selected":""}" style="--tag:${color}" data-tag="${name}">${name.toUpperCase()}</button>`).join(""); root.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{this.selectedTag=button.dataset.tag;this.renderTags();})); }
  saveTask(done) { const task=this.editTask; task.client=document.querySelector("#task-client").value.trim(); task.text=document.querySelector("#task-text").value.trim(); task.notes=document.querySelector("#task-notes").value.trim(); task.tag=this.selectedTag; task.done=done||task.done; task.updatedAt=Date.now(); if(!this.hasContent(task))return; if(!this.editing.id){const list=this.editing.zone==="approvals"?this.data.approvals:this.currentWeek().days[this.editing.zone];const blank=list.findIndex(x=>!this.hasContent(x)); blank>=0?list.splice(blank,1,task):list.push(task);} this.save(); document.querySelector("#task-dialog").close(); this.render(); }
  escape(value="") { const node=document.createElement("span"); node.textContent=value; return node.innerHTML; }
}

const planner=new Planner();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("./service-worker.js");
window.m87Planner=planner;
