/**
 * Example function. Replace it with your own code.
 */
export function greet(name: string): string {
  const trimmed = name.trim();
  if (trimmed.length === 0) {
    throw new Error("name must not be empty");
  }
  return `Hello, ${trimmed}!`;
}
