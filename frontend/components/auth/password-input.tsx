"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState, type ComponentProps } from "react";

import { inputClass } from "@/components/ui";

/** A password field with a reveal toggle. The toggle's name avoids the word "password" so the
 * field stays the only control labelled that way. */
export function PasswordInput(props: ComponentProps<"input">) {
  const [shown, setShown] = useState(false);
  return (
    <span className="relative block">
      <input {...props} type={shown ? "text" : "password"} className={`${inputClass} pr-11`} />
      <button
        type="button"
        onClick={() => setShown(!shown)}
        aria-label={shown ? "Hide characters" : "Show characters"}
        aria-pressed={shown}
        className="absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-fg-3 hover:bg-sunken hover:text-fg"
      >
        {shown ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </span>
  );
}
