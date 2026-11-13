import * as React from "react";
import {Slot} from "@radix-ui/react-slot";
import {clsx} from "clsx";
import {twMerge} from "tailwind-merge";
export function Button({asChild=false,className,...props}:React.ButtonHTMLAttributes<HTMLButtonElement> & {asChild?:boolean}) {
const Component=asChild?Slot:"button";
return <Component className={twMerge(clsx("rounded-lg px-4 py-2 font-medium disabled:opacity-50",className))} {...props}/>;
}
