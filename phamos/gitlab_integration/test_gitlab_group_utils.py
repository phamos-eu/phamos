from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from phamos.gitlab_integration import gitlab_group_utils as utils

MODULE = "phamos.gitlab_integration.gitlab_group_utils"

CUSTOMER = "Test Gitlab customer"
IMPLEMENTATION = "testing Gitlab customer"


class FakeDB:
    """In-memory stand-in for the records these functions read and write.

    No GitLab API call and no database write happens in these tests.
    """

    def __init__(self, groups=(), implementations=None):
        self.rows = {"GitLab Group": [dict(g) for g in groups], "GitLab Project": []}
        self.implementations = implementations or {IMPLEMENTATION: CUSTOMER}

    def _matches(self, doctype, filters):
        return [
            row for row in self.rows.get(doctype, [])
            if all(row.get(k) == v for k, v in (filters or {}).items())
        ]

    def get_value(self, doctype, filters, fieldname="name", as_dict=False, **kwargs):
        rows = self._matches(doctype, filters)
        if not rows:
            return None
        row = rows[0]
        if isinstance(fieldname, (list, tuple)):
            values = {f: row.get(f) for f in fieldname}
            return frappe._dict(values) if as_dict else tuple(values.values())
        return row.get(fieldname)

    def get_all(self, doctype, filters=None, fields=None, **kwargs):
        fields = fields or ["name"]
        return [frappe._dict({f: row.get(f) for f in fields}) for row in self._matches(doctype, filters)]

    def exists(self, doctype, filters):
        return bool(self._matches(doctype, filters))

    def commit(self):
        pass

    def get_doc(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            data = dict(args[0])
            doc = frappe._dict(data)
            doc.insert = lambda **kw: self.rows[data["doctype"]].append(data)
            return doc

        doctype, name = args[0], args[1]
        if doctype == "Implementation":
            return frappe._dict(name=name, customer=self.implementations[name])
        if doctype == "Customer":
            return frappe._dict(name=name, image=None)
        raise AssertionError(f"unexpected get_doc({doctype!r}, {name!r})")


def group(group_id, title, customer):
    return {"name": str(group_id), "group_id": group_id, "title": title, "customer": customer}


def fake_project(name, group_id):
    return {
        "id": 888001,
        "web_url": f"https://git.example/x/{name}",
        "path_with_namespace": f"x/{name}",
        "namespace": {"kind": "group", "id": group_id},
    }


class TestCreateGitlabProjectForImplementation(TestCase):
    def run_create(self, db, project_name="proj-1293"):
        with patch.object(frappe, "db", db), \
                patch.object(frappe, "get_doc", db.get_doc), \
                patch.object(frappe, "msgprint"), \
                patch(f"{MODULE}.create_gitlab_project") as create:
            create.side_effect = lambda name, group_id, customer_doc=None: fake_project(name, group_id)
            try:
                utils.create_gitlab_project_for_implementation(IMPLEMENTATION, project_name)
            finally:
                self.create = create

    def test_finds_group_whose_title_differs_from_the_customer(self):
        """phamos/phamos#1293: the group was renamed when it was created."""
        db = FakeDB(groups=[group(419, "Test Gitlab rename", CUSTOMER)])

        self.run_create(db)

        self.create.assert_called_once()
        self.assertEqual(self.create.call_args.args[1], 419)
        project = db.rows["GitLab Project"][0]
        self.assertEqual(project["implementation"], IMPLEMENTATION)
        self.assertEqual(project["group"], "419")

    def test_never_uses_the_group_of_another_customer(self):
        """A group titled like this customer but linked to another one is not used."""
        db = FakeDB(groups=[group(500, CUSTOMER, "Other customer")])

        with self.assertRaisesRegex(frappe.ValidationError, "No GitLab Group found"):
            self.run_create(db)
        self.create.assert_not_called()

    def test_group_without_gitlab_id_gives_a_clear_error(self):
        row = group(419, CUSTOMER, CUSTOMER)
        row["group_id"] = None
        db = FakeDB(groups=[row])

        with self.assertRaisesRegex(frappe.ValidationError, "has no GitLab group ID"):
            self.run_create(db)
        self.create.assert_not_called()

    def test_no_group_for_the_customer_still_raises(self):
        db = FakeDB()

        with self.assertRaisesRegex(frappe.ValidationError, "No GitLab Group found"):
            self.run_create(db)
        self.create.assert_not_called()

    def test_second_project_for_the_same_implementation_is_blocked(self):
        db = FakeDB(groups=[group(419, "Test Gitlab rename", CUSTOMER)])
        self.run_create(db)

        with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
            self.run_create(db, project_name="proj-1293-2")


class TestCustomerAvatarSync(TestCase):
    def test_avatar_sync_finds_a_renamed_group(self):
        db = FakeDB(groups=[group(419, "Test Gitlab rename", CUSTOMER)])
        db.rows["GitLab Project"].append({"group": "419", "project_id": 888001})
        customer = MagicMock()
        customer.name = CUSTOMER
        customer.image = "/files/new-logo.png"
        customer.get_doc_before_save.return_value = None

        with patch.object(frappe, "db", db), \
                patch(f"{MODULE}.update_gitlab_avatar") as update_avatar:
            utils.update_gitlab_avatar_on_customer(customer)

        group_ids = [c.kwargs.get("group_id") for c in update_avatar.call_args_list]
        project_ids = [c.kwargs.get("project_id") for c in update_avatar.call_args_list]
        self.assertIn(419, group_ids)
        self.assertIn(888001, project_ids)
