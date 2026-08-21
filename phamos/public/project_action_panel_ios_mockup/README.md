# Project Action Panel — iOS Click Dummy

Standalone HTML preview of the **Project Action Panel** desk page, laid out as an iOS app.

This is a click dummy only (sample data, no ERPNext API). It mirrors the desk flows: start / pause / resume / stop timesheets, assign projects, hours stats, My Calendar, and Team Calendar.

## Open locally

```bash
cd phamos/public/project_action_panel_ios_mockup
python3 -m http.server 8766
# then open http://127.0.0.1:8766/
```

On a phone or in Safari responsive mode, the iPhone chrome is hidden and the dummy goes full screen.

Query helpers:

- `?tab=calendar` — My Calendar
- `?tab=team` — Team Calendar
- `?filter=all` — All Projects
- `?sheet=start` — open Start Timesheet
- `?sheet=stop` — open Stop Timesheet
- `?sheet=info` — feature map vs. the desk page

## Desk page

The production desk page lives at `/app/project-action-panel`.
