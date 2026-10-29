// Design System v1.0 Applied
// Anti-Slop Rules Applied
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface OptionSelectProps {
  id: string
  label: string
  value: string
  options: string[]
  disabled: boolean
  onChange: (value: string) => void
}

export function OptionSelect({ id, label, value, options, disabled, onChange }: OptionSelectProps) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
