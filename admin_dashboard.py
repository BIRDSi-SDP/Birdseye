# admin_dashboard.py
from flask import Blueprint, render_template, jsonify
from chat_dataset import chat_dataset
from user_dataset import user_dataset

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@admin_bp.route('/admin/stats')
def admin_stats():
    # We'll get connected_users from the main app
    total_users = len(user_dataset.get_users())
    total_messages = len(chat_dataset.data)
    
    return jsonify({
        'total_users': total_users,
        'total_messages': total_messages
    })