import React from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {describe,it,expect,vi} from "vitest";
import {filtered} from "../lib/risk";
import Home from "../app/page";
vi.mock("recharts",()=>({ResponsiveContainer:()=>null,BarChart:()=>null,Bar:()=>null,XAxis:()=>null,YAxis:()=>null,Tooltip:()=>null,CartesianGrid:()=>null}));
describe("analyst workflow",()=>{
it("filters IDs and risk together",()=>{
expect(filtered([{transaction_id:"12",risk_category:"high"},{transaction_id:"13",risk_category:"low"}],"1","high")).toHaveLength(1);
});
it("renders dashboard, changes threshold and accepts file upload",async()=>{
vi.stubGlobal("fetch",vi.fn(async(path:string)=>({ok:true,json:async()=>path.endsWith("models")?[]:path.includes("demo/")?{records:[]}:{rows:1,duplicates:0,columns:["amount"],missing:{},records:[{amount:3}]}})));
render(<Home/>);
expect(screen.getByText("See the risk. Focus your review.")).toBeDefined();
fireEvent.change(screen.getByLabelText("Review threshold"),{target:{value:".7"}});
expect(screen.getByText("0.70")).toBeDefined();
fireEvent.click(screen.getByText("Upload dataset"));
fireEvent.change(screen.getByLabelText("Upload CSV"),{target:{files:[new File(["amount\n3"],"data.csv",{type:"text/csv"})]}});
await waitFor(()=>expect(screen.getByText("1 rows · 0 duplicate rows")).toBeDefined());
fireEvent.change(screen.getByLabelText("Map amount"),{target:{value:"total"}});
fireEvent.click(screen.getByText("Apply column mapping"));
expect(screen.getByLabelText("Map total")).toBeDefined();
});
it("shows backend errors instead of invented demo data",async()=>{
vi.stubGlobal("fetch",vi.fn(async()=>({ok:false,json:async()=>({detail:"Backend unavailable"})})));
render(<Home/>);
await waitFor(()=>expect(screen.getByRole("alert").textContent).toContain("Backend unavailable"));
});
});
