# Sales Action Panel — Visual Click Dummy

Standalone HTML preview of the **Sales Action Panel** SPA (Frappe CRM–style three-column layout).

## Open locally

```bash
cd phamos/public/sales_action_panel_mockup
python3 -m http.server 8765
# then open http://127.0.0.1:8765/
```

Query helpers:

- `?view=opportunities` — open a CRM view
- `?dialog=1` — open the Start Work dialog
- `?settings=1` — open Sales Action Panel Settings

## Desk SPA

The production desk page lives at `/app/sales-action-panel` and mounts the Vue bundle under `phamos/public/js/sales_action_panel/`.
