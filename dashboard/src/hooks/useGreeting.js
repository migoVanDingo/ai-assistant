const greetings = {
  morning: ['Good morning.', 'Morning briefing is ready.', 'Start sharp.'],
  afternoon: ['Good afternoon.', 'Midday brief is ready.', 'Here is the state of play.'],
  evening: ['Good evening.', 'Evening review is ready.', 'Here is the latest rundown.'],
  night: ['Still up.', 'Late shift briefing.', 'Night watch is ready.'],
}

export function useGreeting() {
  const now = new Date()
  const hour = now.getHours()
  let bucket = 'night'
  if (hour >= 5 && hour < 12) bucket = 'morning'
  else if (hour >= 12 && hour < 17) bucket = 'afternoon'
  else if (hour >= 17 && hour < 22) bucket = 'evening'

  const list = greetings[bucket]
  const index = (now.getDate() + hour) % list.length
  return list[index]
}
