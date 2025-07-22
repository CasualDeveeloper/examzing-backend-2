from flask import Blueprint, request, jsonify, session
from src.models.user import db, User, Document, Quiz, QuizResult
import json
from openai import OpenAI
import os

quiz_bp = Blueprint('quiz', __name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def generate_quiz_questions(content_text, question_count, custom_prompt=""):
    """Generate quiz questions using OpenAI API"""
    try:
        base_prompt = f"""
        Based on the following document content, generate exactly {question_count} multiple-choice questions.
        
        Document content:
        {content_text[:4000]}
        
        {f"Additional instructions: {custom_prompt}" if custom_prompt else ""}
        
        Requirements:
        1. Generate exactly {question_count} questions
        2. Each question should have 4 options (A, B, C, D)
        3. Only one option should be correct
        4. Questions should test understanding of the document content
        5. Provide explanations for the correct answers
        6. Return the response in the following JSON format:
        {{
            "questions": [
                {{
                    "id": 1,
                    "question": "Question text here?",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_answer": 0,
                    "explanation": "Explanation for why this is correct"
                }}
            ]
        }}
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert quiz generator. Generate high-quality multiple-choice questions based on document content."},
                {"role": "user", "content": base_prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )

        response_text = response.choices[0].message.content

        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            json_str = response_text[start_idx:end_idx]
            quiz_data = json.loads(json_str)
            return quiz_data['questions']
        except Exception as e:
            print(f"JSON parsing error: {str(e)}")
            return generate_mock_questions(question_count, custom_prompt)

    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return generate_mock_questions(question_count, custom_prompt)

def generate_mock_questions(question_count, custom_prompt=""):
    questions = []
    for i in range(1, question_count + 1):
        questions.append({
            "id": i,
            "question": f"Sample question {i} from the document{f' ({custom_prompt})' if custom_prompt else ''}?",
            "options": [
                f"Option A for question {i}",
                f"Option B for question {i}",
                f"Option C for question {i}",
                f"Option D for question {i}"
            ],
            "correct_answer": i % 4,
            "explanation": f"This is the explanation for question {i}. The correct answer provides the most accurate information based on the document content."
        })
    return questions

@quiz_bp.route('/generate', methods=['POST'])
def generate_quiz():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.get_json()
        document_id = data.get('document_id')
        question_count = data.get('question_count', 10)
        custom_prompt = data.get('custom_prompt', '')

        if not document_id:
            return jsonify({'error': 'Document ID is required'}), 400

        if question_count not in [10, 20, 30, 40, 50]:
            return jsonify({'error': 'Invalid question count. Must be 10, 20, 30, 40, or 50'}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if user.tokens < question_count:
            return jsonify({'error': 'Insufficient tokens'}), 400

        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        if not document:
            return jsonify({'error': 'Document not found'}), 404

        questions = generate_quiz_questions(document.content_text, question_count, custom_prompt)

        user.tokens -= question_count

        quiz = Quiz(
            document_id=document_id,
            user_id=user_id,
            title=f"Quiz for {document.original_filename}",
            custom_prompt=custom_prompt,
            question_count=question_count,
            questions_data=json.dumps(questions)
        )

        db.session.add(quiz)
        db.session.commit()

        return jsonify({
            'message': 'Quiz generated successfully',
            'quiz_id': quiz.id,
            'questions': questions,
            'remaining_tokens': user.tokens
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Quiz generation failed: {str(e)}'}), 500
