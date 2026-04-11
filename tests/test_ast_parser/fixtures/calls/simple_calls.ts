// Two top-level functions, one calling the other.

export function callee(): number {
  return 1;
}

export function caller(): number {
  return callee() + 1;
}
