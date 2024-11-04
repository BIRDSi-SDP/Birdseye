# chat_dataset.py
import json
from datetime import datetime

class ChatDataset:
    def __init__(self, filename='chat_dataset.json'):
        self.filename = filename
        self.load_data()

    def load_data(self):
        try:
            with open(self.filename, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = []

    def save_data(self):
        with open(self.filename, 'w') as f:
            json.dump(self.data, f)

    def add_message(self, from_user, to_user, content):
        message = {
            'from': from_user,
            'to': to_user,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        self.data.append(message)
        self.save_data()

    def get_messages(self, user1, user2):
        return [msg for msg in self.data if 
                (msg['from'] == user1 and msg['to'] == user2) or 
                (msg['from'] == user2 and msg['to'] == user1)]

chat_dataset = ChatDataset()