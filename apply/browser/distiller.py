"""Compact Accessibility-Tree / Interactive DOM distiller for Playwright pages."""

from __future__ import annotations

from typing import Protocol, cast

from apply.models import DistilledElement, DistilledPage, ElementRole

DISTILLER_JS = """
() => {
  const nodes = [];
  let counter = 1;
  const selector = [
    'input:not([type="hidden"])',
    'textarea',
    'select',
    'button',
    '[role="button"]',
    '[role="combobox"]',
    '[role="radiogroup"]'
  ].join(',');

  const getLabel = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const ref = document.getElementById(labelledBy);
      if (ref && ref.innerText) return ref.innerText.trim();
    }
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl && lbl.innerText) return lbl.innerText.trim();
    }
    const parentLabel = el.closest('label');
    if (parentLabel && parentLabel.innerText) return parentLabel.innerText.trim();
    return (el.getAttribute('placeholder') || el.innerText || el.name || '').trim();
  };

  for (const el of document.querySelectorAll(selector)) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    const uid = `e${counter++}`;
    el.setAttribute('data-apply-uid', uid);

    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const roleAttr = (el.getAttribute('role') || '').toLowerCase();
    let role = 'textbox';
    if (tag === 'button' || roleAttr === 'button' || type === 'submit') role = 'button';
    else if (tag === 'textarea') role = 'textarea';
    else if (tag === 'select') role = 'select';
    else if (roleAttr === 'combobox') role = 'typeahead_select';
    else if (roleAttr === 'radiogroup') role = 'radio_group';
    else if (type === 'checkbox') role = 'checkbox';
    else if (type === 'file') role = 'file_input';

    const options = [];
    if (tag === 'select') {
      for (const opt of el.querySelectorAll('option')) {
        if (opt.textContent && opt.textContent.trim()) options.push(opt.textContent.trim());
      }
    }

    nodes.push({
      uid,
      role,
      label: getLabel(el).slice(0, 200),
      required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
      current_value: type === 'checkbox' ? Boolean(el.checked) : (el.value || null),
      options: options.slice(0, 50),
      accept: el.getAttribute('accept') || ''
    });
  }
  return nodes;
}
"""


class EvaluablePage(Protocol):
    url: str

    def evaluate(self, expression: str) -> object: ...


def normalize_raw_elements(raw: list[dict[str, object]]) -> list[DistilledElement]:
    """Normalize raw DOM dicts into strictly typed DistilledElement entries."""
    allowed_roles: set[str] = {
        "textbox",
        "textarea",
        "select",
        "typeahead_select",
        "radio_group",
        "checkbox",
        "file_input",
        "button",
    }
    elements: list[DistilledElement] = []
    for item in raw:
        role_str = str(item.get("role") or "textbox")
        role: ElementRole = cast(ElementRole, role_str if role_str in allowed_roles else "textbox")
        cur = item.get("current_value")
        cur_val: str | bool | None = (
            cur if isinstance(cur, (str, bool)) else (str(cur) if cur is not None else None)
        )
        el: DistilledElement = {
            "uid": str(item.get("uid") or ""),
            "role": role,
            "label": str(item.get("label") or ""),
            "required": bool(item.get("required", False)),
            "current_value": cur_val,
        }
        opts = item.get("options")
        if isinstance(opts, list) and opts:
            el["options"] = [str(o) for o in cast(list[object], opts)]
        accept = str(item.get("accept") or "")
        if accept:
            el["accept"] = accept
        elements.append(el)
    return elements


def distill_page(page: EvaluablePage, detected_step: str = "unknown") -> DistilledPage:
    """Evaluate DISTILLER_JS on a Playwright page and return a DistilledPage."""
    raw = cast(list[dict[str, object]], page.evaluate(DISTILLER_JS))
    return {
        "page_url": page.url,
        "detected_step": detected_step,
        "elements": normalize_raw_elements(raw),
    }
