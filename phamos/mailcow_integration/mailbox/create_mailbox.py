import frappe
from frappe.utils.password import get_decrypted_password

from .utils import convert_to_base64, generate_password
from .api import create_mailbox, get_mailbox, create_app_password



def provision_mailbox(doc, method):
    if not doc.user_id:
        return
    
    username = doc.user_id

    if method == "on_update":
        res = get_mailbox(username)
        if not len(res.json()) == 0:
            return
        
    full_name = f"{doc.first_name} {doc.last_name}"
    reset_password = generate_password(10)
    domain = frappe.get_single_value("Mailcow Settings", "domain")
    local_part = username.split('@')[0]

    # Create Mailbox
    create_mailbox(domain=domain, local_part=local_part, full_name=full_name, password=reset_password)

    # Create and Save App Password
    if not frappe.db.exists('Mailcow DAV Password', username):
        dav_password = generate_password(12)
        create_app_password(username_email=username, app_name='ERPNext', app_password=dav_password)
        dav_doc = frappe.get_doc({'doctype':'Mailcow DAV Password', 'user_email': username, 'dav_password': dav_password,'reset_password': reset_password})
        dav_doc.insert()
    else:
        dav_doc = frappe.get_doc('Mailcow DAV Password', username)
        dav_password = generate_password(12)
        create_app_password(username_email=username, app_name='ERPNext', app_password=dav_doc.dav_password)
        dav_doc.reset_password = reset_password
        dav_doc.dav_password = dav_password
        dav_doc.save()
    
    msg = f'''
                <div><h5> Email for {full_name} Provisioned Successfully</h5><br><br>
                Email: {username}<br><br>
                Password: {reset_password}</div>
        '''
    frappe.msgprint(msg)