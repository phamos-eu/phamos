import requests
import frappe
from datetime import datetime
import random
import os

import os
from datetime import datetime

def get_thought_of_the_day():
    url = "https://zenquotes.io/api/today"
    
    try:
        response = requests.get(url)
        response.raise_for_status()

        data = response.json()

        if data and isinstance(data, list):
            thought_of_the_day = data[0].get("q","No thought available")
            author = data[0].get("a","Unknown")
            return f"{thought_of_the_day} - {author}"

        else:
            return "No thought available from the API."
    except requests.exceptions.RequestException as e:
        raise f"An error occurred while fetching the thought of the day : {e}"


def post_to_mattermost(channel_id, message, bot_username="Jarvis", parent_id=None):
    """
    Function to post a message to a Mattermost channel and optionally create a thread.

    :param channel_id: The ID of the Mattermost channel
    :param message: The message to post
    :param bot_username: The username of the bot creating the thread (default is "Jarvis")
    :param parent_id: The ID of the parent post to create a thread (optional)
    :return: Response from the Mattermost API
    """
    mattermost_url = frappe.db.get_single_value('phamos Settings', 'mattermost_url') 
    token = frappe.db.get_single_value('phamos Settings', 'token')

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

     # List of emojis
    emojis = [
    "😊", "🎉", "👍", "🚀", "🔥", "😎", "🌟", "💪", "💥", "🎈",
    "😍", "🥳", "🌈", "💖", "✨", "💯", "💫", "🌻", "🦄",  
    "🙌", "🥰", "💚", "💙", "🧡", "💛", "🌸", "🎊", "🥂", "🎶", 
    "👑", "🎁", "🎬", "🤩", "💃", "🕺", "🏆", "👻", "🎨", "🌺",
    "🧚", "🐱", "🐶", "💌", "🌍", "💎", "🍀", "🍓", "🥑", "🍍", 
    "🥝", "🍉", "🍪", "🍩", "🍪", "🍰", "🍪", "🍒", "🍪"
    ]

    # Select a random emoji
    random_emoji = random.choice(emojis)
    
    # Construct the message including the bot's username and today's date
    today_date = datetime.now().strftime("%Y%m%d")
    if parent_id:
        message_with_bot = f"{message}"
    else:
        message_with_bot = f"{today_date} - Daily {random_emoji} {message}"
        

    payload = {
        "channel_id": channel_id,
        "message": message_with_bot
    }

    if parent_id:
        payload["root_id"] = parent_id

    response = requests.post(mattermost_url, json=payload, headers=headers)
    return response.json()



@frappe.whitelist()
def create_mattermost_thread():
    # Get today's date in the desired format (YYYY-MM-DD)
    today_date = frappe.utils.today()  # Returns a string in YYYY-MM-DD format
    
    # Retrieve the last daily thread creation date from the phamos Settings
    last_daily_thread_creation_date = frappe.db.get_single_value('phamos Settings', 'last_daily_thread_creation_date')

   
    # Ensure last_daily_thread_creation_date is in the same format
    if last_daily_thread_creation_date:
        # Convert to string if it’s not already
        last_daily_thread_creation_date_str = str(last_daily_thread_creation_date)

        # Check if the dates match
        if last_daily_thread_creation_date_str == today_date:
            frappe.logger().error("Thread already created for today - {}, - {}".format(last_daily_thread_creation_date, today_date))
            return

    # If dates do not match, proceed to create the thread
    thought_of_the_day = get_thought_of_the_day()

    # Fetch the enabled Mattermost channel
    channel_ids = frappe.db.sql("""
        SELECT channel_id FROM `tabMattermost Channel` WHERE enable = %s
    """, (1,), as_dict=True)

    # List of positive emojis (already defined in your function)
    emojis = [
        "😊", "🎉", "👍", "🚀", "🔥", "😎", "🌟", "💪", "💥", "🎈",  
        "😃", "😍", "🥳", "🌈", "💖", "✨", "💯", "💫", "🌻", "🦄",  
        "🙌", "🥰", "💚", "💙", "🧡", "💛", "🌸", "🎊", "🥂", "🎶", 
        "👑", "🎁", "🎬", "🤩", "💃", "🕺", "🏆", "👻", "🎨", "🌺",
        "🧚", "🐱", "🐶", "💌", "🌍", "💎", "🍀", "🍓", "🥑", "🍍", 
        "🥝", "🍉", "🍪", "🍩", "🍪", "🍰", "🍪", "🍒", "🍪"
    ]
    phamos_emojis = ["🌅", "🌞", "🌿", "🌼", "🌈", "💫", "🌻", "🌟"]

    random_emoji = random.choice(emojis)
    phamos_random_emoji = random.choice(phamos_emojis)

    if not channel_ids:
        frappe.throw("No enabled Mattermost channels found.")
        return
    
    channel_id = channel_ids[0]['channel_id']

    # Construct the reply message with the thought of the day
    #reply_message = f"Good Morning 'phamos' 💮 🙏\n > {thought_of_the_day} 🌟"
    reply_message = f"Good Morning 'phamos' {phamos_random_emoji} 🙏\n > {thought_of_the_day} {random_emoji}"
    # Post the initial message (empty placeholder for the thread start)
    initial_message = ""
    initial_response = post_to_mattermost(channel_id, initial_message)

    initial_post_id = initial_response.get("id")

    if initial_post_id:
        # Post a reply with the thought of the day
        reply_response = post_to_mattermost(channel_id, reply_message, parent_id=initial_post_id)
        
        if reply_response.get("id"):
            # Update the last_daily_thread_creation_date in phamos Settings
            frappe.db.set_single_value("phamos Settings", "last_daily_thread_creation_date", today_date)
        else:
            frappe.throw("Failed to post the reply in Mattermost.")
    else:
        frappe.throw("Failed to create the initial post in Mattermost.")
