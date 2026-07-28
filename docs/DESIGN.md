# Serviceflow — UI/UX & Wireframes

## Design principles

1. **Operational density, not decoration.** Service-center staff live in this
   app all day. Screens are information-dense, scannable, and fast — tables,
   status pills, and KPIs over hero imagery.
2. **Status is the universal language.** A consistent color-coded status system
   runs through every screen (dashboard, lists, detail, portal) so anyone can
   read a job at a glance.
3. **Two audiences, one system.** Staff get a powerful operational console; the
   customer portal is calm, guided, and reassuring. Both share one design
   system so the brand feels coherent.
4. **The asset is the hero.** Equipment (motor/valve/actuator/pump) carries its
   nameplate and history everywhere it appears.

## Design system (`assets/css/design-system.css`)

- **Palette:** industrial steel blues (`--brand-*`) with a signal amber accent
  (`--accent-*`) reserved for attention/rush.
- **Status colors:** every `WorkOrderStatus` has a dedicated token and `.status`
  pill class.
- **Type scale, spacing, radius, shadows** are all tokenized as CSS variables so
  the look is consistent and themeable.
- **Components:** buttons, cards, KPI stat tiles, badges/pills, data tables,
  forms, timeline, app shell (sidebar + topbar), modal, toast.

## Screen map

```
Marketing (index.html)
  └─ Sign in (login.html)  ──►  role-based redirect
       ├─ Staff App (/app/)                    ├─ Customer Portal (/portal/)
       │   • Dashboard (KPIs, pipeline, recent) │   • My Repairs (active + history,
       │   • Work Orders (filterable list)      │     progress trackers)
       │   • Work Order detail                  │   • Repair detail (progress bar,
       │     - problem, findings, quotes        │     quote approval, timeline,
       │     - equipment nameplate, customer    │     equipment)
       │     - timeline, status actions         │   • My Equipment (assets +
       │   • Field Service (field-type jobs)    │     repair counts)
       │   • Customers / Equipment
```

## Key flows (wireframe intent)

### 1. Intake → Ship (staff)
`+ New Work Order` modal (customer → equipment → problem → type/priority) →
work order detail → **Advance status** stepper enforces the state machine →
add findings → build & send quote → after approval, move through repair /
testing / ready / shipped. Every action writes to the timeline.

### 2. Quote approval (customer)
Customer opens their repair → a highlighted **"Action needed"** card shows the
itemized quote and totals → **Approve** (authorizes repair, advances the WO to
`approved`) or **Decline** → decision is timestamped on the timeline and
reflected instantly in the staff app.

### 3. Live status (customer)
An 8-step progress tracker (Received → Inspection → Quote → Approved → Repair →
Testing → Ready → Shipped) plus a plain-language timeline — designed to remove
"what's the status of my motor?" phone calls.

## Responsive behavior

The app shell collapses the sidebar into a top nav under 860px; grids reflow to
a single column; tables scroll horizontally inside their container. The portal
is fully usable on a phone (customers often check status on mobile).

## Accessibility notes

Semantic HTML, labelled form fields, sufficient contrast on status pills, focus
rings on inputs, and non-color status text (pills always carry a label, never
color alone).

## Screenshots

See `docs/screenshots/` for captured views of the dashboard, work-order detail,
equipment, and the customer portal (status tracker + quote approval).
