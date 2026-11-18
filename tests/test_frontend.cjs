// Frontend regression checks, including the browser's unforgeable window.top.
// Run with Node.js: node tests/test_frontend.cjs
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(){
  const fields={};
  const element=selector=>fields[selector]??=(
    {hidden:['#shell','#demo-login','#toast'].includes(selector),value:'',textContent:'',innerHTML:'',className:'',
     querySelectorAll:()=>[],focus(){},setSelectionRange(){},close(){},showModal(){}});
  element('#username').value='organiser';element('#login').hidden=false;
  const memory=new Map(),calls=[];
  const fixture={mode:'offline',user:{id:'user1',username:'organiser',role:'organiser'},
    players:[{id:'p1',name:'Synthetic Player',archived:false,email:''}],tournaments:[],divisions:[],registrations:[],matches:[],legs:[],reviews:[],snapshots:[],drafts:[],audits:[],rankings:[]};
  const context={document:{querySelector:element},sessionStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
    setTimeout:()=>0,structuredClone,console,fetch:async(url,options)=>{
      calls.push({url,options});
      if(url==='/api/health')return {ok:true,json:async()=>({mode:'offline'})};
      if(url==='/api/login'){
        const body=JSON.parse(options.body);const ok=body.username==='organiser'&&body.password==='demo-organiser-26';
        return {ok,json:async()=>ok?{token:'test-session',user:fixture.user}:{error:'Invalid username or password'}};
      }
      if(url==='/api/state')return {ok:true,json:async()=>fixture};
      if(url==='/api/logout')return {ok:true,json:async()=>({signed_out:true})};
      throw Error('Unexpected frontend request '+url);
    }};
  Object.defineProperty(context,'top',{configurable:false,enumerable:true,get:()=>context});
  return {context,element,memory,calls};
}
(async()=>{
  const b=setup();vm.runInNewContext(source,b.context);await tick();
  assert.equal(typeof b.element('#login-form').onsubmit,'function','Login handler must load despite window.top');
  assert.equal(b.element('#password').value,'demo-organiser-26');
  assert.equal(b.element('#demo-login').hidden,false);
  let prevented=false;
  await b.element('#login-form').onsubmit({preventDefault(){prevented=true}});
  assert.ok(prevented);assert.equal(b.element('#shell').hidden,false);assert.equal(b.element('#login').hidden,true);
  assert.match(b.element('#main').innerHTML,/A clear view of every leg/);
  assert.equal(b.memory.get('steeltip-token'),'test-session');
  assert.equal(b.context.top,b.context,'Application must preserve the browser top property');
  assert.equal(b.context.refresh,undefined,'Application functions must remain scoped');
  await b.element('#logout').onclick();assert.equal(b.element('#login').hidden,false);assert.equal(b.memory.has('steeltip-token'),false);
  b.element('#password').value='incorrect';await b.element('#login-form').onsubmit({preventDefault(){}});
  assert.equal(b.element('#login-error').textContent,'Invalid username or password');assert.equal(b.element('#login').hidden,false);
  console.log('Frontend regression passed: window.top collision, login, dashboard, logout, and incorrect-password feedback.');
})().catch(e=>{console.error(e);process.exitCode=1});
