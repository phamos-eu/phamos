import frappe

def execute():
    old_to_new_levels = {
        "1 - Start der Implementierung, keine Vorerfahrung, noch kein": "1 - Inception Phase. Early Implementation, no previous Frappe experience",
        "2 - Poweruser kann sich orientieren,": "2 - Initial Development Phase. Initial development work, Power user can navigate system",
        "3 - Live-Betrieb, Erste Module sind im Einsatz,": "3 - Development Phase. Development process understood, first modules customized",
        "4 - Erste Module abgeschlossen, Entwicklungsprozesse in der Tiefe verstanden,": "4 - Go Live Phase. Go Live, first modules in use with real life data",
        "5 - Quasi-abgeschlossen, System ist implementiert, Viele geschulte Anwender, hoher Automatisierungsgrad,": "5 - Live Development Phase. Ongoing development in parallel to system in daily use with live data"
    }

    for old, new in old_to_new_levels.items():
        frappe.db.set_value(
            "Implementation",
            {"maturity_level": old},
            "maturity_level",
            new,
            update_modified=False
        )

    frappe.db.commit()
