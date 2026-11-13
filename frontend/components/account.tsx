"use client";
import {useEffect,useState} from "react";
import {Button} from "./ui/button";
type Props={api:(path:string,options?:RequestInit)=>Promise<Response>;onSession:(csrf:string)=>void;records:unknown[];model:string;threshold:number;reviews:Record<string,string>;onLoad:(payload:any)=>void};
export default function Account({api,onSession,records,model,threshold,reviews,onLoad}:Props){
 const [email,setEmail]=useState(""),[password,setPassword]=useState(""),[resetToken,setResetToken]=useState("");
 const [user,setUser]=useState<any>(null),[saved,setSaved]=useState<any[]>([]),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
 const [name,setName]=useState("My analysis");
 async function load(){
 try{const me=await(await api("auth/me")).json();setUser(me);onSession(me.csrf_token);setSaved(await(await api("workspace/resources")).json());}catch{setUser(null);}
 }
 useEffect(()=>{load()},[]);
 async function action(path:string,body:any){
 setBusy(true);setMessage("");
 try{const data=await(await api(path,{method:"POST",body:JSON.stringify(body)})).json();if(data.csrf_token)onSession(data.csrf_token);if(data.user_id)setUser(data);setMessage(data.message||"Completed.");}
 catch(e){setMessage(String(e))}finally{setBusy(false)}
 }
 async function save(kind:string){
 try{await api("workspace/resources",{method:"POST",body:JSON.stringify({kind,name,payload:{records,model_id:model,threshold,reviews}})});await load();setMessage("Saved privately.");}catch(e){setMessage(String(e))}
 }
 return <section className="panel"><h3>Account workspace</h3><p>Your saved data and models are visible only to your account. Do not save sensitive cardholder information.</p>
 <div role="status">{message}</div>
 {!user?<><form onSubmit={e=>{e.preventDefault();action("auth/login",{email,password})}}>
 <label>Email <input aria-label="Account email" type="email" required value={email} onChange={e=>setEmail(e.target.value)} autoComplete="username"/></label>
 <label>Password (12+ characters) <input aria-label="Account password" type="password" required minLength={12} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></label>
 <Button disabled={busy} type="submit">Log in</Button><Button disabled={busy} type="button" onClick={()=>action("auth/register",{email,password})}>Register</Button></form>
 <details><summary>Forgot or reset password</summary><p>Delivery requires administrator-configured SMTP. No reset tokens are exposed in the browser or logs.</p>
 <Button onClick={()=>action("auth/forgot-password",{email})}>Request reset email</Button>
 <label>Reset token <input value={resetToken} onChange={e=>setResetToken(e.target.value)}/></label>
 <Button onClick={()=>action("auth/reset-password",{token:resetToken,password})}>Reset password using entered password</Button></details></>:
 <><p>Signed in {user.email||user.user_id}</p><Button onClick={async()=>{try{await api("auth/logout",{method:"POST"});setUser(null);onSession("");setSaved([]);}catch(e){setMessage(String(e))}}}>Log out</Button>
 <label>Saved item name <input value={name} onChange={e=>setName(e.target.value)} maxLength={100}/></label>
 {["dataset","investigation","report"].map(kind=><Button key={kind} disabled={!records.length} onClick={()=>save(kind)}>Save {kind}</Button>)}
 <Button onClick={load}>Refresh workspace</Button>
 <h3>Saved datasets, investigations and reports</h3>
 {saved.length?saved.map(item=><div className="contribution" key={item.id}><span>{item.kind}: {item.name}</span>
 <Button onClick={async()=>{try{const row=await(await api("workspace/resources/"+item.id)).json();onLoad(row.payload)}catch(e){setMessage(String(e))}}}>Open</Button>
 <Button onClick={async()=>{try{await api("workspace/resources/"+item.id,{method:"DELETE"});await load()}catch(e){setMessage(String(e))}}}>Delete</Button></div>):<p>No saved items. Trained models appear in the scoring model selector.</p>}
 <details><summary>Delete account and all saved data</summary><p>This permanently deletes your datasets, models, investigations, reports and sessions.</p>
 <Button onClick={async()=>{if(!window.confirm("Permanently delete your account and all saved data?"))return;try{await api("auth/account",{method:"DELETE"});setUser(null);setSaved([]);onSession("");setMessage("Account deleted.")}catch(e){setMessage(String(e))}}}>Permanently delete account</Button></details>
 </>}
 </section>
}
