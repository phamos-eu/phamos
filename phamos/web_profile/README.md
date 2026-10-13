# Web Profiles: public website sections

Design decisions: phamos/phamos#1492 (foundation) and the section issues #1487, #1493–#1497.

## Page inventory and routes

| Section | Doctype | Mirrors | EN | DE |
|---|---|---|---|---|
| People | Person Web Profile | Employee, or Contact of a Customer / Supplier / Sales Partner | `/en/people` | `/de/personen` |
| Departments | Department Web Profile | Department | `/en/departments` | `/de/abteilungen` |
| Teams | Team Web Profile | Team | `/en/teams` | `/de/teams` |
| Modules | Module Web Profile | Implementation Module (+ Workspace icon) | `/en/modules` | `/de/module` |
| Implementations | Implementation Web Profile | Implementation (+ Customer industry) | `/en/implementations` | `/de/implementierungen` |
| Industries | Industry Web Profile | Industry Type | `/en/industries` | `/de/branchen` |
| Customers | Stakeholder Web Profile (type Customer) | Customer / Supplier / Sales Partner | `/en/customers` | `/de/kunden` |
| Partners | Stakeholder Web Profile (type Partner) | Customer / Supplier / Sales Partner | `/en/partners` | `/de/partner` |

Each section has a listing (`/<lang>/<slug>`) and a profile per record (`/<lang>/<slug>/<route>`).
The record's route is the same in both languages. German is the default language (x-default).
Old URLs of the current site are redirected with *Website Route Redirect* records when a section
goes live, not in code. Routes are generated in `hooks.py` (`_WEB_PROFILE_SLUGS`); keep them in sync
with `sections.py`.

Every record gets one URL when it is created and keeps it for good; it never exposes personal or
confidential data (#1512): people get a random code (`p-7k3fq`), customers and partners a neutral
slug (`handel-dach`), implementations industry + start year (`fertigung-2023`). Switching between
named and anonymous changes only what the page shows, never its URL. Unpublished pages are not found.

## How it fits together

- `sections.py`: section registry (slugs, filters, sorts) and loaders that turn published records into display items. **Anonymisation happens here**: anonymous people, stakeholders and implementations never get a name, photo or named URL.
- `listing.py`: URL-driven filtering (OR within a filter, AND across, min/max sliders for numbers), full-text search over everything a detail page shows, option counts, sorting, pagination.
- `page.py`: language switch, canonical, hreflang, Open Graph, JSON-LD.
- `i18n.py`: languages and the text rows ("Web Profile Content", one row per language) with fallback to German.
- `contact.py`: the one contact workflow behind every contact button (shared dialog). phamos people and page-level requests become Lead/Customer + Opportunity (assigned to the phamos person if they have a user); consenting external people get the request forwarded by email, recorded on their profile.
- `chrome.py` (#1502): runs on every website page (`update_website_context`). Sets the page language (Web Profile route or the Web Page "Language" field), swaps navbar/footer links kept in Website Settings with German URLs to the page language, fills the footer groups "Module"/"Branchen" with the published profiles, and builds the DIN 5008 company footer (`templates/includes/footer/footer_info.html`; IBAN masked, no tax number).
- `setup.py`: Web Page custom fields "Language" and "Translation Of" (`after_migrate`). Translate a Web Page by creating the English page with route `en/…` and pointing "Translation Of" to the German one.
- `mirror.py`: read-only facts copied from the source records (on profile save and on source `on_update`).
- `www/web_profile/{listing,profile}.{py,html}` + `templates/web_profile/macros.html`: one listing and one profile template for every section.
- `public/css/web_profile.bundle.css`: design option C; brand colours are the `--wp-*` tokens at the top. Clickable = card, not clickable = chip.
- `public/js/web_profile.bundle.js`: optional enhancement (no-reload filters, load on scroll, mobile drawer, contact dialog). Pages work without it.
- `public/js/web_profile_form.bundle.js`: desk forms show missing translations and "View on Website".

## Adding a section

1. Create `<Source> Web Profile` (base class `WebProfileDocument`; website fields: published, route, image, sort_order, the `translations` table "Web Profile Content").
2. Add it to `mirror.MIRRORS`, `document.TITLE_FIELDS`, `sections.SECTIONS` + a loader + a branch in `build_profile`.
3. Add the slugs to `_WEB_PROFILE_SLUGS` in `hooks.py` and to `web_profile_form.bundle.js`.

## Local testing

```bash
bench --site dev.localhost execute phamos.web_profile.demo.seed   # developer sites only
bench --site dev.localhost set-config web_profile_page_size 4      # see load-on-scroll with few records
```

Tests (privacy, URL and contact rules; needs `allow_tests` in the site config):

```bash
bench --site dev.localhost run-tests --module phamos.tests.test_web_profile
bench --site dev.localhost run-tests --module phamos.tests.test_web_profile_chrome
```

Known gaps: profiles are not yet in `sitemap.xml`, and `llms.txt` is not generated yet (tracked in #1492).
