/** Replace {key} placeholders with bidi-isolated (LTR) values — numbers and
 *  "3R" inside Persian sentences otherwise get reordered by the browser. */
export function fill(template, values) {
  return String(template).split(/(\{\w+\})/).map((part, i) => {
    const m = /^\{(\w+)\}$/.exec(part);
    return m && m[1] in values ? <bdi key={i} dir="ltr">{values[m[1]]}</bdi> : part;
  });
}
