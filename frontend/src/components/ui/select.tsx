import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown, ChevronUp } from 'lucide-react'
import * as React from 'react'

import { cn } from '~/lib/utils'

const Select = SelectPrimitive.Root

const SelectGroup = SelectPrimitive.Group

const SelectValue = SelectPrimitive.Value

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      'flex h-8 w-full min-w-0 items-center justify-between gap-1 rounded-md border border-neutral-200 bg-white px-2 text-left text-xs text-neutral-900 shadow-sm outline-none transition-[color,box-shadow] focus-visible:border-neutral-400 focus-visible:ring-2 focus-visible:ring-neutral-400/30 disabled:cursor-not-allowed disabled:opacity-50 data-[placeholder]:text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:data-[placeholder]:text-neutral-400 [&>span]:line-clamp-1',
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="size-3.5 shrink-0 opacity-60" aria-hidden />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
))
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName

const SelectScrollUpButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollUpButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollUpButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpButton
    ref={ref}
    className={cn(
      'flex cursor-default items-center justify-center py-1 text-neutral-500 dark:text-neutral-400',
      className,
    )}
    {...props}
  >
    <ChevronUp className="size-3.5" />
  </SelectPrimitive.ScrollUpButton>
))
SelectScrollUpButton.displayName = SelectPrimitive.ScrollUpButton.displayName

const SelectScrollDownButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollDownButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollDownButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownButton
    ref={ref}
    className={cn(
      'flex cursor-default items-center justify-center py-1 text-neutral-500 dark:text-neutral-400',
      className,
    )}
    {...props}
  >
    <ChevronDown className="size-3.5" />
  </SelectPrimitive.ScrollDownButton>
))
SelectScrollDownButton.displayName = SelectPrimitive.ScrollDownButton.displayName

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = 'popper', ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      className={cn(
        'relative z-50 max-h-56 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border border-neutral-200 bg-white text-neutral-900 shadow-md dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100',
        position === 'popper' &&
          'data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1',
        className,
      )}
      position={position}
      {...props}
    >
      <SelectScrollUpButton />
      <SelectPrimitive.Viewport
        className={cn(
          'max-h-52 overflow-y-auto p-1',
          position === 'popper' && 'w-full min-w-[var(--radix-select-trigger-width)]',
        )}
      >
        {children}
      </SelectPrimitive.Viewport>
      <SelectScrollDownButton />
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
))
SelectContent.displayName = SelectPrimitive.Content.displayName

const SelectLabel = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Label
    ref={ref}
    className={cn('px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--muted)]', className)}
    {...props}
  />
))
SelectLabel.displayName = SelectPrimitive.Label.displayName

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item> & {
    /** Renders after the label; use for actions on disabled rows (stopPropagation in handlers). */
    itemSuffix?: React.ReactNode
  }
>(({ className, children, itemSuffix, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      'relative flex h-8 w-full cursor-default select-none items-center rounded-sm py-0 pl-7 pr-2 text-xs leading-tight outline-none focus:bg-neutral-100 focus:text-neutral-900 data-[disabled]:pointer-events-none data-[disabled]:opacity-40 dark:focus:bg-neutral-800 dark:focus:text-neutral-100',
      Boolean(itemSuffix) &&
        'group data-[disabled]:pointer-events-auto data-[disabled]:opacity-100',
      className,
    )}
    {...props}
  >
    <span className="absolute left-2 top-1/2 flex size-3.5 -translate-y-1/2 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="size-3.5" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText asChild>
      <span className="flex min-h-0 min-w-0 flex-1 items-center truncate group-data-[disabled]:opacity-50">
        {children}
      </span>
    </SelectPrimitive.ItemText>
    {itemSuffix != null ? (
      <span
        className="flex shrink-0 items-center justify-center pl-1"
        onMouseDown={(e) => e.preventDefault()}
      >
        {itemSuffix}
      </span>
    ) : null}
  </SelectPrimitive.Item>
))
SelectItem.displayName = SelectPrimitive.Item.displayName

const SelectSeparator = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Separator
    ref={ref}
    className={cn('-mx-1 my-1 h-px bg-neutral-200 dark:bg-neutral-800', className)}
    {...props}
  />
))
SelectSeparator.displayName = SelectPrimitive.Separator.displayName

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
}
