// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer", {
    refresh(frm) {
        render_gitlab_groups_section(frm);
        render_gitlab_projects_section(frm);
        render_gitlab_issues_section(frm);
        if (!document.getElementById("gitlab-custom-style")) {
            const style = document.createElement("style");
            style.id = "gitlab-custom-style";
            style.innerHTML = `
                .gitlab-project-connection .document-link {
                    display: flex;
                    align-items: center;
                }

                .gitlab-project-connection .document-link-badge {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }

                .gitlab-project-connection .btn-new {
                    height: 22px;
                    width: 22px;
                    padding: 0;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .gitlab-project-connection .btn-new svg {
                    width: 12px;
                    height: 12px;
                }
            `;
            document.head.appendChild(style);
        }

        frm.add_custom_button('Create Gitlab Group', function () {
        // Confirmation dialog with editable name
        let d = new frappe.ui.Dialog({
            title: 'Create GitLab Group',
            fields: [
                {
                    label: 'GitLab Group Name',
                    fieldname: 'gitlab_group_name',
                    fieldtype: 'Data',
                    default: frm.doc.name,
                    reqd: 1,
                    description: 'You can edit this name for GitLab Group. Customer link will remain the same.'
                }
            ],
            primary_action_label: 'Create Group',
            primary_action(values) {
                d.hide();
                frappe.call({
                    method: 'phamos.gitlab_integration.gitlab_group_utils.create_gitlab_group_for_customer',
                    args: {
                        customer_name: frm.doc.name,         
                        gitlab_group_name: values.gitlab_group_name  
                    },
                    callback: function (r) {
                        frappe.msgprint(r.message || "GitLab Group created successfully!");
                        frm.reload_doc();
                    }
                });
            }
        });
        d.show();
    }, __("Create"));

    },
});

function render_gitlab_groups_section(frm) {
        if (frm.is_new()) return;

        const customer = frm.doc.name;
        const wrapper = frm.fields_dict.custom_gitlab_group?.wrapper;

        if (!wrapper) return;

        // clear old
        $(wrapper).empty();

        // UI block (same style feel)
        $(wrapper).html(`
            <div class="gitlab-project-connection">
                <div class="document-link" data-doctype="GitLab Group">
                    <div class="document-link-badge">
                        <span class="count hidden"></span>
                        <a class="badge-link">${__("GitLab Group")}</a>
                        <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                    </div>
                </div>
            </div>
        `);

        const $link = $(wrapper).find(".document-link");
        const $count = $link.find(".count");

        // open list
        $link.find(".badge-link").on("click", e => {
            e.preventDefault();
            frappe.route_options = {
                customer: customer
            };
            frappe.set_route("List", "GitLab Group", "List");
        });

        // new
        $link.find(".btn-new").on("click", e => {
            e.preventDefault();
            frappe.new_doc("GitLab Group", {
                customer: customer
            });
        });

        // count
        frappe.call({
            method: "phamos.api.get_gitlab_group_count",
            args: {
                customer: customer
            },
            callback: r => {
                const c = cint(r.message);
                $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c || "0");
            }
        });
    }

function render_gitlab_projects_section(frm) {
    if (frm.is_new()) return;

    const customer = frm.doc.name;
    const wrapper = frm.fields_dict.custom_gitlab_project?.wrapper;

    if (!wrapper) return;

    $(wrapper).empty();

    $(wrapper).html(`
        <div class="gitlab-project-connection">
            <div class="document-link" data-doctype="GitLab Project">
                <div class="document-link-badge">
                    <span class="count hidden"></span>
                    <a class="badge-link" href="#">${__("GitLab Projects")}</a>
                    <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                </div>
            </div>
        </div>
    `);

    const $link = $(wrapper).find(".document-link");
    const $count = $link.find(".count");

    // open list — group chain ke through
    $link.find(".badge-link").on("click", function (e) {
        e.preventDefault();

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "GitLab Group",
                filters: { customer: customer },
                fields: ["name"],
                limit: 0
            },
            callback: function (r) {
                const groups = (r.message || []).map(d => d.name);

                if (!groups.length) {
                    frappe.msgprint(__("Koi GitLab Group linked nahi hai is customer se."));
                    return;
                }

                frappe.route_options = {
                    group: ["in", groups]
                };
                frappe.set_route("List", "GitLab Project", "List");
            }
        });
    });

    // new project
    $link.find(".btn-new").on("click", function (e) {
        e.preventDefault();
        frappe.new_doc("GitLab Project", {
            customer: customer
        });
    });

    // count
    frappe.call({
        method: "phamos.api.get_gitlab_project_count",
        args: { customer: customer },
        callback: function (r) {
            const c = cint(r.message);
            $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c || "0");
        }
    });
}

function render_gitlab_issues_section(frm) {
    if (frm.is_new()) return;

    const customer = frm.doc.name;
    const wrapper = frm.fields_dict.custom_gitlab_issue?.wrapper;

    if (!wrapper) return;

    $(wrapper).empty();

    $(wrapper).html(`
        <div class="gitlab-project-connection">
            <div class="document-link" data-doctype="GitLab Issue">
                <div class="document-link-badge">
                    <span class="count hidden"></span>
                    <a class="badge-link" href="#">${__("GitLab Issues")}</a>
                    <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                </div>
            </div>
        </div>
    `);

    const $link = $(wrapper).find(".document-link");
    const $count = $link.find(".count");

    $link.find(".badge-link").on("click", function (e) {
        e.preventDefault();

        // Step 1: Customer ke Groups
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "GitLab Group",
                filters: { customer: customer },
                fields: ["name"],
                limit: 0
            },
            callback: function (r) {
                const groups = (r.message || []).map(d => d.name);

                if (!groups.length) {
                    frappe.msgprint(__("Koi GitLab Group linked nahi hai is customer se."));
                    return;
                }

                // Step 2: Un Groups ke Projects
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "GitLab Project",
                        filters: { group: ["in", groups] },
                        fields: ["name"],
                        limit: 0
                    },
                    callback: function (r2) {
                        const projects = (r2.message || []).map(d => d.name);

                        if (!projects.length) {
                            frappe.msgprint(__("Koi GitLab Project linked nahi hai is customer ke groups se."));
                            return;
                        }

                        // Step 3: Un Projects ki Issues list open karo
                        frappe.route_options = {
                            gitlab_project: ["in", projects]
                        };
                        frappe.set_route("List", "GitLab Issue", "List");
                    }
                });
            }
        });
    });

    $link.find(".btn-new").on("click", function (e) {
        e.preventDefault();
        frappe.new_doc("GitLab Issue", {
            customer: customer
        });
    });

    // count
    frappe.call({
        method: "phamos.api.get_gitlab_issue_count",
        args: { customer: customer },
        callback: function (r) {
            const c = cint(r.message);
            $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c || "0");
        }
    });
}