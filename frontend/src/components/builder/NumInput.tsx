import { useState, useEffect } from 'react'

interface Props {
  value: number | null
  onChange: (v: number | null) => void
  step?: number
  min?: number
  max?: number
  placeholder?: string
  allowNull?: boolean
  className?: string
}

export default function NumInput({
  value,
  onChange,
  step = 1,
  min,
  max,
  placeholder,
  allowNull = false,
  className = '',
}: Props) {
  const [raw, setRaw] = useState<string>(value === null ? '' : String(value))

  useEffect(() => {
    setRaw(value === null ? '' : String(value))
  }, [value])

  return (
    <input
      type="number"
      step={step}
      min={min}
      max={max}
      value={raw}
      placeholder={placeholder}
      onChange={(e) => {
        setRaw(e.target.value)
        if (e.target.value === '') {
          if (allowNull) onChange(null)
          return
        }
        const n = Number(e.target.value)
        if (!Number.isNaN(n)) onChange(n)
      }}
      className={
        'border border-ink-200 rounded-md px-2 py-1 text-sm w-24 tabular-nums ' + className
      }
    />
  )
}
