// One request per context. Polls must never invalidate a slow manual analysis.
// An old context may finish, but cannot publish or release a newer request.
export function createRequestGate() {
  let generation = 0;
  let active = null;
  return {
    begin() {
      if (active !== null) return null;
      active = ++generation;
      return active;
    },
    current(id) { return id !== null && active === id && generation === id; },
    finish(id) { if (active === id) active = null; },
    invalidate() { generation++; active = null; },
  };
}