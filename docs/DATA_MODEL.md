# Serviceflow — Data Model

## Entity relationship (conceptual)

```
Organization (tenant)
 ├─< User            (staff + portal accounts)
 ├─< Customer        (companies you do repairs for)
 │     ├─< Contact   (people at that customer)
 │     └─< Equipment (assets owned by the customer)
 ├─< Equipment       (motor / valve / pump / actuator / blower …)
 │     └─< WorkOrder (repair jobs performed on this asset over time)
 └─< WorkOrder
        ├─< WorkOrderEvent   (status-change timeline)
        ├─< Finding          (inspection notes / defects)
        ├─< Quote
        │     └─< QuoteLine  (labor + parts line items)
        ├─< TimeEntry        (technician labor logging)
        └─< Attachment       (photos, reports, nameplate pics)
```

## Key entities

### Organization
The tenant. `name`, `slug`, `plan`, timestamps. Everything else hangs off it.

### User
`email`, `hashed_password`, `full_name`, `role`
(`owner|manager|service_writer|technician|customer`), `organization_id`,
optional `customer_id` (set only for portal users). `is_active`.

### Customer
A company the shop serves. `name`, `account_number`, `billing/shipping address`,
`phone`, `email`. Has many Contacts and Equipment.

### Equipment (Asset)
The physical thing being repaired — the reason Serviceflow is asset-centric.
`tag` (shop asset tag), `equipment_type`
(`motor|valve|actuator|pump|blower|gearbox|other`), `manufacturer`, `model`,
`serial_number`, `nameplate_data` (JSON: HP, RPM, voltage, frame, valve size,
torque rating, etc.), `location`, `customer_id`. Has many WorkOrders → permanent
service history.

### WorkOrder (Repair Job) — the core entity
`number` (human ID, e.g. `WO-2026-0042`), `customer_id`, `equipment_id`,
`service_type` (`shop_repair | field_service`), `priority`
(`low|normal|high|rush`), `status`, `title`, `problem_description`,
`assigned_to` (technician user), `scheduled_at` (field service),
`promised_date`, timestamps, `total_estimate`, `total_actual`.

#### Status workflow (state machine)

```
 intake ─▶ inspection ─▶ quote_pending ─▶ approved ─▶ in_repair
   │            │             │              │            │
   │            │             ▼              │            ▼
   │            │        quote_rejected      │        testing ─▶ ready ─▶ shipped ─▶ closed
   └────────────┴──────────▶ on_hold ◀───────┴────────────┘
                                │
                             cancelled
```

Every transition writes a `WorkOrderEvent` so both staff and the customer see a
full, timestamped history.

### WorkOrderEvent
`work_order_id`, `event_type` (`status_change | note | quote_sent | quote_decision
| assignment | field_visit`), `from_status`, `to_status`, `message`,
`created_by`, `visible_to_customer` (bool), `created_at`. This table powers the
timeline in both the staff app and the portal.

### Finding
Inspection results. `work_order_id`, `title`, `detail`, `severity`
(`info|minor|major|critical`), `created_by`.

### Quote / QuoteLine
`Quote`: `work_order_id`, `number`, `status`
(`draft|sent|approved|rejected|expired`), `subtotal`, `tax`, `total`,
`valid_until`, `approved_by`, `decided_at`.
`QuoteLine`: `quote_id`, `kind` (`labor|part|misc`), `description`, `quantity`,
`unit_price`, `line_total`.

### TimeEntry
`work_order_id`, `user_id` (technician), `hours`, `note`, `worked_on`.

### Attachment
`work_order_id`, `filename`, `content_type`, `url`, `kind`
(`photo|report|nameplate|document`), `uploaded_by`. (Storage interface stubbed
for MVP; metadata modeled now.)

## Indexing & integrity

- All tenant tables carry `organization_id` (indexed) for tenant isolation.
- `WorkOrder.number` and `Customer.account_number` are unique per organization.
- Foreign keys enforce referential integrity; soft-delete via `is_active` where
  history must be preserved (Users, Customers, Equipment).

## Customer-portal scoping

Portal users (`role = customer`, with a `customer_id`) can read only:
`Customer` = their own; `Equipment` where `customer_id` = theirs;
`WorkOrder` where `customer_id` = theirs; and `WorkOrderEvent` where
`visible_to_customer = true`. They can act only on: **quote approval/rejection**
for their own work orders.
