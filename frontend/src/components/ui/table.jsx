import * as React from "react"

import { cn } from "@/lib/utils"

// Em ecrãs < 768 px (stack=true), cada linha passa a cartão: as células mostram o título da
// coluna como rótulo (data-label, lido do cabeçalho) e deixa de haver scroll horizontal.
const Table = React.forwardRef(({ className, stack = true, ...props }, ref) => {
  const innerRef = React.useRef(null)
  const setRefs = React.useCallback((node) => {
    innerRef.current = node
    if (typeof ref === "function") ref(node)
    else if (ref) ref.current = node
  }, [ref])

  React.useLayoutEffect(() => {
    const table = innerRef.current
    if (!table || !stack) return undefined
    const label = () => {
      const heads = [...table.querySelectorAll(":scope > thead > tr:first-child > th")]
        .map((th) => th.textContent.trim())
      table.querySelectorAll(":scope > tbody > tr").forEach((tr) => {
        [...tr.children].forEach((td, i) => {
          const l = heads[i] || ""
          if (td.getAttribute("data-label") !== l) td.setAttribute("data-label", l)
        })
      })
    }
    label()
    // Só childList/characterData: escrever atributos não volta a disparar o observador.
    const mo = new MutationObserver(label)
    mo.observe(table, { childList: true, subtree: true, characterData: true })
    return () => mo.disconnect()
  }, [stack])

  return (
    <div className="relative w-full overflow-auto">
      <table
        ref={setRefs}
        data-stack={stack ? "true" : undefined}
        className={cn("w-full caption-bottom text-sm", className)}
        {...props} />
    </div>
  )
})
Table.displayName = "Table"

const TableHeader = React.forwardRef(({ className, ...props }, ref) => (
  <thead ref={ref} className={cn("[&_tr]:border-b [&_tr:hover]:bg-transparent", className)} {...props} />
))
TableHeader.displayName = "TableHeader"

const TableBody = React.forwardRef(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0", className)}
    {...props} />
))
TableBody.displayName = "TableBody"

const TableFooter = React.forwardRef(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn("border-t bg-muted/50 font-medium [&>tr]:last:border-b-0", className)}
    {...props} />
))
TableFooter.displayName = "TableFooter"

const TableRow = React.forwardRef(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b transition-colors hover:bg-accent/60 data-[state=selected]:bg-accent",
      className
    )}
    {...props} />
))
TableRow.displayName = "TableRow"

const TableHead = React.forwardRef(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn(
      "h-10 bg-muted/70 px-3 text-left align-middle text-xs font-semibold text-muted-foreground whitespace-nowrap first:pl-4 last:pr-4 [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
      className
    )}
    {...props} />
))
TableHead.displayName = "TableHead"

const TableCell = React.forwardRef(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn(
      "px-3 py-2.5 align-middle first:pl-4 last:pr-4 [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
      className
    )}
    {...props} />
))
TableCell.displayName = "TableCell"

const TableCaption = React.forwardRef(({ className, ...props }, ref) => (
  <caption
    ref={ref}
    className={cn("mt-4 text-sm text-muted-foreground", className)}
    {...props} />
))
TableCaption.displayName = "TableCaption"

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
