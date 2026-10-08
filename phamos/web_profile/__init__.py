"""Web Profiles: the reusable data + page pattern behind the public website sections.

Every public section (/people, /departments, /teams, /modules, /implementations, /industries)
is backed by one ``<Source> Web Profile`` doctype that holds only public data and mirrors facts
from its internal source record. One listing page and one profile page render every section;
``sections.py`` declares what differs per section. Design decisions: phamos/phamos#1492.
"""
