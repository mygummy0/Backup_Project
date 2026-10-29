// Design System v1.0 Applied
// Anti-Slop Rules Applied
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { COPY } from "@/lib/copy"

interface FolderFieldProps {
  id: string
  label: string
  value: string
  invalid: boolean
  disabled: boolean
  onChange: (value: string) => void
  onPick: () => void
}

export function FolderField({ id, label, value, invalid, disabled, onChange, onPick }: FolderFieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      <div className="flex gap-2">
        <Input
          id={id}
          value={value}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby="form-error"
          onChange={(event) => onChange(event.target.value)}
        />
        <Button type="button" variant="outline" disabled={disabled} onClick={onPick}>
          {COPY.pick}
        </Button>
      </div>
    </div>
  )
}
