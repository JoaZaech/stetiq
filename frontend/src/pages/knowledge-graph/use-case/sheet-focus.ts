/**
 * A sheet's `onOpenAutoFocus`: focus the sheet, not its first control (Edit): for a reader,
 * that would open its "Needs edit access" tooltip.
 */
export function focusSheetItself(event: Event) {
  event.preventDefault()
  ;(event.currentTarget as HTMLElement).focus()
}
