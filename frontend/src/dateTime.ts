function zonedParts(value: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value)
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((item) => item.type === type)?.value)
  return {
    year: part('year'),
    month: part('month'),
    day: part('day'),
    hour: part('hour'),
    minute: part('minute'),
    second: part('second'),
  }
}

export function dateInTimeZone(value: Date, timeZone: string) {
  const { year, month, day } = zonedParts(value, timeZone)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export function noonInTimeZone(date: string, timeZone: string) {
  const [year, month, day] = date.split('-').map(Number)
  const localNoon = Date.UTC(year, month - 1, day, 12)
  let instant = localNoon

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = zonedParts(new Date(instant), timeZone)
    const representedAsUtc = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
    )
    instant = localNoon - (representedAsUtc - instant)
  }

  return new Date(instant).toISOString()
}

export function todayInTimeZone(timeZone: string, now = new Date()) {
  return dateInTimeZone(now, timeZone)
}
