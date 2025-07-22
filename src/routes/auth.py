from flask import Blueprint, request, jsonify, session
from src.models.user import db, User
import re

auth_bp = Blueprint('auth', __name__)

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        username = data.get('username', email.split('@')[0])  # Use email prefix as default username
        
        # Validation
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'User with this email already exists'}), 409
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            tokens=20  # Default 20 tokens for new users
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Set session
        session['user_id'] = new_user.id
        session['user_email'] = new_user.email
        
        return jsonify({
            'message': 'User registered successfully',
            'user': new_user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Set session
        session['user_id'] = user.id
        session['user_email'] = user.email
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    try:
        session.clear()
        return jsonify({'message': 'Logout successful'}), 200
    except Exception as e:
        return jsonify({'error': f'Logout failed: {str(e)}'}), 500

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'user': user.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get user info: {str(e)}'}), 500

@auth_bp.route('/tokens', methods=['GET'])
def get_user_tokens():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'tokens': user.tokens}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get tokens: {str(e)}'}), 500

@auth_bp.route('/tokens/add', methods=['POST'])
def add_tokens():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        tokens_to_add = data.get('tokens', 0)
        
        if not isinstance(tokens_to_add, int) or tokens_to_add <= 0:
            return jsonify({'error': 'Invalid token amount'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.tokens += tokens_to_add
        db.session.commit()
        
        return jsonify({
            'message': f'Added {tokens_to_add} tokens',
            'total_tokens': user.tokens
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to add tokens: {str(e)}'}), 500

@auth_bp.route('/tokens/deduct', methods=['POST'])
def deduct_tokens():
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.get_json()
        tokens_to_deduct = data.get('tokens', 0)
        
        if not isinstance(tokens_to_deduct, int) or tokens_to_deduct <= 0:
            return jsonify({'error': 'Invalid token amount'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.tokens < tokens_to_deduct:
            return jsonify({'error': 'Insufficient tokens'}), 400
        
        user.tokens -= tokens_to_deduct
        db.session.commit()
        
        return jsonify({
            'message': f'Deducted {tokens_to_deduct} tokens',
            'remaining_tokens': user.tokens
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to deduct tokens: {str(e)}'}), 500

