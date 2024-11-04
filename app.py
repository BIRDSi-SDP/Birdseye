import os
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
import uuid
import bcrypt
from datetime import datetime
from chat_dataset import chat_dataset
from user_dataset import user_dataset
from admin_dashboard import admin_bp

app = Flask(__name__, static_folder='public', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '5fca2f8b274131b6712193dd80a67ced')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///birdseye.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Register the admin blueprint
app.register_blueprint(admin_bp)

# Track connected clients
connected_clients = set()

class User(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    online = db.Column(db.Boolean, default=False)

class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    to_user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    to_user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/admin')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"error": "Username already exists"}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user_id = str(uuid.uuid4())
    new_user = User(id=user_id, username=username, password=hashed_password)

    db.session.add(new_user)
    db.session.commit()

    user_dataset.add_user(username, user_id)

    return jsonify({"userId": user_id, "username": username}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password):
        user.online = True
        db.session.commit()
        return jsonify({"userId": user.id, "username": username})
    else:
        return jsonify({"error": "Invalid username or password"}), 401
    

@app.route('/logout', methods=['POST'])
def logout():
    data = request.json
    user_id = data.get('userId')
    
    user = User.query.get(user_id)
    if user:
        user.online = False
        db.session.commit()
        
        # Remove the user from connected_clients if they're there
        client_sid = next((sid for sid, uid in connected_clients.items() if uid == user_id), None)
        if client_sid:
            del connected_clients[client_sid]
        
        return jsonify({"message": "Logged out successfully"}), 200
    else:
        return jsonify({"error": "User not found"}), 404


@app.route('/send-friend-request', methods=['POST'])
def send_friend_request():
    data = request.json
    from_username = data.get('fromUsername')
    to_username = data.get('toUsername')

    from_user = User.query.filter_by(username=from_username).first()
    to_user = User.query.filter_by(username=to_username).first()

    if not to_user:
        return jsonify({"error": "User not found"}), 404

    # Check if they are already friends
    existing_friendship = Friendship.query.filter(
        ((Friendship.user1_id == from_user.id) & (Friendship.user2_id == to_user.id)) |
        ((Friendship.user1_id == to_user.id) & (Friendship.user2_id == from_user.id))
    ).first()

    if existing_friendship:
        return jsonify({"error": "Already friends"}), 400

    # Check if a friend request already exists
    existing_request = FriendRequest.query.filter_by(from_user_id=from_user.id, to_user_id=to_user.id).first()
    if existing_request:
        return jsonify({"error": "Friend request already sent"}), 400

    new_request = FriendRequest(from_user_id=from_user.id, to_user_id=to_user.id)
    db.session.add(new_request)
    db.session.commit()

    # Emit the friend request to the recipient
    socketio.emit('new_friend_request', {"from": from_username}, room=to_user.id)

    return jsonify({"message": "Friend request sent"}), 200

@app.route('/remove-friend', methods=['POST'])
def remove_friend():
    data = request.json
    username = data.get('username')
    friend_username = data.get('friendUsername')

    user = User.query.filter_by(username=username).first()
    friend = User.query.filter_by(username=friend_username).first()

    if not user or not friend:
        return jsonify({"error": "User not found"}), 404

    friendship = Friendship.query.filter(
        ((Friendship.user1_id == user.id) & (Friendship.user2_id == friend.id)) |
        ((Friendship.user1_id == friend.id) & (Friendship.user2_id == user.id))
    ).first()

    if friendship:
        db.session.delete(friendship)
        db.session.commit()
        return jsonify({"message": "Friend removed"}), 200
    else:
        return jsonify({"error": "Not friends"}), 400


@app.route('/pending-friend-requests/<username>', methods=['GET'])
def get_pending_friend_requests(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    pending_requests = FriendRequest.query.filter_by(to_user_id=user.id).all()
    requests_data = [{
        "id": request.id,
        "from_username": User.query.get(request.from_user_id).username
    } for request in pending_requests]

    return jsonify(requests_data)

@app.route('/accept-friend-request', methods=['POST'])
def accept_friend_request():
    data = request.json
    request_id = data.get('requestId')
    username = data.get('username')

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    friend_request = FriendRequest.query.get(request_id)
    if not friend_request or friend_request.to_user_id != user.id:
        return jsonify({"error": "Invalid friend request"}), 400

    # Create friendship
    new_friendship = Friendship(user1_id=friend_request.from_user_id, user2_id=friend_request.to_user_id)
    db.session.add(new_friendship)

    # Remove the friend request
    db.session.delete(friend_request)
    db.session.commit()

    # Notify both users about the accepted friend request
    from_user = User.query.get(friend_request.from_user_id)
    socketio.emit('friend_request_accepted', {"friend": user.username}, room=from_user.id)
    socketio.emit('friend_request_accepted', {"friend": from_user.username}, room=user.id)

    return jsonify({"message": "Friend request accepted"}), 200


@app.route('/deny-friend-request', methods=['POST'])
def deny_friend_request():
    data = request.json
    request_id = data.get('requestId')
    username = data.get('username')

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    friend_request = FriendRequest.query.get(request_id)
    if not friend_request or friend_request.to_user_id != user.id:
        return jsonify({"error": "Invalid friend request"}), 400

    # Remove the friend request
    db.session.delete(friend_request)
    db.session.commit()

    return jsonify({"message": "Friend request denied"}), 200

@app.route('/friends/<username>', methods=['GET'])
def get_friends(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    friendships = Friendship.query.filter((Friendship.user1_id == user.id) | (Friendship.user2_id == user.id)).all()
    friend_ids = [f.user2_id if f.user1_id == user.id else f.user1_id for f in friendships]
    friends = User.query.filter(User.id.in_(friend_ids)).all()
    friend_usernames = [f.username for f in friends]

    return jsonify(friend_usernames)

@socketio.on('connect')
def handle_connect():
    connected_clients[request.sid] = None  # Initially set to None, will be updated when user authenticates
    emit('update_connected_users', {'count': len([uid for uid in connected_clients.values() if uid])}, broadcast=True)
    print('Client connected')

@socketio.on('authenticate')
def handle_authenticate(data):
    user_id = data.get('userId')
    connected_clients[request.sid] = user_id
    join_room(user_id)
    emit('update_connected_users', {'count': len([uid for uid in connected_clients.values() if uid])}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in connected_clients:
        del connected_clients[request.sid]
    emit('update_connected_users', {'count': len([uid for uid in connected_clients.values() if uid])}, broadcast=True)
    print('Client disconnected')


@socketio.on('message')
def handle_message(data):
    from_user_id = data.get('from')
    to_username = data.get('to')
    content = data.get('content')

    from_user = User.query.get(from_user_id)
    to_user = User.query.filter_by(username=to_username).first()
    if not to_user:
        return

    new_message = Message(from_user_id=from_user_id, to_user_id=to_user.id, content=content)
    db.session.add(new_message)
    db.session.commit()

    chat_dataset.add_message(from_user.username, to_user.username, content)

    message_data = {
        'id': new_message.id,
        'from': from_user.username,
        'content': content,
        'timestamp': new_message.timestamp.isoformat()
    }

    emit('new_message', message_data, room=to_user.id)
    emit('new_message', message_data, room=from_user_id)

connected_clients = set()

@socketio.on('connect')
def handle_connect():
    connected_clients.add(request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    connected_clients.remove(request.sid)

@app.route('/messages/<username>', methods=['GET'])
def get_messages(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    messages = Message.query.filter((Message.from_user_id == user.id) | (Message.to_user_id == user.id)).order_by(Message.timestamp).all()
    message_list = [{
        'id': msg.id,
        'from': User.query.get(msg.from_user_id).username,
        'to': User.query.get(msg.to_user_id).username,
        'content': msg.content,
        'timestamp': msg.timestamp.isoformat()
    } for msg in messages]

    return jsonify(message_list)

@app.route('/admin/stats')
def admin_stats():
    total_users = len(user_dataset.get_users())
    total_messages = len(chat_dataset.data)
    
    return jsonify({
        'connected_users': len(connected_clients),
        'total_users': total_users,
        'total_messages': total_messages
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)