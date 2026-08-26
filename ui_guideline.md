# UI Guidelines — Resend-Inspired Dark Style

Design system for building UI in the style of resend.com: minimal, dark, high-contrast, with subtle radial glows and 3D icon accents.

---

## 1. Color Palette

```css
:root {
  /* Backgrounds */
  --bg-base:        #000000;   /* page background */
  --bg-elevated:    #0a0a0a;   /* sections */
  --bg-card:        #0f0f10;   /* cards, empty states */
  --bg-input:       #1a1a1a;   /* inputs, selects, pills */
  --bg-hover:       #1f1f1f;   /* hover state on dark surfaces */

  /* Borders */
  --border-subtle:  rgba(255, 255, 255, 0.06);
  --border-default: rgba(255, 255, 255, 0.08);
  --border-strong:  rgba(255, 255, 255, 0.12);

  /* Text */
  --text-primary:   #ededed;   /* headings, key text */
  --text-secondary: #a1a1a1;   /* body, descriptions */
  --text-muted:     #6b6b6b;   /* placeholders, disabled */

  /* Accents (used sparingly) */
  --accent-white:   #ffffff;   /* primary CTA bg */
  --accent-black:   #000000;   /* primary CTA text */
  --accent-green:   #22c55e;   /* success / active status */
  --accent-red:     #ef4444;   /* error / destructive */

  /* Glow (for card centers) */
  --glow-soft:      rgba(255, 255, 255, 0.05);
  --glow-strong:    rgba(255, 255, 255, 0.08);
}
```

**Rule:** never use saturated brand colors as backgrounds. Color is reserved for status dots and small accents only.

---

## 2. Typography

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11'; /* Inter alternates */
  -webkit-font-smoothing: antialiased;
}

/* Headings: tight tracking, semi-bold to bold */
h1 { font-size: 48px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; }
h2 { font-size: 32px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.2; }
h3 { font-size: 24px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.3; }
h4 { font-size: 18px; font-weight: 600; letter-spacing: -0.015em; }

/* Body */
p, span { font-size: 14px; font-weight: 400; line-height: 1.6; color: var(--text-secondary); }
small  { font-size: 12px; color: var(--text-muted); }
```

**Rule:** large headings always have negative letter-spacing. This is the single most important typographic detail of the style.

---

## 3. Spacing & Radius

```css
:root {
  --radius-sm: 6px;    /* badges, small pills */
  --radius-md: 8px;    /* buttons, inputs */
  --radius-lg: 12px;   /* small cards */
  --radius-xl: 16px;   /* main cards, empty states */
  --radius-2xl: 20px;  /* large containers */

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;
}
```

Cards are generously padded (`32–48px` internal). Empty states get `80–120px` vertical padding.

---

## 4. Core Components

### 4.1 Button — Primary (inverted)

```css
.btn-primary {
  background: var(--accent-white);
  color: var(--accent-black);
  font-weight: 600;
  font-size: 14px;
  padding: 10px 16px;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: opacity 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.btn-primary:hover { opacity: 0.9; }
```

### 4.2 Button — Secondary

```css
.btn-secondary {
  background: var(--bg-input);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  font-weight: 500;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s ease;
}
.btn-secondary:hover { background: var(--bg-hover); }
```

### 4.3 Input / Select

```css
.input, .select {
  background: var(--bg-input);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s ease;
}
.input::placeholder { color: var(--text-muted); }
.input:focus, .select:focus { border-color: var(--border-strong); }
```

### 4.4 Tabs (pill style)

```css
.tabs { display: inline-flex; gap: 4px; }
.tab {
  padding: 6px 14px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
}
.tab.active {
  background: var(--bg-input);
  color: var(--text-primary);
}
```

### 4.5 Card

```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: 32px;
}
```

### 4.6 Empty-State Card (the signature pattern)

```css
.empty-state {
  background: var(--bg-card);
  background-image: radial-gradient(
    circle at 50% 35%,
    var(--glow-strong) 0%,
    transparent 60%
  );
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: 100px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  text-align: center;
}
.empty-state img { width: 80px; height: 80px; border-radius: 18px; }
.empty-state h3 { color: var(--text-primary); margin: 8px 0 0; }
.empty-state p  { color: var(--text-secondary); max-width: 360px; margin: 0; }
```

### 4.7 Status Dot

```css
.status { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; }
.status::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
}
.status.success::before { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); }
.status.error::before   { background: var(--accent-red);   box-shadow: 0 0 8px var(--accent-red); }
```

### 4.8 Table

```css
.table { width: 100%; border-collapse: collapse; }
.table thead {
  background: var(--bg-input);
  border-radius: var(--radius-lg);
}
.table th {
  text-align: left;
  font-weight: 500;
  font-size: 14px;
  color: var(--text-secondary);
  padding: 12px 16px;
}
.table td {
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
  font-size: 14px;
}
.table tr:hover td { background: rgba(255, 255, 255, 0.02); }
```

---

## 5. Icons 
- Inline icons: use Lucide (https://lucide.dev), `1.5px` stroke, `16–20px` size, color `var(--text-secondary)`.


---

## 7. Layout Patterns

### Page header

```html
<header style="margin-bottom: 32px;">
  <h1>Emails</h1>
</header>
```

### Toolbar (tabs + filters + search)

```html
<div class="toolbar" style="display:flex; justify-content:space-between; margin-bottom:24px;">
  <div class="tabs">
    <button class="tab active">Sending</button>
    <button class="tab">Receiving</button>
  </div>
  <div style="display:flex; gap:12px;">
    <input class="input" placeholder="Search...">
    <select class="select"><option>Last 15 days</option></select>
  </div>
</div>
```

### Page container

```css
.page { max-width: 1200px; margin: 0 auto; padding: 32px 40px; }
```

---

## 8. Reference Snippet — Full Empty State

```html
<div class="empty-state">
  <img src="/icons/email-3d.png" alt="">
  <h3>No sent emails yet</h3>
  <p>Start sending emails to see insights and previews for every message.</p>
  <button class="btn-primary">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
      <polyline points="15 3 21 3 21 9"/>
      <line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
    Go to docs
  </button>
</div>
```

---

## 9. Do / Don't

**Do:**
- Use pure `#000` as the page background
- Use radial gradients inside cards for depth
- Keep borders barely visible (`rgba(255,255,255,0.08)`)
- Use negative letter-spacing on headings
- Use white-on-black for primary CTAs

**Don't:**
- Use gray (`#1a1a1a`, `#222`) as the page background — must be pure black
- Add box-shadows for elevation — use border + radial gradient instead
- Use saturated colors for primary buttons or large surfaces
- Use rounded-pill (`border-radius: 9999px`) for buttons — stick to `8px`
- Use serif fonts or condensed sans-serifs

---

## 10. Checklist Before Shipping a Component

- [ ] Background is `#000` or `var(--bg-card)`
- [ ] Border uses `var(--border-default)`
- [ ] Headings have negative letter-spacing
- [ ] Body text uses `var(--text-secondary)`, not pure white
- [ ] Border-radius is from the scale (no arbitrary values)
- [ ] Primary CTA is white-on-black
- [ ] No drop shadows; depth comes from radial gradients
- [ ] Transitions are ≤ 300ms with ease-out