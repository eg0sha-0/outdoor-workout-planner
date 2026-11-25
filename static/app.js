const $ = id => document.getElementById(id);
const form = $("form");
const statuses = {planned:"Запланирована", done:"Выполнена", cancelled:"Отменена"};
const stamp = t => t.slice(0,16).replace("T"," ");
async function api(path, method="GET", body) {
  const res = await fetch("/api/"+path, {method,headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const data = await res.json();
  if (!res.ok) throw Error(typeof data.detail === "string" ? data.detail : "Проверьте значения полей");
  return data;
}
function report(error){ $("notice").textContent = error.message; }
function add(parent, tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}
function action(parent, label, run){
  const button = add(parent,"button",label);
  button.onclick = async () => {
    button.disabled = true;
    try { $("notice").textContent=""; await run(); } catch(e){report(e);} finally {button.disabled=false;}
  };
}
async function refresh(){
  const rows = await api("workouts");
  const list = $("list");
  list.replaceChildren();
  for(const row of rows.filter(r=>!$("filter").value || r.starts.startsWith($("filter").value))){
    const card = add(list,"article","");
    const path = "workouts/"+row.id;
    add(card,"h3",row.sport+" · "+row.city);
    add(card,"p",stamp(row.starts)+" МСК · "+row.minutes+" мин · "+statuses[row.status]);
    const details = add(card,"div","");
    if(row.status==="planned"){
      action(card,"Прогноз",async()=>{
        const f = await api(path+"/forecast");
        details.replaceChildren();
        f.hours.forEach(([t,r,w],i)=>add(details,"p",String(Number(row.starts.slice(11,13))+i).padStart(2,"0")+":00 · "+t+" °C · осадки "+r+"% · ветер "+w+" км/ч"));
        if(f.suggestion) action(details,"Перенести на "+stamp(f.suggestion),async()=>{
          await api(path+"/move","POST",{previous:row.starts,replacement:f.suggestion}); await refresh();
        });
        else add(details,"p",!f.hours.length?"Нет полного прогноза":f.suitable?"Погода подходит":"Подходящего окна сегодня нет");
      });
      for(const [value,label] of [["done","Завершить"],["cancelled","Отменить"]]){
        action(card,label,async()=>{await api(path+"/status?value="+value,"PUT");await refresh();});
      }
    }
    action(card,"История переносов",async()=>{
      const moves=await api(path+"/history"); details.replaceChildren();
      if(!moves.length)add(details,"p","Переносов пока нет");
      for(const m of moves)add(details,"p",stamp(m.previous)+" → "+stamp(m.replacement));
    });
  }
  if(!list.children.length)add(list,"p","На выбранные даты тренировок пока нет.");
}
form.onsubmit=async e=>{
  e.preventDefault();const button=form.querySelector("button");button.disabled=true;
  try{
    await api("workouts","POST",Object.fromEntries(new FormData(form)));
    $("filter").value="";await refresh();$("notice").textContent="Тренировка добавлена";
  }catch(e){report(e);}finally{button.disabled=false;}
};
$("filter").onchange=()=>refresh().catch(report);
$("all").onclick=()=>{$("filter").value="";refresh().catch(report);};
async function init(){
  const {cities,today}=await api("session");
  cities.forEach(c=>add(form.elements.city,"option",c));
  form.elements.starts.min=today+"T00:00";
  await refresh();
}
init().catch(report);
