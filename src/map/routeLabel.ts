// Display-only names for routes. The stable data id (e.g. "rt-orbital-guess-v1") stays the key
// everywhere; this only changes what people read.

export function routeLabel(id: string): string {
  // Purpose: turn a route `id` such as "rt-orbital-guess-v1" into "orbital guess v1"
  // (drop the "rt-" prefix, replace dashes with spaces). Never used as a lookup key.
  return id.replace(/^rt-/, '').replace(/-/g, ' ');
}
