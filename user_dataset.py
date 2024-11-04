# user_dataset.py
import json
from datetime import datetime

class UserDataset:
    def __init__(self, filename='user_dataset.json'):
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

    def add_user(self, username, user_id):
        user = {
            'username': username,
            'user_id': user_id,
            'created_at': datetime.now().isoformat()
        }
        self.data.append(user)
        self.save_data()

    def get_users(self):
        return self.data

user_dataset = UserDataset()