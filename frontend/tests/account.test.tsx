import React from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {it,expect,vi} from "vitest";
import Account from "../components/account";
it("registers an account and propagates its CSRF token",async()=>{
 const onSession=vi.fn();
 const api=vi.fn(async(path:string)=>{if(path==="auth/me")throw Error("anonymous");return {json:async()=>({user_id:"alice",csrf_token:"csrf-test"})} as Response});
 render(<Account api={api} onSession={onSession} records={[]} model="demo-logistic" threshold={.5} reviews={{}} onLoad={()=>{}}/>);
 fireEvent.change(screen.getByLabelText("Account email"),{target:{value:"alice@example.test"}});
 fireEvent.change(screen.getByLabelText("Account password"),{target:{value:"a-long-test-password"}});
 fireEvent.click(screen.getByText("Register"));
 await waitFor(()=>expect(onSession).toHaveBeenCalledWith("csrf-test"));
 expect(screen.getByText("Log out")).toBeDefined();
});
it("loads and deletes owned saved resources",async()=>{
 const onLoad=vi.fn();
 const api=vi.fn(async(path:string,options:any)=>({json:async()=>path==="auth/me"?{user_id:"a",csrf_token:"c"}:path==="workspace/resources"?[{id:"item",kind:"dataset",name:"Example"}]:{payload:{records:[{amount:7}]}}}) as Response);
 render(<Account api={api} onSession={()=>{}} records={[]} model="demo-logistic" threshold={.5} reviews={{}} onLoad={onLoad}/>);
 await waitFor(()=>expect(screen.getByText("Open")).toBeDefined());
 fireEvent.click(screen.getByText("Open"));
 await waitFor(()=>expect(onLoad).toHaveBeenCalledWith({records:[{amount:7}]}));
 fireEvent.click(screen.getByText("Delete"));
 await waitFor(()=>expect(api).toHaveBeenCalledWith("workspace/resources/item",{method:"DELETE"}));
});
