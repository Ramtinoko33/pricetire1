import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-lg border border-input bg-card px-3 py-1 text-base text-foreground transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground hover:border-foreground/50 focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25 aria-[invalid=true]:border-danger disabled:cursor-not-allowed disabled:opacity-55 md:text-sm",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Input.displayName = "Input"

export { Input }
