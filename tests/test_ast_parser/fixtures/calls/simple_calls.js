// Two top-level functions, one calling the other.

export function callee() {
  return 1;
}

export function caller() {
  return callee() + 1;
}
