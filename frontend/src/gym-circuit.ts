type OrderedExercise = {order?: string};

/** An explicit, contiguous sequence A1, A2, ... represents an exercise circuit. */
export function circuitAt(exercises: OrderedExercise[], index: number): {start: number; end: number} | null {
  const label = (item?: OrderedExercise) => /^([A-Za-z])\s*([1-9]\d*)$/.exec((item?.order || "").trim());
  const current = label(exercises[index]);
  if (!current) return null;
  let start = index, end = index;
  while (start > 0 && label(exercises[start - 1])?.[1].toUpperCase() === current[1].toUpperCase()) start--;
  while (end + 1 < exercises.length && label(exercises[end + 1])?.[1].toUpperCase() === current[1].toUpperCase()) end++;
  return end > start && exercises.slice(start, end + 1).every((item, n) => Number(label(item)?.[2]) === n + 1) ? {start, end} : null;
}
