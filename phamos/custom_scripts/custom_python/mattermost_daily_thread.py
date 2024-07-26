import requests
import frappe
from datetime import datetime
import random
import os

import os
from datetime import datetime

def get_thought_of_the_day():
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the full file path to thoughtOftheDay.txt
    file_path = os.path.join(script_dir, 'thoughtOftheDay.txt')

    try:
        with open(file_path, 'r') as file:
            thoughts = file.readlines()

        thought_of_the_day = random.choice(thoughts).strip()

        return thought_of_the_day
    except FileNotFoundError:
        raise FileNotFoundError(f"File '{file_path}' not found")

# Example usage:
try:
    thought = get_thought_of_the_day()
    print(f"Thought of the day: {thought}")
except FileNotFoundError as e:
    print(e)


def post_to_mattermost(channel_id, message, bot_username="Jarvis", parent_id=None):
    """
    Function to post a message to a Mattermost channel and optionally create a thread.

    :param channel_id: The ID of the Mattermost channel
    :param message: The message to post
    :param bot_username: The username of the bot creating the thread (default is "Jarvis")
    :param parent_id: The ID of the parent post to create a thread (optional)
    :return: Response from the Mattermost API
    """
    mattermost_url = "https://chat.phamos.eu/api/v4/posts"  # Replace with your Mattermost server URL
    token = "xk81d48io3d3igwohegetf7n3w"  # Replace with your Mattermost access token

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

     # List of emojis
    emojis = ["😊", "🎉", "👍", "🚀", "🔥", "😎", "🌟", "💪", "💥", "🎈"]

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
    frappe.logger().info("Executing create_mattermost_thread function...")
    """
    Function to create a new thread in Mattermost with an initial message and a reply.
    """

    thought_of_the_day = get_thought_of_the_day()
    channel_ids = frappe.db.sql("""
        select channel_id from `tabMattermost Channel` where enable = %s
    """,{1}, as_dict=True)

    if channel_ids:
        channel_id = channel_ids[0]['channel_id']  # Replace with your Mattermost channel ID
    else:
        return    
    
    #reply_message = "Good Morning 'phamos'"
    reply_message = f"Good Morning 'phamos' 💮 🙏\n > {thought_of_the_day}🌟"
   

    # Post the initial message with today's date and "Daily"
    initial_message = ""  # Placeholder message, as initial_message needs to be constructed dynamically
    initial_response = post_to_mattermost(channel_id, initial_message)
    initial_post_id = initial_response.get("id")

    if initial_post_id:
        # Post a reply with the reply_message
        reply_response = post_to_mattermost(channel_id,reply_message, parent_id=initial_post_id)
        
        if reply_response.get("id"):
            frappe.msgprint(f"Thread created in Mattermost with initial post ID: {initial_post_id} and reply post ID: {reply_response.get('id')}")
        else:
            frappe.throw("Failed to post the reply in Mattermost.")
    else:
        frappe.throw("Failed to create the initial post in Mattermost.")
