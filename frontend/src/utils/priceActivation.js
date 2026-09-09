import api from '@/api'

// localStorage key for the last IST date on which we triggered activation.
const STORAGE_KEY = 'lastPriceActivationDate'

// Today's date in Asia/Kolkata (IST) as YYYY-MM-DD. Independent of the
// browser's timezone so the dedup works whether the user is in India or not.
function istToday() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}

/**
 * Trigger backend price activation for the day — but only the first time it's
 * called per IST date. Subsequent calls on the same day are a no-op.
 *
 * Returns { skipped: true } when the day already activated client-side, or
 * { activated: N, skipped: false } from the backend on the first call.
 */
export async function triggerDailyPriceActivation(queryClient) {
  const today = istToday()
  const last = localStorage.getItem(STORAGE_KEY)
  if (last === today) return { skipped: true }

  try {
    const { data } = await api.post('/api/v1/price-history/activate-due')
    localStorage.setItem(STORAGE_KEY, today)

    // If any prices were activated, invalidate product caches so list / form
    // screens pull fresh b2b/b2c/mrp values.
    if (queryClient && data?.activated > 0) {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['product-search-billing'] })
      queryClient.invalidateQueries({ queryKey: ['price-history'] })
    }
    return { ...data, skipped: false }
  } catch (e) {
    // Non-blocking — failures shouldn't prevent the user from working.
    return { error: true, skipped: false }
  }
}
