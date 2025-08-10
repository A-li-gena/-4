function serializeForm(form){const data=new FormData(form);const obj={};for(const [k,v] of data.entries()){obj[k]=v}return obj}
class ApiClient{constructor(){this.baseURL='/api'}async request(url,opt={}){const r=await fetch(this.baseURL+url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}async get(url,params={}){const sp=new URLSearchParams(params);const u=sp.toString()?`${url}?${sp}`:url;return this.request(u)}async post(url,data){return this.request(url,{method:'POST',body:JSON.stringify(data)})}async patch(url,data){return this.request(url,{method:'PATCH',body:JSON.stringify(data)})}}
const api=new ApiClient();
function showModal(id){const m=document.getElementById(id);if(m){m.style.display='flex';document.body.style.overflow='hidden'}}
function hideModal(id){const m=document.getElementById(id);if(m){m.style.display='none';document.body.style.overflow=''}}
function showSuccess(msg){console.log(msg)}
function showError(msg){console.error(msg)}